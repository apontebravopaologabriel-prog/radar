"""Consultas de solo lectura para responder preguntas abiertas sobre el mercado y las ofertas.

Todo se calcula por código sobre SQLite; el agente y el MCP solo lo leen y lo explican.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from typing import Any

from radar.careers import WEIGHT_KEYS, effective_weights
from radar.db.analytics import QueryError, QueryTimeout, describe_schema, run_readonly_query
from radar.db.database import connection
from radar.db.queries import get_profile, list_jobs, skill_overview
from radar.feed import skill_impact
from radar.freshness import DEFAULT_MAX_AGE_DAYS
from radar.geolocation import infer_location

BREAKDOWNS = ("area", "place", "company", "work_mode", "seniority", "source")
DESCRIPTION_LIMIT = 3000


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else (value or [])


def job_details(job_id: str) -> dict[str, Any]:
    """Ficha completa de una oferta: datos, skills exigidas, puntaje personal y seguimiento."""
    with connection() as conn:
        row = conn.execute(
            """SELECT j.id, j.title, c.name, j.location, j.seniority, j.work_mode, j.employment_type,
            j.salary_min, j.salary_max, j.salary_currency, j.salary_period, j.published_at, j.sector,
            j.hours_per_week, j.schedule_text, j.application_status, j.relevance_tier,
            COALESCE(j.description_clean, j.description_raw),
            (SELECT ia.name FROM job_areas ja JOIN industrial_areas ia ON ia.id=ja.area_id
             WHERE ja.job_id=j.id AND ja.is_primary=1),
            (SELECT source_url FROM job_sources js WHERE js.job_id=j.id ORDER BY js.last_seen_at DESC LIMIT 1),
            EXISTS(SELECT 1 FROM job_user_favorites f WHERE f.job_id=j.id)
            FROM jobs j LEFT JOIN companies c ON c.id=j.company_id WHERE j.id=%s""",
            (job_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Oferta no encontrada: {job_id}")
        skills = conn.execute(
            "SELECT s.name, js.requirement_type FROM job_skills js JOIN skills s ON s.id=js.skill_id WHERE js.job_id=%s ORDER BY s.name",
            (job_id,),
        ).fetchall()
        application = conn.execute("SELECT status, notes FROM applications WHERE job_id=%s", (job_id,)).fetchone()
    profile = get_profile()
    fit = _fit(job_id, profile["id"]) if profile else None
    place = infer_location(row[3])
    return {
        "id": row[0], "title": row[1], "company": row[2], "location": row[3],
        "place": place.label if place else None, "seniority": row[4], "work_mode": row[5],
        "employment_type": row[6], "salary": {"min": row[7], "max": row[8], "currency": row[9], "period": row[10]},
        "published_at": str(row[11]) if row[11] else None, "sector": row[12],
        "hours_per_week": row[13], "schedule": row[14], "application_status": row[15],
        "relevance": row[16], "area": row[18], "url": row[19], "is_favorite": bool(row[20]),
        "skills": [{"name": s[0], "requirement": s[1]} for s in skills],
        "description": (row[17] or "")[:DESCRIPTION_LIMIT],
        "your_tracking": {"status": application[0], "notes": application[1]} if application else None,
        "fit": fit,
    }


def _fit(job_id: str, profile_id: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(
            """SELECT total_score, area_score, skills_score, seniority_score, education_score,
            location_score, preference_score, strong_matches, missing_skills, reason
            FROM job_scores WHERE job_id=%s AND profile_id=%s""",
            (job_id, profile_id),
        ).fetchone()
    if row is None:
        return None
    weights = effective_weights()
    parts = dict(zip(WEIGHT_KEYS, row[1:7], strict=True))
    return {
        "total": round(row[0], 1),
        "dimensions": [
            {"name": k, "score": round(v, 1), "weight": round(weights[k], 3), "contribution": round(v * weights[k], 1)}
            for k, v in parts.items()
        ],
        "strong_matches": _json(row[7]), "missing_skills": _json(row[8]), "reason": row[9],
    }


def explain_fit(job_id: str) -> dict[str, Any]:
    """Desglose del puntaje de encaje de una oferta: qué dimensión aporta cuánto y por qué."""
    profile = get_profile()
    if not profile:
        raise ValueError("Configura tu perfil para calcular el encaje.")
    fit = _fit(job_id, profile["id"])
    if fit is None:
        raise ValueError("Esa oferta no tiene puntaje calculado para tu perfil.")
    return {"job_id": job_id, **fit}


def compare(job_ids: list[str]) -> dict[str, Any]:
    if not 2 <= len(job_ids) <= 4:
        raise ValueError("Compara entre 2 y 4 ofertas.")
    jobs = [job_details(j) for j in job_ids]
    skill_sets = [{s["name"] for s in j["skills"]} for j in jobs]
    rows = []
    for index, job in enumerate(jobs):
        others = set().union(*(s for i, s in enumerate(skill_sets) if i != index))
        rows.append({
            **{k: job[k] for k in ("id", "title", "company", "place", "seniority", "work_mode", "salary", "area", "url")},
            "fit_total": (job["fit"] or {}).get("total"),
            "missing_skills": (job["fit"] or {}).get("missing_skills", []),
            "only_here": sorted(skill_sets[index] - others),
        })
    return {"jobs": rows, "common_skills": sorted(set.intersection(*skill_sets))}


def skill_demand(area: str | None = None, max_age_days: int = 30, limit: int = 15) -> dict[str, Any]:
    data = skill_overview(max_age_days=max_age_days, area=area)
    rows = [
        {"skill": s["name"], "type": s["skill_type"], "jobs": s["job_count"], "required_in": s["required_count"],
         "share_pct": round(s["share"] * 100, 1), "your_level": s["user_level"]}
        for s in data["skills"][: min(max(limit, 1), 40)]
    ]
    return {"total_jobs": data["total_jobs"], "max_age_days": max_age_days, "area": area, "skills": rows}


def market_breakdown(by: str, max_age_days: int = DEFAULT_MAX_AGE_DAYS, limit: int = 10) -> dict[str, Any]:
    """Cuenta ofertas vigentes agrupadas por área, lugar, empresa, modalidad, nivel o portal."""
    if by not in BREAKDOWNS:
        raise ValueError(f"`by` debe ser uno de {', '.join(BREAKDOWNS)}")
    counter: Counter[str] = Counter()
    if by == "source":
        with connection() as conn:
            rows = conn.execute(
                """SELECT s.name, count(DISTINCT j.id) FROM jobs j JOIN job_sources js ON js.job_id=j.id
                JOIN sources s ON s.id=js.source_id
                WHERE j.is_active=1 AND j.duplicate_status='canonical' AND j.published_at IS NOT NULL
                AND date(j.published_at) >= date('now', '-' || %s || ' days') GROUP BY s.name""",
                (max_age_days,),
            ).fetchall()
        counter.update({r[0]: r[1] for r in rows})
        total = sum(counter.values())
    else:
        jobs = list_jobs(limit=None, max_age_days=max_age_days)
        total = len(jobs)
        for job in jobs:
            if by == "place":
                point = infer_location(job["location"])
                key = point.label if point else None
            else:
                key = {"area": job["primary_area"], "company": job["company"],
                       "work_mode": job["work_mode"], "seniority": job["seniority"]}[by]
            counter[key or "sin dato"] += 1
    return {"by": by, "max_age_days": max_age_days, "total": total,
            "rows": [{"value": k, "jobs": n} for k, n in counter.most_common(min(max(limit, 1), 30))]}


def salary_stats(area: str | None = None, place: str | None = None, max_age_days: int = 60) -> dict[str, Any]:
    """Salarios declarados (no todas las ofertas los publican). Se resume por moneda y periodo."""
    groups: dict[tuple[str, str], list[float]] = {}
    considered = 0
    for job in list_jobs(limit=None, max_age_days=max_age_days, area=area):
        considered += 1
        if place:
            point = infer_location(job["location"])
            if not point or point.label.lower() != place.lower():
                continue
        low, high = job["salary_min"], job["salary_max"]
        if low is None and high is None:
            continue
        mid = (low + high) / 2 if low is not None and high is not None else (low if low is not None else high)
        groups.setdefault((job["salary_currency"] or "?", "mensual"), []).append(mid)
    return {
        "jobs_considered": considered, "area": area, "place": place,
        "note": "Solo ofertas que publican salario; suele ser una minoría.",
        "groups": [
            {"currency": c, "period": p, "count": len(v), "min": round(min(v)), "median": round(statistics.median(v)),
             "max": round(max(v))}
            for (c, p), v in sorted(groups.items())
        ],
    }


def learning_plan(limit: int = 5) -> dict[str, Any]:
    """Skills que conviene aprender: impacto en tu encaje combinado con la demanda del mercado."""
    impact = skill_impact(30)
    if not impact.get("profile_configured"):
        return {"profile_configured": False, "skills": []}
    demand = {s["skill"]: s for s in skill_demand(limit=40)["skills"]}
    ranked = []
    for item in impact["skills"][: min(max(limit, 1), 10)]:
        d = demand.get(item["skill"], {})
        ranked.append({**item, "market_share_pct": d.get("share_pct"), "required_in": d.get("required_in")})
    return {"profile_configured": True, "skills": ranked, "threshold": impact["threshold"]}


def readonly_sql(sql: str, max_rows: int = 50) -> dict[str, Any]:
    """SQL de solo lectura (SELECT/WITH) con tope de filas y tiempo. Usa get_data_schema antes."""
    try:
        return run_readonly_query(sql, max_rows=min(max_rows, 50))
    except (QueryError, QueryTimeout) as exc:
        raise ValueError(str(exc)) from exc


def data_schema() -> dict[str, Any]:
    return describe_schema()
