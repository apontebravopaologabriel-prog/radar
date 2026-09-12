from __future__ import annotations

from typing import Any

from radar.db.database import connection
from radar.freshness import DEFAULT_MAX_AGE_DAYS


def list_jobs(
    limit: int = 20,
    seniority: str | None = None,
    area: str | None = None,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    search: str | None = None,
    work_mode: str | None = None,
    min_salary: float | None = None,
) -> list[dict[str, Any]]:
    clauses = [
        "j.is_active = TRUE",
        "j.published_at IS NOT NULL",
        "COALESCE(j.application_status, 'unknown') NOT IN ('closed', 'expired')",
        "NOT EXISTS (SELECT 1 FROM job_sources jsl JOIN sources sl ON sl.id=jsl.source_id WHERE jsl.job_id=j.id AND lower(sl.name)='linkedin' AND (COALESCE(j.application_status, 'unknown') <> 'open' OR j.application_checked_at IS NULL OR j.application_checked_at < CURRENT_DATE - (%s * INTERVAL '1 day')))",
        "j.published_at >= CURRENT_DATE - (%s * INTERVAL '1 day')",
        "j.published_at < CURRENT_DATE + INTERVAL '1 day'",
    ]
    params: list[Any] = [max_age_days, max_age_days]
    if seniority:
        clauses.append("j.seniority = %s")
        params.append(seniority)
    if area:
        clauses.append("ia.name = %s")
        params.append(area)
    if search:
        clauses.append("(j.title ILIKE %s OR c.name ILIKE %s OR j.description_clean ILIKE %s OR j.location ILIKE %s)")
        search_value = f"%{search}%"
        params.extend([search_value] * 4)
    if work_mode:
        clauses.append("j.work_mode = %s")
        params.append(work_mode)
    if min_salary is not None:
        clauses.append("COALESCE(j.salary_max, j.salary_min, 0) >= %s")
        params.append(min_salary)
    params.append(min(max(limit, 1), 100))
    sql = f"""SELECT j.id, j.title, c.name AS company, j.location, j.seniority,
        j.work_mode, j.salary_min, j.salary_max, j.salary_currency, js.source_url,
        j.published_at, ia.name AS primary_area, j.sector,
        j.hours_per_week, j.schedule_text, j.application_status, j.application_checked_at
        FROM jobs j LEFT JOIN companies c ON c.id=j.company_id
        LEFT JOIN job_areas ja ON ja.job_id=j.id AND ja.is_primary=TRUE
        LEFT JOIN industrial_areas ia ON ia.id=ja.area_id
        LEFT JOIN LATERAL (SELECT source_url FROM job_sources WHERE job_id=j.id ORDER BY last_seen_at DESC LIMIT 1) js ON TRUE
        WHERE {" AND ".join(clauses)} ORDER BY j.published_at DESC NULLS LAST, j.detected_at DESC LIMIT %s"""
    with connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(row) for row in rows]


def market_summary() -> dict[str, Any]:
    with connection() as conn:
        areas = conn.execute("""SELECT ia.name, count(*)::int AS job_count
            FROM job_areas ja JOIN industrial_areas ia ON ia.id=ja.area_id
            JOIN jobs j ON j.id=ja.job_id WHERE j.is_active AND ja.is_primary
            GROUP BY ia.name ORDER BY job_count DESC, ia.name""").fetchall()
        skills = conn.execute("""SELECT s.name, count(*)::int AS job_count
            FROM job_skills js JOIN skills s ON s.id=js.skill_id JOIN jobs j ON j.id=js.job_id
            WHERE j.is_active GROUP BY s.name ORDER BY job_count DESC, s.name LIMIT 30""").fetchall()
        total = conn.execute("SELECT count(*)::int FROM jobs WHERE is_active").fetchone()[0]
    return {
        "total_active_jobs": total,
        "by_area": [{"area": x[0], "job_count": x[1]} for x in areas],
        "top_skills": [{"skill": x[0], "job_count": x[1]} for x in skills],
    }


def get_profile() -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT id, name, education, target_roles, preferred_locations, preferred_work_modes FROM user_profile ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        skills = conn.execute(
            """SELECT s.name, us.level, us.evidence, us.interest
            FROM user_skills us JOIN skills s ON s.id=us.skill_id WHERE us.profile_id=%s ORDER BY s.name""",
            (row[0],),
        ).fetchall()
    return {
        "id": str(row[0]),
        "name": row[1],
        "education": row[2],
        "target_roles": row[3],
        "locations": row[4],
        "work_modes": row[5],
        "skills": {x[0]: x[1] for x in skills},
        "skill_details": [
            {"skill": x[0], "level": x[1], "evidence": x[2], "interest": x[3]} for x in skills
        ],
    }


