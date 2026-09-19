"""Brecha base determinista entre una oferta y el perfil real, sin LLM.

Cruza las skills que Radar ya detectó en la oferta (``job_skills``), los años de experiencia y el
nivel de estudios pedidos en la descripción contra ``cv_master.json``. Cada resultado conserva su
evidencia. Las ofertas marcadas con estrella (favoritos) son los objetivos. El agente puede
enriquecer un objetivo con un candidato ideal, pero el estado de lo que el código ya calculó no se
lo puede reasignar el agente. Ver ``docs/target-profiles.md``.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, date, datetime
from typing import Any

from radar import cv_targets
from radar.db.database import connection
from radar.geolocation import infer_location

_ALIASES = {
    "power bi": ["power bi", "powerbi"],
    "sql": ["sql", "structured query language"],
    "optimization": ["optimizacion", "optimization"],
    "inventory management": ["inventario", "inventarios", "inventory"],
    "english": ["ingles", "english"],
    "lean manufacturing": ["lean"],
}
_WEIGHT = {"required": 1.0, "unknown": 0.8, "preferred": 0.6, "desirable": 0.4}
_YEARS = [
    re.compile(r"(\d+)\s*(?:a|-|y)\s*(\d+)\s*a[nñ]os?\s+de\s+experiencia", re.IGNORECASE),
    re.compile(r"experiencia\s+(?:m[ií]nima\s+)?(?:de\s+)?(\d+)(?:\s*(?:a|-)\s*(\d+))?\s*a[nñ]os?", re.IGNORECASE),
    re.compile(r"(\d+)\+?\s*a[nñ]os?\s+de\s+experiencia", re.IGNORECASE),
]
_DEGREE = re.compile(r"\b(bachiller|egresad[oa]|titulad[oa])\b", re.IGNORECASE)
_STUDENT = re.compile(r"\b(estudiante|practicante|pr[aá]cticas)\b", re.IGNORECASE)


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFD", value.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _clean_quote(value: str | None, limit: int = 140) -> str | None:
    """Cita legible: sin marcas de markdown, espacios colapsados y cortada en palabra completa."""
    if not value:
        return None
    text = re.sub(r"[*_#>`|\\-]{2,}|[*#`]", " ", value)
    text = re.sub(r"\s+", " ", text).strip(" .,;:-")
    if len(text) <= limit:
        return text or None
    return text[:limit].rsplit(" ", 1)[0] + "…"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _norm(value)).strip("-")


def _contains(text: str, term: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", _norm(text)) is not None


def _evidence(name: str, profile: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Evidencia fuerte (certificados, experiencia) y débil (aptitudes de estudios, autodeclaración)."""
    terms = _ALIASES.get(_norm(name), [_norm(name)])
    strong: list[str] = []
    weak: list[str] = []
    for cert in profile.get("certifications", []):
        if any(_contains(cert.get("name", ""), t) for t in terms):
            strong.append(f"certificado: {cert['name']}")
    for job in profile.get("experience", []):
        haystack = " ".join([*job.get("bullets", []), *job.get("skills", [])])
        if any(_contains(haystack, t) for t in terms):
            strong.append(f"experiencia: {job.get('role')} en {job.get('company')}")
    for school in profile.get("education", []):
        if any(_contains(" ".join(school.get("skills", [])), t) for t in terms):
            weak.append(f"aptitud en {school.get('institution')}")
    for tool, level in (profile.get("tools_declared_in_db") or {}).items():
        if not tool.startswith("_") and any(_contains(tool, t) for t in terms):
            weak.append(f"autodeclarado {level}")
    return strong, weak


def _months(start: str | None, end: str | None) -> int:
    def parse(value: str | None) -> date | None:
        if not value or not re.match(r"^\d{4}-\d{2}", value):
            return None
        return date(int(value[:4]), int(value[5:7]), 1)

    first, last = parse(start), parse(end) or datetime.now(UTC).date()
    return max(0, (last.year - first.year) * 12 + last.month - first.month + 1) if first else 0


