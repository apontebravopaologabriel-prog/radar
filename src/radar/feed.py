"""Feed "Hoy" y simulador de impacto de skills: consultas deterministas sobre el score guardado."""

from __future__ import annotations

from typing import Any

from radar.careers import effective_weights
from radar.db.database import connection
from radar.db.queries import get_profile, list_jobs, recommendations
from radar.freshness import DEFAULT_MAX_AGE_DAYS

HIGH_FIT = 70.0


def _excluded_job_ids() -> set[str]:
    """Ofertas ocultas o que el usuario ya movió en su seguimiento (postuladas, descartadas...)."""
    with connection() as conn:
        hidden = conn.execute("SELECT job_id FROM job_user_status WHERE status='hidden'").fetchall()
        tracked = conn.execute(
            "SELECT job_id FROM applications WHERE status IN ('applied','interview','offer','rejected','ignored','expired')"
        ).fetchall()
    return {r[0] for r in hidden} | {r[0] for r in tracked}


def _favorite_ids() -> set[str]:
    with connection() as conn:
        return {r[0] for r in conn.execute("SELECT job_id FROM job_user_favorites").fetchall()}


def _why(job: dict[str, Any]) -> str:
    strong = job.get("strong_matches") or []
    missing = job.get("missing_skills") or []
    parts = []
    if strong:
        parts.append("Coincide en " + ", ".join(strong[:3]))
    if missing:
        parts.append("te falta " + ", ".join(missing[:2]))
    return " · ".join(parts) or job.get("reason") or "Sin señales suficientes"


def today_feed(limit: int = 5, max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> dict[str, Any]:
    """Pocas ofertas frescas que encajan, con el motivo en una línea y sin las ya gestionadas."""
    limit = min(max(limit, 1), 20)
    excluded = _excluded_job_ids()
    favorites = _favorite_ids()
    rec = recommendations(50, max_age_days)
    if rec.get("profile_configured"):
        picks = [j for j in rec["jobs"] if j["id"] not in excluded][:limit]
        for job in picks:
            job["why"] = _why(job)
            job["is_favorite"] = job["id"] in favorites
        return {"profile_configured": True, "jobs": picks}
    # Sin perfil no hay score: se muestran las más recientes del foco de la carrera.
    rows = [
        r
        for r in list_jobs(limit=50, max_age_days=max_age_days, relevance_tier="core")
        if r["id"] not in excluded
    ][:limit]
    jobs = [
        {
            "id": r["id"],
            "title": r["title"],
            "company": r.get("company"),
            "location": r.get("location"),
            "url": r.get("url"),
            "published_at": r.get("published_at"),
            "work_mode": r.get("work_mode"),
            "score": None,
            "strong_matches": [],
            "missing_skills": [],
            "why": "Configura tu perfil para ver por qué encaja",
            "is_favorite": r["id"] in favorites,
        }
        for r in rows
    ]
    return {"profile_configured": False, "jobs": jobs}


def skill_impact(limit: int = 8, max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> dict[str, Any]:
    """Qué skill faltante sube más el encaje si la aprendes (nivel básico).

    Aprender una skill mueve un requisito de "falta" a "coincide"; el efecto en el score de una
    oferta con `n` skills es `peso_skills * 100 / n`. Es una simulación, no una promesa.
    """
    profile = get_profile()
    if not profile:
        return {"profile_configured": False, "skills": []}
    weight = effective_weights()["skills"]
    jobs = recommendations(50, max_age_days)["jobs"]
    impact: dict[str, dict[str, Any]] = {}
    for job in jobs:
        strong, missing = job["strong_matches"], job["missing_skills"]
        total_skills = len(strong) + len(missing)
        if not total_skills:
            continue
        gain = round(weight * 100 / total_skills, 2)
        for skill in missing:
            entry = impact.setdefault(skill, {"skill": skill, "jobs": 0, "total_gain": 0.0, "crossing": 0})
            entry["jobs"] += 1
            entry["total_gain"] += gain
            if job["score"] < HIGH_FIT <= job["score"] + gain:
                entry["crossing"] += 1
    ranked = sorted(impact.values(), key=lambda e: (-e["crossing"], -e["total_gain"], e["skill"]))
    for entry in ranked:
        entry["avg_gain"] = round(entry["total_gain"] / entry["jobs"], 1)
        entry["total_gain"] = round(entry["total_gain"], 1)
    return {
        "profile_configured": True,
        "threshold": HIGH_FIT,
        "jobs_considered": len(jobs),
        "skills": ranked[: min(max(limit, 1), 30)],
    }
