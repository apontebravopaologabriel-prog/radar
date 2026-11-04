"""Conservative requirement evidence shared by map scoring and CV gaps."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

from radar.classification_text import contains, job_text
from radar.normalize import normalize_text


@cache
def qualification_aliases():
    return json.loads((Path(__file__).parent / "careers/qualifications.json").read_text(encoding="utf-8"))


def clauses(description):
    text = job_text(description).role.replace("ing.", "ing")
    return [c.strip() for c in re.split(r"\n|;|(?<=[.!?])\s+", text) if c.strip()]


def assessment(status, reason, quote="", required=True, **extra):
    return {"status": status, "reason": reason, "quote": quote[:350], "required": required,
            "lower": {"met": 100.0, "partial": 50.0}.get(status, 0.0),
            "upper": 100.0 if status in {"unknown", "partial"} else (100.0 if status == "met" else 0.0),
            **extra}


def optional(text):
    return any(contains(text, t) for t in ("deseable", "preferible", "preferentemente", "preferred", "plus", "no indispensable", "no excluyente"))


_DEGREE = re.compile(r"\b(estudiant\w*|en curso|ultimos ciclos|egresad\w*|graduad\w*|bachiller|bachelor|titulad\w*|licenciad\w*)\b")


def degree_level(text):
    found = []
    for m in _DEGREE.finditer(normalize_text(text)):
        word = m.group()
        level = 0 if word.startswith("estudiant") or word in {"en curso", "ultimos ciclos"} else 1 if word.startswith(("egresad", "graduad")) else 2 if word in {"bachiller", "bachelor"} else 3
        found.append((m.start(), level))
    return found


def _families(text):
    return {family for family, aliases in qualification_aliases().items()
            if any(contains(text, alias) for alias in aliases)}


def education_assessment(description, profile):
    candidates = [c for c in clauses(description) if _families(c) and
                  (degree_level(c) or re.search(r"\b(carrera|formacion|profesional|degree|requisito)", c))]
    if not candidates:
        return assessment("unknown", "La oferta no precisa formación suficiente para comparar.")
    education = profile.get("education", [])
    if isinstance(education, str):
        education = [{"program": education, "status": education}]
    if not education:
        return assessment("unknown", "Tu perfil no declara formación comparable.", " | ".join(candidates))
    records = []
    for item in education:
        text = normalize_text(item.get("program", ""))
        status = normalize_text(item.get("status", ""))
        levels = degree_level(status or text)
        records.append((_families(text), max((level for _, level in levels), default=None), status, text))
    results = []
    for clause in candidates:
        alternatives = []
        families = _families(clause)
        levels = degree_level(clause)
        matched = False
        for own, own_level, own_status, own_program in records:
            shared = families & own
            if not shared:
                continue
            matched = True
            # Degrees preceding each program belong to that alternative. A shared prefix applies
            # to the subsequent list; “egresado o bachiller” uses the less restrictive alternative.
            for family in shared:
                positions = [clause.find(alias) for alias in qualification_aliases()[family] if contains(clause, alias)]
                pos = min(positions)
                prefix = clause[:pos]
                other_programs = [alias for f, aliases in qualification_aliases().items() if f != family
                                  for alias in aliases if contains(prefix, alias)]
                if other_programs:
                    previous_end = max(prefix.rfind(alias)+len(alias) for alias in other_programs)
                    local_levels = [(p, level) for p, level in levels if previous_end <= p < pos]
                else:
                    local_levels = [(p, level) for p, level in levels if p < pos]
                required_level = min((level for _, level in local_levels or levels), default=None)
                if own_level is None or required_level is None:
                    alternatives.append(assessment("unknown", "La carrera coincide, pero el grado no está suficientemente definido.", clause, not optional(clause)))
                elif own_level < required_level:
                    alternatives.append(assessment("missing", "Tu perfil no acredita el grado solicitado para esa carrera.", clause, not optional(clause)))
                elif (required_level == 2 or contains(clause, "universitario")) and own_level == 3 and not any(
                    contains(own_program + " " + own_status, t)
                    for t in ("ingenieria", "universitario", "bachiller", "bachelor")
                ):
                    alternatives.append(assessment("unknown", "El título declarado no confirma el grado universitario exigido.", clause, not optional(clause)))
                elif any(contains(clause, term) and not contains(own_status, term) for term in ("colegiado", "habilitado")):
                    alternatives.append(assessment("partial", "Carrera y grado coinciden; falta acreditar colegiatura o habilitación.", clause, not optional(clause)))
                else:
                    alternatives.append(assessment("met", "Carrera y grado coinciden con la formación declarada.", clause, not optional(clause)))
        if not matched:
            related = any(contains(clause, term) for term in ("afines", "related", "similar"))
            alternatives.append(assessment("unknown" if related else "missing",
                                      "Solo indica carreras afines; no confirma aceptación de tu carrera." if related else "Tu perfil no acredita una de las carreras indicadas.",
                                      clause, not optional(clause)))
        results.append(max(alternatives, key=lambda r: {"met": 3, "partial": 2, "unknown": 1, "missing": 0}[r["status"]]))
    mandatory = [item for item in results if item["required"]]
    return min(mandatory or results, key=lambda r: {"met": 3, "partial": 2, "unknown": 1, "missing": 0}[r["status"]])


def month_set(entries, now=None):
    today = now or datetime.now(UTC)
    current = today.year*12+today.month-1
    months = set()
    for item in entries:
        first, last = str(item.get("from") or ""), str(item.get("to") or "")
        if not re.match(r"^\d{4}-\d{2}", first):
            continue
        if not 1 <= int(first[5:7]) <= 12:
            continue
        start = int(first[:4])*12+int(first[5:7])-1
        if re.match(r"^\d{4}-\d{2}", last):
            if not 1 <= int(last[5:7]) <= 12:
                continue
            end = min(current, int(last[:4])*12+int(last[5:7])-1)
        elif last and normalize_text(last) not in {"actualidad", "presente", "present", "actual"}:
            continue
        else:
            end = current
        if 1900*12 <= start <= end:
            months.update(range(start, end+1))
    return months


_YEARS = re.compile(r"(?:experiencia\s+(?:minima\s+)?(?:de\s+)?|minimum\s+)?(\d+(?:[.,]\d+)?)\s*(?:(?:a|-|–|y)\s*\d+\s*)?(anos?|years?|meses?|months?)\s*(?:de\s+)?(?:experiencia|experience)?")


def experience_assessment(description, profile, skill_names=()):
    found = []
    for clause in clauses(description):
        if "experiencia" not in clause and "experience" not in clause:
            continue
        if re.search(r"\b(?:no se requiere|sin necesidad de|no requiere)\b", clause):
            continue
        match = _YEARS.search(clause)
        if match:
            prefix = clause[:match.start()]
            if re.search(r"\b(?:empresa|compania|organizacion|somos)\b", prefix) and not re.search(
                r"\b(?:buscamos|busqueda|requisitos|requerimos|candidato|postulante|perfil)\b", prefix
            ):
                continue
            required = float(match[1].replace(",", ".")) * (12 if match[2].startswith(("ano", "year")) else 1)
            scope = clause[match.end():].strip(" .,:-")
            # Match an explicit specialization conservatively; generic experience uses all dated work.
            scope = re.sub(r"^(?:de experiencia|experience|en|in)\s*", "", scope)
            tokens = [t for t in re.findall(r"\w+", scope) if len(t)>2 and t not in {"experiencia", "puestos", "similares", "posiciones", "minimo", "minima", "para", "como", "con", "del", "los", "las", "una", "anos", "meses"}]
            comparable_unknown = not tokens and any(contains(scope, t) for t in ("similares", "similar", "afines"))
            entries = profile.get("experience") or []
            total = len(month_set(entries))
            related_entries = []
            for entry in entries:
                text = normalize_text(" ".join([entry.get("role") or "", *entry.get("bullets", []), *entry.get("skills", [])]))
                if tokens:
                    related = all(re.search(rf"\b{re.escape(t[:5])}\w*", text) for t in tokens)
                else:
                    related = True
                if related:
                    related_entries.append(entry)
            related = len(month_set(related_entries))
            if not entries or not total:
                status, reason = "unknown", "Tu perfil no aporta fechas de experiencia suficientes."
            elif total < required:
                status, reason = "missing", f"Suman ~{total/12:.1f} años entre experiencias sin duplicar meses simultáneos."
            elif comparable_unknown:
                status, reason = "unknown", "Las fechas cubren el mínimo total, pero ‘puestos similares’ no concreta una especialidad comparable."
            elif related < required:
                status, reason = "partial", f"Sumas ~{total/12:.1f} años; solo ~{related/12:.1f} coinciden con la especialidad indicada."
            else:
                status, reason = "met", f"~{related/12:.1f} años declarados con fechas y ámbito comparables."
            found.append(assessment(status, reason, clause, not optional(clause), required_months=required,
                                    total_months=total, related_months=related))
    if not found:
        return assessment("unknown", "La oferta no concreta meses o años de experiencia.")
    mandatory = [item for item in found if item["required"]]
    return min(mandatory or found, key=lambda r: {"missing": 0, "unknown": 1, "partial": 2, "met": 3}[r["status"]])


def skill_level(description, name, aliases=()):
    matches = []
    for clause in clauses(description):
        for alias in (name, *aliases):
            match = re.search(rf"(?<!\w){re.escape(normalize_text(alias))}(?!\w)", clause)
            if not match:
                continue
            # Stop at a list separator so “SQL, Excel avanzado” does not raise SQL's level.
            after = re.split(r",|\s+y\s+|\s+and\s+", clause[match.end():match.end()+65])[0]
            before = clause[max(0, match.start()-25):match.start()]
            local = after if re.search(r"basico|intermedio|avanzado|basic|intermediate|advanced", after) else before if before.rstrip().endswith(("de", "in")) else ""
            level = next((key for key, phrases in (("advanced", ("avanzado", "advanced")), ("intermediate", ("intermedio", "intermediate")), ("basic", ("basico", "basic"))) if any(contains(local, phrase) for phrase in phrases)), None)
            if level:
                matches.append((level, clause, not optional(clause)))
    order = {"basic": 1, "intermediate": 2, "advanced": 3}
    return max(matches, key=lambda x: order[x[0]]) if matches else (None, "", True)