def _experience_item(description: str, profile: dict[str, Any]) -> dict[str, Any] | None:
    for pattern in _YEARS:
        match = pattern.search(description)
        if match:
            required = int(match.group(1))
            quote = description[max(0, match.start() - 20) : match.end() + 20].strip()
            years = sum(_months(j.get("from"), j.get("to")) for j in profile.get("experience", [])) / 12
            missing = required > years
            return {
                "key": "experiencia-previa", "label": f"Experiencia previa (mín. {required} {'año' if required == 1 else 'años'})",
                "requirement": "required", "category": "experience", "blocker": missing,
                "status": "falta" if missing else "parcial",
                "reason": f"Suman ~{years:.1f} años entre tus experiencias, en cualquier rol"
                          + ("" if missing else "; no se verifica que sean del área"),
                "quote": quote,
            }
    return None


def _education_item(description: str, profile: dict[str, Any]) -> dict[str, Any] | None:
    studying = [s for s in profile.get("education", []) if "curso" in str(s.get("status", ""))]
    degree, student = _DEGREE.search(description), _STUDENT.search(description)
    if not degree and not student:
        return None
    current = studying[0] if studying else None
    until = f" (hasta {current['to']})" if current else ""
    if degree and student:
        status, reason = "parcial", "Acepta estudiantes de últimos ciclos" + until
    elif degree:
        status, reason = "falta", "Pide grado; aún cursas " + (current["program"] if current else "estudios") + until
    else:
        status, reason = "cubierto", "Cursas " + (current["program"] if current else "estudios") + until
    quote = (degree or student).group(0)
    return {
        "key": "formacion", "label": "Grado o estudios", "requirement": "required",
        "category": "education", "blocker": status == "falta", "status": status,
        "reason": reason, "quote": quote,
    }


