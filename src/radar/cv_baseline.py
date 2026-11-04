"""Brecha base determinista entre una oferta y el perfil real, sin LLM.

Cruza las skills que Radar ya detectó en la oferta (``job_skills``), los años de experiencia y el
nivel de estudios pedidos en la descripción contra ``cv_master.json``. Cada resultado conserva su
evidencia. Las ofertas marcadas con estrella (favoritos) son los objetivos. El agente puede
enriquecer un objetivo con un candidato ideal, pero el estado de lo que el código ya calculó no se
lo puede reasignar el agente. Ver ``docs/cv.md``.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, date, datetime
from typing import Any

from radar import careers, cv_targets, insights
from radar.db.database import connection
from radar.db.queries import get_profile
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


def _terms(name: str) -> list[str]:
    """Formas en que puede aparecer una skill en el CV: los alias de la carrera activa (los mismos con los
    que se detectó en la oferta) más los propios de este módulo. Así ambos lados hablan el mismo vocabulario."""
    key = _norm(name)
    terms = set(_ALIASES.get(key, [key]))
    try:
        for skill in careers.active_pack().skills.values():
            if _norm(skill.name) == key:
                terms.update(_norm(alias) for alias in skill.aliases)
    except careers.CareerPackError:
        pass  # sin pack legible se usan solo los alias locales
    return sorted(terms, key=len, reverse=True)


def _evidence(name: str, profile: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Evidencia fuerte (certificados, experiencia) y débil (aptitudes de estudios, autodeclaración)."""
    terms = _terms(name)
    strong: list[str] = []
    weak: list[str] = []
    for cert in profile.get("certifications", []):
        if any(_contains(cert.get("name", ""), t) for t in terms):
            strong.append(f"certificado: {cert['name']}")
    for job in profile.get("experience", []):
        haystack = " ".join([*job.get("bullets", []), *job.get("skills", [])])
        if any(_contains(haystack, t) for t in terms):
            months = _months(job.get("from"), job.get("to"))
            span = f" (~{months} {'mes' if months == 1 else 'meses'})" if months else ""
            strong.append(f"experiencia: {job.get('role')} en {job.get('company')}{span}")
    for project in profile.get("projects", []):
        haystack = " ".join([project.get("name") or "", project.get("description") or "", *project.get("skills", [])])
        if any(_contains(haystack, t) for t in terms):
            strong.append(f"proyecto: {project.get('name')}")
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


def _requirement_item(value: dict, key: str, label: str, category: str) -> dict | None:
    if not value["quote"]:
        return None
    return {"key": key, "label": label, "category": category,
            "requirement": "required" if value["required"] else "preferred",
            "blocker": value["required"] and value["status"] == "missing",
            "status": {"met": "cubierto", "missing": "falta"}.get(value["status"], "parcial"),
            "uncertain": value["status"] == "unknown", "reason": value["reason"], "quote": value["quote"]}


def _experience_item(description: str, profile: dict[str, Any], skill_names: list[str] | None = None) -> dict[str, Any] | None:
    from radar.requirements import experience_assessment

    return _requirement_item(experience_assessment(description, profile, skill_names or []),
                             "experiencia-previa", "Experiencia previa", "experience")


def _education_item(description: str, profile: dict[str, Any]) -> dict[str, Any] | None:
    from radar.requirements import education_assessment

    return _requirement_item(education_assessment(description, profile), "formacion", "Grado o estudios", "education")


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
        from radar.requirements import skill_level
        from radar.scoring import LEVELS

        needed, level_quote, _ = skill_level(job.get("description") or "", name, _terms(name))
        declared = (profile.get("tools_declared_in_db") or {}).get(name)
        if needed and (declared not in LEVELS or LEVELS[declared] < LEVELS[needed]):
            status = "parcial"
            reason = f"Nivel solicitado: {needed}; nivel declarado: {declared or 'sin especificar'}. La evidencia no certifica ese nivel."
        items.append({
            "key": _slug(name), "label": name, "requirement": requirement or "unknown",
            "category": "skill", "blocker": False, "status": status, "reason": reason,
            "quote": _clean_quote(level_quote or quote),
        })
    description = job.get("description") or ""
    skill_names = [row[0] for row in rows if row[3] != "soft"]
    for extra in (_experience_item(description, profile, skill_names), _education_item(description, profile)):
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
        gained += weight * (0 if item.get("uncertain") else {"cubierto": 1.0, "parcial": 0.5}.get(item["status"], 0.0))
    return {
        "percent": round(100 * gained / total) if total else None,
        "covered": sum(i["status"] == "cubierto" for i in items),
        "partial": sum(i["status"] == "parcial" for i in items),
        "missing": sum(i["status"] == "falta" for i in items),
        "blockers": sum(1 for i in items if i.get("blocker") and i["status"] == "falta"),
        "low_data": sum(not i.get("uncertain") for i in items) < 3 or len(description) < 300,
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


def _fit_total(job_id: str, profile_id: str | None) -> float | None:
    """Encaje de la oferta con tus preferencias (el puntaje del mapa), o ``None`` si no hay perfil."""
    if profile_id is None:
        return None
    fit = insights._fit(job_id, profile_id)
    return fit["total"] if fit and not fit.get("stale") else None


def read_of(fit: float | None, percent: int | None, low_data: bool) -> str | None:
    """Frase que reconcilia las dos cifras: encaje (preferencias) y cercanía (evidencia en tu CV)."""
    if fit is None or percent is None or low_data:
        return None
    if fit >= 60 and percent < 50:
        return "Encaja con lo que buscas, pero te falta evidencia: buen candidato para cerrar brechas."
    if fit < 45 and percent >= 60:
        return "Tu CV aporta evidencia, aunque la coincidencia respaldada es baja."
    if fit >= 60 and percent >= 60:
        return "La oferta tiene coincidencias y evidencia en tu CV; revisa los requisitos pendientes antes de postular."
    return None


def ranked_selection() -> list[dict[str, Any]]:
    """Todos los objetivos, del más al menos alcanzable, sin el cuerpo del candidato ideal."""
    profile = cv_targets.load_profile() or {}
    account = get_profile()
    profile_id = account["id"] if account else None
    ranked = []
    for job_id in selected_job_ids():
        target = combined_target(job_id, profile)
        if target:
            item = {k: target[k] for k in ("id", "title", "company", "location", "readiness", "has_enrichment")}
            fit = insights._fit(job_id, profile_id) if profile_id else None
            evidence = fit.get("assessment", {}) if fit and not fit.get("stale") else {}
            item["fit_total"] = fit["total"] if evidence else None
            item["fit_coverage"] = evidence.get("coverage")
            item["fit_upper_bound"] = evidence.get("upper_bound")
            readiness_ = item["readiness"]
            item["read"] = read_of(item["fit_total"], readiness_["percent"], readiness_["low_data"])
            if (item["fit_coverage"] or 0) < 60:
                item["read"] = "Datos insuficientes para estimar el encaje con confianza."
            ranked.append(item)
    # Con datos suficientes primero, luego sin bloqueadores, luego por cercanía.
    ranked.sort(key=lambda t: (t["readiness"]["low_data"], t["readiness"]["blockers"],
                               -(t["readiness"]["percent"] or 0)))
    return ranked
