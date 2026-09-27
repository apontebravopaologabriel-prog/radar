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


def setup_status() -> dict[str, Any]:
    """Lista de pasos de configuración con su estado, para guiar la primera conversación."""
    from radar.agent.provider import load_config
    from radar.careers import active_pack

    profile = get_profile()
    skills = len((profile or {}).get("skills", {}))
    with connection() as conn:
        fresh = conn.execute(
            "SELECT count(*) FROM jobs WHERE is_active=1 AND duplicate_status='canonical' "
            "AND published_at IS NOT NULL AND date(published_at) >= date('now', '-14 days')"
        ).fetchone()[0]
        tracked = conn.execute("SELECT count(*) FROM applications").fetchone()[0]
    pack = active_pack()
    steps = [
        {"id": "career", "done": True, "detail": f"Carrera activa: {pack.name}",
         "next_action": "Cámbiala en Ajustes o con set_career_track si no es la tuya."},
        {"id": "profile", "done": profile is not None,
         "detail": "Sin perfil" if profile is None else f"Perfil de {profile['name']}",
         "next_action": "Pregunta nombre, formación, áreas, ubicaciones y modalidad; luego propón update_profile."},
        {"id": "skills", "done": skills > 0, "detail": f"{skills} skills declaradas",
         "next_action": "Pregunta qué skills domina y con qué nivel; solo lo que afirme; propón update_profile."},
        {"id": "market", "done": fresh > 0, "detail": f"{fresh} ofertas de los últimos 14 días",
         "next_action": "Explica (get_help actualizar) que el mercado se actualiza desde la PC."},
        {"id": "tracking", "done": tracked > 0, "detail": f"{tracked} ofertas en seguimiento",
         "next_action": "Muestra get_today_feed y ofrece guardar las que le interesen."},
        {"id": "ai", "done": load_config().ready, "detail": "Clave de IA configurada",
         "next_action": "Ya estás hablando con el agente."},
    ]
    pending = [s for s in steps if not s["done"]]
    return {"complete": not pending, "steps": steps, "next": pending[0] if pending else None}


def default_place() -> str | None:
    """Primer lugar del perfil que se resuelve a un distrito o ciudad conocidos."""
    from radar.geolocation import infer_location

    for place in (get_profile() or {}).get("locations", []):
        point = infer_location(place)
        if point and point.precision in ("district", "city") and point.label != "Lima":
            return point.label
    return None


def _open_jobs() -> list[dict[str, Any]]:
    return [
        row
        for row in list_jobs(limit=None, max_age_days=DEFAULT_MAX_AGE_DAYS)
        if row["relevance_tier"] != "out_of_focus"
    ]


def nearby(place: str, radius_km: float = 5.0, limit: int = 30) -> dict[str, Any]:
    """Ofertas a `radius_km` de un distrito o ciudad, de la más cercana a la más lejana.

    La distancia es entre centroides (distrito o ciudad). Las ofertas que solo indican el
    departamento se ubican en su capital y se marcan con precisión "department".
    """
    from radar.cv_targets import distance_km
    from radar.geolocation import infer_location

    origin = infer_location(place)
    if origin is None or origin.precision == "department" and origin.label == "Lima":
        raise ValueError(f"Lugar desconocido: {place}")
    radius_km = min(max(radius_km, 0.5), 2500.0)
    found: list[dict[str, Any]] = []
    for row in _open_jobs():
        point = infer_location(row["location"])
        if point is None:
            continue
        km = distance_km(origin, point)
        if km <= radius_km:
            found.append({
                "id": row["id"], "title": row["title"], "company": row["company"],
                "location": row["location"], "place": point.label, "precision": point.precision,
                "km": km, "url": row["url"], "published_at": row["published_at"],
                "work_mode": row["work_mode"], "area": row["primary_area"],
                "is_favorite": row["is_favorite"],
            })
    found.sort(key=lambda j: (j["km"], j["published_at"] or ""))
    # `precision` distingue un distrito real ("district") de una etiqueta genérica sin distrito preciso
    # ("city"/"department", p.ej. "Lima" cuando la oferta solo dice la ciudad): sin esto, "Lima" se veía
    # como un distrito más en la tabla, cuando en realidad es la bolsa de lo que no se pudo ubicar mejor.
    by_place: dict[str, dict[str, Any]] = {}
    for job in found:
        entry = by_place.setdefault(job["place"], {"place": job["place"], "count": 0, "precision": job["precision"]})
        entry["count"] += 1
    return {
        "origin": origin.label, "radius_km": radius_km, "total": len(found),
        "jobs": found[: min(max(limit, 1), 60)],
        "by_place": sorted(by_place.values(), key=lambda x: -x["count"]),
        "precision": "centroides de distrito o ciudad (aproximado)",
    }


def map_places() -> dict[str, Any]:
    """Ofertas agregadas por lugar para el mapa móvil: un punto por lugar, no uno por oferta."""
    from radar.geolocation import infer_location

    places: dict[str, dict[str, Any]] = {}
    unlocated = 0
    for row in _open_jobs():
        point = infer_location(row["location"])
        if point is None:
            unlocated += 1
            continue
        entry = places.setdefault(point.label, {
            "name": point.label, "latitude": point.latitude, "longitude": point.longitude,
            "precision": point.precision, "count": 0,
        })
        entry["count"] += 1
    ranked = sorted(places.values(), key=lambda e: -e["count"])
    return {"places": ranked, "total": sum(e["count"] for e in ranked), "unlocated": unlocated}