def baseline(job_id: str, profile: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Requisitos de la oferta con estado calculado por reglas contra el perfil real."""
    profile = profile if profile is not None else (cv_targets.load_profile() or {})
    job = cv_targets._job_context(job_id)
    if job is None:
        return []
    with connection() as conn:
        rows = conn.execute(
            """SELECT s.name, k.requirement_type, k.evidence, s.skill_type FROM job_skills k
               JOIN skills s ON s.id = k.skill_id WHERE k.job_id = %s""",
            (job_id,),
        ).fetchall()
    items: list[dict[str, Any]] = []
    for name, requirement, quote, skill_type in rows:
        if skill_type == "soft":
            continue  # Un certificado no demuestra una habilidad blanda: no es una brecha medible.
        strong, weak = _evidence(name, profile)
        if strong:
            status, reason = "cubierto", "; ".join(strong[:3])
        elif weak:
            status, reason = "parcial", "Sin certificado ni proyecto: " + "; ".join(weak[:3])
        else:
            status, reason = "falta", "No aparece en tu perfil"
        items.append({
            "key": _slug(name), "label": name, "requirement": requirement or "unknown",
            "category": "skill", "blocker": False, "status": status, "reason": reason,
            "quote": _clean_quote(quote),
        })
    description = job.get("description") or ""
    for extra in (_experience_item(description, profile), _education_item(description, profile)):
        if extra:
            items.append(extra)
    for item in items:
        item["source"] = "codigo"
    return items


def readiness(items: list[dict[str, Any]], description: str = "") -> dict[str, Any]:
    """Cercanía ponderada: cubierto suma 1, parcial 0.5. Los bloqueadores no se compensan con cursos.

    ``low_data`` avisa de que hay pocas señales (o una descripción muy corta) y el porcentaje no es
    fiable; la vista debe mostrar "datos insuficientes" en lugar de la cifra.
    """
    total = gained = 0.0
    for item in items:
        weight = _WEIGHT.get(item.get("requirement", "unknown"), 0.8)
        total += weight
        gained += weight * {"cubierto": 1.0, "parcial": 0.5}.get(item["status"], 0.0)
    return {
        "percent": round(100 * gained / total) if total else None,
        "covered": sum(i["status"] == "cubierto" for i in items),
        "partial": sum(i["status"] == "parcial" for i in items),
        "missing": sum(i["status"] == "falta" for i in items),
        "blockers": sum(1 for i in items if i.get("blocker") and i["status"] == "falta"),
        "low_data": len(items) < 3 or len(description) < 300,
    }


def selected_job_ids(limit: int = 50) -> list[str]:
    """Objetivos = ofertas activas marcadas con estrella."""
    with connection() as conn:
        rows = conn.execute(
            """SELECT f.job_id FROM job_user_favorites f JOIN jobs j ON j.id = f.job_id
               WHERE j.is_active = 1 ORDER BY f.created_at DESC LIMIT %s""",
            (max(1, min(limit, 100)),),
        ).fetchall()
    return [row[0] for row in rows]


def _km_from_home(location: str | None, profile: dict[str, Any]) -> float | None:
    home, place = infer_location(profile.get("home_district")), infer_location(location)
    if home and place and place.precision == "district":
        return cv_targets.distance_km(home, place)
    return None


def soft_skills(job_id: str) -> list[str]:
    """Habilidades blandas mencionadas por la oferta; se listan pero no puntúan."""
    with connection() as conn:
        rows = conn.execute(
            """SELECT s.name FROM job_skills k JOIN skills s ON s.id = k.skill_id
               WHERE k.job_id = %s AND s.skill_type = 'soft' ORDER BY s.name""",
            (job_id,),
        ).fetchall()
    return [row[0] for row in rows]


def combined_target(job_id: str, profile: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Oferta + brecha base + enriquecimiento opcional del agente, con la brecha base como autoridad."""
    profile = profile if profile is not None else (cv_targets.load_profile() or {})
    job = cv_targets._job_context(job_id)
    if job is None:
        return None
    items = baseline(job_id, profile)
    by_key = {item["key"]: item for item in items}
    enrichment = next((t for t in cv_targets.load_targets() if t.get("job_id") == job_id), None)
    sections: dict[str, list[dict[str, Any]]] = {}
    for name, entries in (enrichment or {}).get("sections", {}).items():
        sections[name] = []
        for entry in entries if isinstance(entries, list) else []:
            entry = dict(entry) if isinstance(entry, dict) else {}
            known = by_key.get(entry.get("key", ""))
            if known:
                entry.update(status=known["status"], status_source="codigo")
                entry["reason"] = known["reason"]
            elif entry.get("status"):
                entry["status_source"] = "agente"
            sections[name].append(entry)
    return {
        "id": job_id, "job_id": job_id, "title": job["title"], "company": job["company"],
        "location": {"job": job["location"], "home": profile.get("home_district"),
                     "km_from_home": _km_from_home(job["location"], profile)},
        "baseline": items, "soft_skills": soft_skills(job_id), "readiness": readiness(items, job.get("description") or ""),
        "has_enrichment": enrichment is not None, "hypothetical": True,
        "aviso": (enrichment or {}).get("aviso"),
        "sections": sections, "gaps": (enrichment or {}).get("gaps", []),
    }


def ranked_selection() -> list[dict[str, Any]]:
    """Todos los objetivos, del más al menos alcanzable, sin el cuerpo del candidato ideal."""
    profile = cv_targets.load_profile() or {}
    ranked = []
    for job_id in selected_job_ids():
        target = combined_target(job_id, profile)
        if target:
            ranked.append({k: target[k] for k in
                           ("id", "title", "company", "location", "readiness", "has_enrichment")})
    # Con datos suficientes primero, luego sin bloqueadores, luego por cercanía.
    ranked.sort(key=lambda t: (t["readiness"]["low_data"], t["readiness"]["blockers"],
                               -(t["readiness"]["percent"] or 0)))
    return ranked