def recommendations(
    limit: int = 10, max_age_days: int = DEFAULT_MAX_AGE_DAYS
) -> dict[str, Any]:
    profile = get_profile()
    if not profile:
        return {
            "profile_configured": False,
            "jobs": [],
            "message": "Configura user_profile y user_skills antes de pedir recomendaciones.",
        }
    with connection() as conn:
        rows = conn.execute(
            """SELECT j.id, j.title, c.name, j.location, jsu.source_url,
            j.published_at, j.work_mode, j.salary_min, j.salary_max, j.salary_currency,
            j.sector, j.hours_per_week, j.schedule_text,
            j.application_status, j.application_checked_at,
            js.total_score, js.strong_matches, js.missing_skills, js.reason
            FROM job_scores js JOIN jobs j ON j.id=js.job_id LEFT JOIN companies c ON c.id=j.company_id
            LEFT JOIN LATERAL (SELECT source_url FROM job_sources WHERE job_id=j.id ORDER BY last_seen_at DESC LIMIT 1) jsu ON TRUE
            WHERE js.profile_id=%s AND j.is_active
            AND COALESCE(j.application_status, 'unknown') NOT IN ('closed', 'expired')
            AND NOT EXISTS (SELECT 1 FROM job_sources jsl JOIN sources sl ON sl.id=jsl.source_id WHERE jsl.job_id=j.id AND lower(sl.name)='linkedin' AND (COALESCE(j.application_status, 'unknown') <> 'open' OR j.application_checked_at IS NULL OR j.application_checked_at < CURRENT_DATE - (%s * INTERVAL '1 day')))
            AND j.published_at IS NOT NULL
            AND j.published_at >= CURRENT_DATE - (%s * INTERVAL '1 day')
            AND j.published_at < CURRENT_DATE + INTERVAL '1 day'
            ORDER BY js.total_score DESC LIMIT %s""",
            (profile["id"], max_age_days, max_age_days, min(max(limit, 1), 50)),
        ).fetchall()
    return {
        "profile_configured": True,
        "jobs": [
            {
                "id": str(x[0]),
                "title": x[1],
                "company": x[2],
                "location": x[3],
                "url": x[4],
                "published_at": x[5].isoformat() if x[5] else None,
                "work_mode": x[6],
                "salary_min": float(x[7]) if x[7] is not None else None,
                "salary_max": float(x[8]) if x[8] is not None else None,
                "salary_currency": x[9],
                "sector": x[10],
                "hours_per_week": float(x[11]) if x[11] is not None else None,
                "schedule_text": x[12],
                "application_status": x[13],
                "application_checked_at": x[14].isoformat() if x[14] else None,
                "score": float(x[15]),
                "strong_matches": x[16],
                "missing_skills": x[17],
                "reason": x[18],
            }
            for x in rows
        ],
    }


def career_timeline(limit: int = 50) -> list[dict[str, Any]]:
    """Devuelve eventos profesionales y versiones del perfil sin perder historia."""
    with connection() as conn:
        rows = conn.execute(
            """SELECT 'career_event' AS kind, id, event_type AS subtype, title,
            description, started_on, created_at FROM career_events
            UNION ALL
            SELECT 'profile_version', id, 'profile_update',
            'Perfil actualizado a v' || version_number, change_reason,
            NULL, created_at FROM profile_versions
            ORDER BY created_at DESC LIMIT %s""",
            (min(max(limit, 1), 200),),
        ).fetchall()
    return [{"kind": x[0], "id": str(x[1]), "subtype": x[2], "title": x[3],
             "description": x[4], "date": (x[5] or x[6]).isoformat() if (x[5] or x[6]) else None}
            for x in rows]


def job_history(job_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Muestra cómo cambió una oferta y cuándo fue observada."""
    with connection() as conn:
        rows = conn.execute(
            """SELECT observed_at, content_hash, is_active, snapshot
            FROM job_observations WHERE job_id=%s ORDER BY observed_at DESC LIMIT %s""",
            (job_id, min(max(limit, 1), 100)),
        ).fetchall()
    return [{"observed_at": x[0].isoformat(), "content_hash": x[1],
             "is_active": x[2], "snapshot": x[3]} for x in rows]


def market_history(limit: int = 90) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """SELECT snapshot_date, metric_name, dimensions, metric_value
            FROM market_snapshots ORDER BY snapshot_date DESC, metric_name LIMIT %s""",
            (min(max(limit, 1), 500),),
        ).fetchall()
    return [{"date": x[0].isoformat(), "metric": x[1], "dimensions": x[2], "value": float(x[3])} for x in rows]


def applications(limit: int = 50) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """SELECT a.id, a.job_id, j.title, c.name, a.status, a.notes, a.applied_at, a.updated_at,
            js.source_url FROM applications a JOIN jobs j ON j.id=a.job_id
            LEFT JOIN companies c ON c.id=j.company_id
            LEFT JOIN LATERAL (SELECT source_url FROM job_sources WHERE job_id=j.id ORDER BY last_seen_at DESC LIMIT 1) js ON TRUE
            ORDER BY a.updated_at DESC LIMIT %s""",
            (min(max(limit, 1), 200),),
        ).fetchall()
    return [{"id": str(x[0]), "job_id": str(x[1]), "title": x[2], "company": x[3],
             "status": x[4], "notes": x[5], "applied_at": x[6].isoformat() if x[6] else None,
             "updated_at": x[7].isoformat(), "url": x[8]} for x in rows]


def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    keys = (
        "id",
        "title",
        "company",
        "location",
        "seniority",
        "work_mode",
        "salary_min",
        "salary_max",
        "salary_currency",
        "url",
        "published_at",
        "primary_area",
        "sector",
        "hours_per_week",
        "schedule_text",
        "application_status",
        "application_checked_at",
    )
    result = dict(zip(keys, row, strict=True))
    result["id"] = str(result["id"])
    for key in ("salary_min", "salary_max"):
        if result[key] is not None:
            result[key] = float(result[key])
    if result["published_at"] is not None:
        result["published_at"] = result["published_at"].isoformat()
    return result
