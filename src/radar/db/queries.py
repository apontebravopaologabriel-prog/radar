from __future__ import annotations

import json
from typing import Any

from radar.db.database import connection
from radar.freshness import DEFAULT_MAX_AGE_DAYS, PERU_UTC_OFFSET_HOURS, visible_date_bounds

# Date-only and zone-less publications retain their calendar day. For zoned timestamps,
# drop fractional seconds before conversion to avoid rounding across midnight in SQLite.
_VISIBLE_PUBLICATION_WINDOW = f"""(CASE
    WHEN substr(j.published_at, -6) GLOB '[+-][0-9][0-9]:[0-9][0-9]'
        THEN date(substr(j.published_at, 1, min(length(j.published_at) - 6, 19)) || substr(j.published_at, -6),
                  '{PERU_UTC_OFFSET_HOURS} hours')
    WHEN upper(substr(j.published_at, -1)) = 'Z'
        THEN date(substr(j.published_at, 1, min(length(j.published_at) - 1, 19)), '{PERU_UTC_OFFSET_HOURS} hours')
    ELSE date(substr(j.published_at, 1, 19))
    END) BETWEEN %s AND date(%s, '-1 day')"""


def list_jobs(
    limit: int | None = 20,
    seniority: str | None = None,
    area: str | None = None,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    search: str | None = None,
    work_mode: str | None = None,
    min_salary: float | None = None,
    max_salary: float | None = None,
    include_hidden: bool = False,
    include_applied: bool = True,
    source: str | None = None,
    skill: str | None = None,
    relevance_tier: str | None = None,
    market_id: str | None = None,
    geo_scope: str | None = None,
    profile_mode: str = "market",
    sector: str | None = None,
    exclude_sectors: list[str] | None = None,
) -> list[dict[str, Any]]:
    from radar.query_context import CURRENT_QUERY

    scope = CURRENT_QUERY.get()
    place = scope.values().get("place") if scope else None
    near = scope.values().get("near") if scope else None
    requested_limit = limit
    if place or near or geo_scope:
        limit = None
    if scope:
        values = scope.values()
        geo_scope = values.get("geo_scope", geo_scope)
        market_id = values.get("market_id", market_id)
        max_age_days = values.get("max_age_days", max_age_days)
        area = values.get("area", area) or None
        seniority = values.get("seniority", seniority) or None
        work_mode = values.get("work_mode", work_mode) or None
        min_salary = values.get("min_salary", min_salary)
        min_salary = None if min_salary == "" else min_salary
        max_salary = values.get("max_salary", max_salary)
        max_salary = None if max_salary == "" else max_salary
        source = values.get("source", source) or None
        skill = values.get("skill", skill) or None
        search = values.get("search", search) or None
        relevance_tier = values.get("relevance_tier", relevance_tier) or None
        profile_mode = values.get("profile_mode", profile_mode)
        include_applied = values.get("include_applied", include_applied)
        include_hidden = values.get("include_hidden", include_hidden)
    if geo_scope not in {None, "", "lima_callao"}:
        raise ValueError("Ámbito geográfico inválido")
    if geo_scope:
        limit = None
    if market_id:
        from radar.markets import backfill_market

        backfill_market(market_id)
    relevance = "m" if market_id else "j"
    tier_col = "+m.relevance_tier" if market_id else "j.relevance_tier"
    area_column = "json_extract(m.areas, '$[0].name')" if market_id else "ia.name"
    market_join = (
        "JOIN job_market_classifications m ON m.job_id=j.id AND m.market_id=%s"
        if market_id
        else "LEFT JOIN job_areas ja ON ja.job_id=j.id AND ja.is_primary=1 LEFT JOIN industrial_areas ia ON ia.id=ja.area_id"
    )
    clauses = [
        "j.is_active = 1",
        "COALESCE(j.application_status, 'unknown') NOT IN ('closed', 'expired')",
        "j.duplicate_status = 'canonical'",
        "j.published_at IS NOT NULL",
        _VISIBLE_PUBLICATION_WINDOW,
    ]
    start, end = visible_date_bounds(max_age_days)
    params: list[Any] = [market_id, start, end] if market_id else [start, end]
    if profile_mode not in {"market", "saved"}:
        raise ValueError("Perfil de búsqueda inválido")
    if profile_mode == "saved":
        if not market_id:
            raise ValueError("El perfil necesita un mercado")
        from radar.markets import search_profile
        from radar.normalize import normalize_text

        preferences = search_profile(market_id)["preferences"]
        if not preferences:
            clauses.append("0=1")
        for key, column in (("areas", area_column), ("seniority", "j.seniority"), ("work_modes", "j.work_mode")):
            values = preferences.get(key, [])
            if values:
                clauses.append(f"{column} IN ({','.join('%s' for _ in values)})")
                params.extend(values)
        for key, column in (("roles", "j.title_normalized"), ("locations", "j.location_normalized")):
            values = [normalize_text(value) for value in preferences.get(key, []) if value.strip()]
            if values:
                clauses.append("(" + " OR ".join(f"instr(COALESCE({column},''),%s)>0" for _ in values) + ")")
                params.extend(values)
        for value in preferences.get("excluded_titles", []):
            if value.strip():
                clauses.append("instr(j.title_normalized,%s)=0")
                params.append(normalize_text(value))
    if seniority:
        if seniority == "senior":
            clauses.append("j.seniority IN ('senior', 'senior_or_lead')")
        elif seniority == "intern":
            clauses.append("j.seniority IN ('intern', 'trainee')")
        else:
            clauses.append("j.seniority = %s")
            params.append(seniority)
    if area:
        clauses.append(f"{area_column} = %s")
        params.append(area)
    if search:
        clauses.append("(j.title LIKE %s OR c.name LIKE %s OR j.description_clean LIKE %s OR j.location LIKE %s)")
        search_value = f"%{search}%"
        params.extend([search_value] * 4)
    if work_mode:
        clauses.append("j.work_mode = %s")
        params.append(work_mode)
    if sector:
        clauses.append("j.sector = %s")
        params.append(sector)
    if exclude_sectors:
        clauses.append(f"COALESCE(j.sector, '') NOT IN ({','.join(['%s'] * len(exclude_sectors))})")
        params.extend(exclude_sectors)
    if min_salary is not None and min_salary < 0 or max_salary is not None and max_salary < 0:
        raise ValueError("El sueldo debe ser positivo")
    if min_salary is not None and max_salary is not None and min_salary > max_salary:
        raise ValueError("El mínimo no puede superar el máximo")
    if max_salary is not None:
        clauses.append("COALESCE(j.salary_min, j.salary_max) <= %s")
        params.append(max_salary)
    if min_salary is not None:
        clauses.append("COALESCE(j.salary_max, j.salary_min) >= %s")
        params.append(min_salary)
    if source:
        clauses.append(
            "EXISTS (SELECT 1 FROM job_sources jsource JOIN sources src ON src.id=jsource.source_id "
            "WHERE jsource.job_id=j.id AND (lower(src.name) LIKE lower(%s) OR lower(jsource.source_url) LIKE lower(%s)))"
        )
        params.extend([f"%{source}%", f"%{source}%"])
    if skill:
        clauses.append("EXISTS (SELECT 1 FROM json_each(m.skills) ms WHERE json_extract(ms.value, '$.name')=%s)"
                       if market_id else "EXISTS (SELECT 1 FROM job_skills jskill JOIN skills skill ON skill.id=jskill.skill_id WHERE jskill.job_id=j.id AND skill.name=%s)")
        params.append(skill)
    if relevance_tier == "market":
        clauses.append(f"{tier_col} IN ('core', 'adjacent')")
    elif relevance_tier == "target":  # cargos objetivo del paquete (prioridad 1 y 2)
        clauses.append(f"{tier_col} = 'core' AND {relevance}.relevance_evidence LIKE 'Cargo objetivo%'")
    elif relevance_tier:
        if relevance_tier not in {"core", "adjacent", "out_of_focus"}:
            raise ValueError("relevance_tier inválido")
        clauses.append(f"{tier_col} = %s")
        params.append(relevance_tier)
    if not include_hidden:
        clauses.append("NOT EXISTS (SELECT 1 FROM job_user_status jus WHERE jus.job_id=j.id AND jus.status='hidden')")
    if not include_applied:
        clauses.append(
            "NOT EXISTS (SELECT 1 FROM applications a WHERE a.job_id=j.id AND a.status IN ('applied','interview','offer','rejected')) AND NOT EXISTS (SELECT 1 FROM processes p WHERE p.job_id=j.id)"
        )
    limit_clause = ""
    if limit is not None:
        params.append(max(limit, 1))
        limit_clause = " LIMIT %s"
    sql = f"""SELECT j.id, j.title, c.name AS company, j.location, j.seniority,
        j.work_mode, j.salary_min, j.salary_max, j.salary_currency,
        (SELECT source_url FROM job_sources js WHERE js.job_id=j.id ORDER BY js.last_seen_at DESC LIMIT 1) AS source_url,
        j.published_at, {area_column} AS primary_area, j.sector, {relevance}.relevance_tier, {relevance}.relevance_score,
        {relevance}.relevance_evidence, j.description_clean,
        j.hours_per_week, j.schedule_text, j.application_status, j.application_checked_at,
        COALESCE(jus.status, 'visible') AS user_status, jus.reason AS user_reason,
        EXISTS (SELECT 1 FROM job_user_favorites juf WHERE juf.job_id=j.id) AS is_favorite,
        (SELECT a.status FROM applications a WHERE a.job_id=j.id) AS user_application
        FROM jobs j {market_join} LEFT JOIN companies c ON c.id=j.company_id
        LEFT JOIN job_user_status jus ON jus.job_id=j.id
        WHERE {" AND ".join(clauses)} ORDER BY j.published_at DESC NULLS LAST, j.detected_at DESC{limit_clause}"""
    with connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    result = [_row_to_dict(row) for row in rows]
    if geo_scope == "lima_callao":
        from radar.geolocation import in_lima_metro

        result = [j for j in result if in_lima_metro(j.get("location"), j.get("title"), j.get("description"))]
    if place or near:
        from radar.geolocation import infer_job_location, infer_location

        target = infer_location(near or place)
        if target is None:
            return []
        def matches(job):
            point = infer_job_location(job.get("location"), job.get("title"), job.get("description"))
            if near:
                from radar.cv_targets import distance_km

                radius = float(scope.values().get("radius_km", 5))
                return point and distance_km(target, point) <= radius
            return point and (point.label == target.label or
                             (target.label == "Lima" and point.precision == "district"))
        result = [job for job in result if matches(job)]
        if requested_limit is not None:
            result = result[:max(requested_limit, 1)]
    return result[:max(requested_limit, 1)] if geo_scope and requested_limit is not None else result


def list_hidden_jobs() -> list[dict[str, Any]]:
    """Devuelve ofertas ocultadas por el usuario para poder restaurarlas."""
    sql = """SELECT j.id, j.title, c.name AS company, j.location, j.seniority,
        j.work_mode, j.salary_min, j.salary_max, j.salary_currency,
        (SELECT source_url FROM job_sources js WHERE js.job_id=j.id ORDER BY js.last_seen_at DESC LIMIT 1) AS source_url,
        j.published_at, ia.name AS primary_area, j.sector, j.relevance_tier, j.relevance_score,
        j.relevance_evidence, j.description_clean,
        j.hours_per_week, j.schedule_text, j.application_status, j.application_checked_at,
        jus.status AS user_status, jus.reason AS user_reason, 1 AS is_favorite,
        (SELECT a.status FROM applications a WHERE a.job_id=j.id) AS user_application
        FROM jobs j
        LEFT JOIN companies c ON c.id=j.company_id
        LEFT JOIN job_areas ja ON ja.job_id=j.id AND ja.is_primary=1
        LEFT JOIN industrial_areas ia ON ia.id=ja.area_id
        LEFT JOIN job_user_status jus ON jus.job_id=j.id
        WHERE jus.status='hidden'
        ORDER BY jus.updated_at DESC, j.published_at DESC NULLS LAST"""
    with connection() as conn:
        rows = conn.execute(sql).fetchall()
    return [_row_to_dict(row) for row in rows]


def set_job_user_status(job_id: str, status: str, reason: str | None = None, note: str | None = None) -> None:
    with connection() as conn:
        conn.execute(
            """INSERT INTO job_user_status(job_id, status, reason, note)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (job_id) DO UPDATE SET status=EXCLUDED.status,
                reason=EXCLUDED.reason, note=EXCLUDED.note, updated_at=now()""",
            (job_id, status, reason, note),
        )
        conn.commit()


_USER_LIST_SQL = """SELECT j.id, j.title, c.name AS company, j.location, j.seniority,
        j.work_mode, j.salary_min, j.salary_max, j.salary_currency,
        (SELECT source_url FROM job_sources js WHERE js.job_id=j.id ORDER BY js.last_seen_at DESC LIMIT 1) AS source_url,
        j.published_at, ia.name AS primary_area, j.sector, j.relevance_tier, j.relevance_score,
        j.relevance_evidence, j.description_clean,
        j.hours_per_week, j.schedule_text, j.application_status, j.application_checked_at,
        COALESCE(jus.status, 'visible') AS user_status, jus.reason AS user_reason,
        EXISTS (SELECT 1 FROM job_user_favorites f WHERE f.job_id=j.id) AS is_favorite,
        (SELECT a.status FROM applications a WHERE a.job_id=j.id) AS user_application
        FROM jobs j
        {join}
        LEFT JOIN companies c ON c.id=j.company_id
        LEFT JOIN job_areas ja ON ja.job_id=j.id AND ja.is_primary=1
        LEFT JOIN industrial_areas ia ON ia.id=ja.area_id
        LEFT JOIN job_user_status jus ON jus.job_id=j.id
        WHERE {where}
        ORDER BY {order}"""


def list_favorite_jobs() -> list[dict[str, Any]]:
    """Devuelve las ofertas guardadas por el usuario, más recientes primero."""
    sql = _USER_LIST_SQL.format(join="JOIN job_user_favorites juf ON juf.job_id=j.id", where="1=1",
                                order="juf.created_at DESC, j.published_at DESC NULLS LAST")
    with connection() as conn:
        rows = conn.execute(sql).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_job(job_id: str) -> dict[str, Any] | None:
    """Una oferta por id (también si está oculta o fuera de los filtros de la vista), o None."""
    sql = _USER_LIST_SQL.format(join="", where="j.id=%s", order="j.id")
    with connection() as conn:
        row = conn.execute(sql, (job_id,)).fetchone()
    return _row_to_dict(row) if row else None


def list_applied_jobs() -> list[dict[str, Any]]:
    """Ofertas a las que el usuario postuló (postulada, entrevista u oferta), la postulación más reciente primero."""
    sql = _USER_LIST_SQL.format(
        join="JOIN applications ap ON ap.job_id=j.id AND ap.status IN ('applied','interview','offer')", where="1=1",
        order="COALESCE(ap.applied_at, ap.updated_at) DESC")
    with connection() as conn:
        rows = conn.execute(sql).fetchall()
    return [_row_to_dict(row) for row in rows]


def skill_overview(
    max_age_days: int = 30,
    area: str | None = None,
    seniority: str | None = None,
    work_mode: str | None = None,
    include_applied: bool = True,
) -> dict[str, Any]:
    """Resume demanda de skills y la cruza con el último perfil local."""
    clauses = [
        "j.is_active = 1",
        "COALESCE(j.application_status, 'unknown') NOT IN ('closed', 'expired')",
        "j.duplicate_status = 'canonical'",
        "j.published_at IS NOT NULL",
        _VISIBLE_PUBLICATION_WINDOW,
        "j.relevance_tier IN ('core', 'adjacent')",
        "NOT EXISTS (SELECT 1 FROM job_user_status jus2 WHERE jus2.job_id=j.id AND jus2.status='hidden')",
    ]
    params: list[Any] = list(visible_date_bounds(max_age_days))
    if not include_applied:
        clauses.append("NOT EXISTS (SELECT 1 FROM applications a WHERE a.job_id=j.id AND a.status IN ('applied','interview','offer','rejected')) AND NOT EXISTS (SELECT 1 FROM processes p WHERE p.job_id=j.id)")
    if area:
        clauses.append("EXISTS (SELECT 1 FROM job_areas ja2 JOIN industrial_areas ia2 ON ia2.id=ja2.area_id WHERE ja2.job_id=j.id AND ja2.is_primary=1 AND ia2.name=%s)")
        params.append(area)
    if seniority:
        if seniority == "senior":
            clauses.append("j.seniority IN ('senior', 'senior_or_lead')")
        elif seniority == "intern":
            clauses.append("j.seniority IN ('intern', 'trainee')")
        else:
            clauses.append("j.seniority=%s")
            params.append(seniority)
    if work_mode:
        clauses.append("j.work_mode=%s")
        params.append(work_mode)
    where = " AND ".join(clauses)
    sql = f"""WITH eligible_jobs AS (
        SELECT DISTINCT j.id FROM jobs j WHERE {where}
    )
    SELECT s.name, COALESCE(s.category, 'other') AS category,
        CASE
            WHEN s.name IN ('Comunicación', 'Trabajo en equipo', 'Pensamiento analítico', 'Resolución de problemas', 'Liderazgo', 'Adaptabilidad') THEN 'soft'
            WHEN s.name = 'English' OR s.category = 'idioma' THEN 'language'
            WHEN s.name IN ('Lean', 'Six Sigma', 'Kaizen', 'VSM', '5S', 'BPMN', 'Scrum', 'Project Management') THEN 'methodology'
            WHEN s.name IN ('Supply Chain', 'Inventory Management', 'Demand Planning', 'Forecasting', 'Optimization') OR s.category IN ('supply-chain', 'planeamiento', 'mejora', 'calidad', 'procesos', 'proyectos') THEN 'domain'
            ELSE COALESCE(s.skill_type, 'technical')
        END AS skill_type,
        count(DISTINCT js.job_id) AS job_count,
        count(DISTINCT CASE WHEN js.requirement_type='required' THEN js.job_id END) AS required_count,
        round(avg(js.confidence), 3) AS confidence,
        COALESCE(us.level, 'none') AS user_level,
        us.interest, us.evidence
    FROM job_skills js
    JOIN eligible_jobs ej ON ej.id=js.job_id
    JOIN skills s ON s.id=js.skill_id
    LEFT JOIN user_skills us ON us.skill_id=s.id
        AND us.profile_id=(SELECT id FROM user_profile ORDER BY updated_at DESC LIMIT 1)
    GROUP BY s.name, s.category, s.skill_type, us.level, us.interest, us.evidence
    ORDER BY job_count DESC, s.name"""
    with connection() as conn:
        total = conn.execute(f"SELECT count(*) FROM jobs j WHERE {where}", params).fetchone()[0]
        rows = conn.execute(sql, params).fetchall()
    skills = []
    for row in rows:
        skills.append({
            "name": row[0],
            "category": row[1],
            "skill_type": row[2],
            "job_count": int(row[3]),
            "required_count": int(row[4]),
            "confidence": float(row[5]) if row[5] is not None else 0,
            "user_level": row[6],
            "interest": row[7],
            "evidence": row[8],
            "share": round(row[3] / total, 4) if total else 0,
        })
    return {"total_jobs": total, "max_age_days": max_age_days, "skills": skills}


def set_job_favorite(job_id: str) -> None:
    with connection() as conn:
        conn.execute(
            """INSERT INTO job_user_favorites(job_id)
            VALUES (%s) ON CONFLICT (job_id) DO NOTHING""",
            (job_id,),
        )
        conn.commit()


def remove_job_favorite(job_id: str) -> None:
    with connection() as conn:
        conn.execute("DELETE FROM job_user_favorites WHERE job_id=%s", (job_id,))
        conn.commit()


def market_summary() -> dict[str, Any]:
    with connection() as conn:
        areas = conn.execute("""SELECT ia.name, count(*) AS job_count
            FROM job_areas ja JOIN industrial_areas ia ON ia.id=ja.area_id
            JOIN jobs j ON j.id=ja.job_id WHERE j.is_active=1 AND j.duplicate_status='canonical' AND ja.is_primary=1
            GROUP BY ia.name ORDER BY job_count DESC, ia.name""").fetchall()
        skills = conn.execute("""SELECT s.name, count(*) AS job_count
            FROM job_skills js JOIN skills s ON s.id=js.skill_id JOIN jobs j ON j.id=js.job_id
            WHERE j.is_active=1 AND j.duplicate_status='canonical' GROUP BY s.name ORDER BY job_count DESC, s.name LIMIT 30""").fetchall()
        total = conn.execute("SELECT count(*) FROM jobs WHERE is_active=1 AND duplicate_status='canonical'").fetchone()[0]
    return {
        "total_active_jobs": total,
        "by_area": [{"area": x[0], "job_count": int(x[1])} for x in areas],
        "top_skills": [{"skill": x[0], "job_count": int(x[1])} for x in skills],
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

    target_roles = json.loads(row[3]) if isinstance(row[3], str) else row[3]
    locations = json.loads(row[4]) if isinstance(row[4], str) else row[4]
    work_modes = json.loads(row[5]) if isinstance(row[5], str) else row[5]

    return {
        "id": str(row[0]),
        "name": row[1],
        "education": row[2],
        "target_roles": target_roles or [],
        "locations": locations or [],
        "work_modes": work_modes or [],
        "skills": {x[0]: x[1] for x in skills},
        "skill_details": [
            {"skill": x[0], "level": x[1], "evidence": x[2], "interest": x[3]} for x in skills
        ],
    }


def recommendations(
    limit: int = 10,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    include_applied: bool = False,
    include_hidden: bool = False,
) -> dict[str, Any]:
    from radar.careers import active_pack
    from radar.markets import backfill_market
    from radar.query_context import CURRENT_QUERY
    from radar.scoring import current_profile_fingerprint

    revision = current_profile_fingerprint()

    if CURRENT_QUERY.get():
        from radar.careers import active_pack

        profile = get_profile()
        jobs = list_jobs(limit=None, max_age_days=max_age_days,
                         include_applied=include_applied, include_hidden=include_hidden,
                         relevance_tier="market")
        scores = {}
        job_ids = {job["id"] for job in jobs}
        if profile and job_ids and CURRENT_QUERY.get().values()["market_id"] == active_pack().id:
            with connection() as conn:
                rows = conn.execute(
                    """SELECT js.job_id,js.total_score,js.strong_matches,js.missing_skills,js.reason,js.assessment,j.content_hash
                    FROM job_scores js JOIN jobs j ON j.id=js.job_id
                    WHERE js.profile_id=%s AND j.is_active=1""",
                    (profile["id"],),
                ).fetchall()
            scores = {
                r[0]: r[1:6]
                for r in rows
                if r[0] in job_ids
                and (meta := json.loads(r[5] or "{}")).get("profile_hash") == revision
                and meta.get("content_hash") == r[6]
            }
        for job in jobs:
            score = scores.get(job["id"])
            job.update(score=score[0] if score else None,
                       strong_matches=json.loads(score[1]) if score else [],
                       missing_skills=json.loads(score[2]) if score else [],
                       reason="Oferta del mercado seleccionado; encaje específico aún no calculado.")
            if score:
                job["reason"] = score[3]
                job["fit_assessment"] = json.loads(score[4])
        jobs.sort(key=lambda j: j["score"] if j["score"] is not None else -1, reverse=True)
        return {"profile_configured": bool(profile), "jobs": jobs[:min(max(limit, 1), 50)],
                "ranking": "reference_score" if scores else "recent",
                "score_scope": "reference_career" if scores else "not_computed_for_selected_market"}
    profile = get_profile()
    if not profile:
        return {
            "profile_configured": False,
            "jobs": [],
            "message": "Configura user_profile y user_skills antes de pedir recomendaciones.",
        }
    backfill_market(active_pack().id)
    extra_filters: list[str] = []
    if not include_hidden:
        extra_filters.append("AND NOT EXISTS (SELECT 1 FROM job_user_status jus WHERE jus.job_id=j.id AND jus.status='hidden')")
    if not include_applied:
        extra_filters.append("AND NOT EXISTS (SELECT 1 FROM applications a WHERE a.job_id=j.id AND a.status IN ('applied','interview','offer','rejected')) AND NOT EXISTS (SELECT 1 FROM processes p WHERE p.job_id=j.id)")
    extra_filter_sql = ("\n            " + "\n            ".join(extra_filters)) if extra_filters else ""

    with connection() as conn:
        rows = conn.execute(
            f"""SELECT j.id, j.title, c.name, j.location,
            (SELECT source_url FROM job_sources js WHERE js.job_id=j.id ORDER BY js.last_seen_at DESC LIMIT 1) AS source_url,
            j.published_at, j.work_mode, j.salary_min, j.salary_max, j.salary_currency,
            j.sector, j.hours_per_week, j.schedule_text,
            j.application_status, j.application_checked_at,
            js.total_score, js.strong_matches, js.missing_skills, js.reason,
            (SELECT a.status FROM applications a WHERE a.job_id=j.id) AS user_application,js.assessment
            FROM job_scores js JOIN jobs j ON j.id=js.job_id LEFT JOIN companies c ON c.id=j.company_id
            JOIN job_market_classifications m ON m.job_id=j.id AND m.market_id=%s
            WHERE js.profile_id=%s AND j.is_active=1 AND j.duplicate_status='canonical'
            AND json_extract(js.assessment,'$.profile_hash')=%s
            AND json_extract(js.assessment,'$.content_hash') IS j.content_hash
            AND m.relevance_tier IN ('core','adjacent')
            AND COALESCE(j.application_status, 'unknown') NOT IN ('closed', 'expired')
            AND j.published_at IS NOT NULL
            AND {_VISIBLE_PUBLICATION_WINDOW}{extra_filter_sql}
            ORDER BY js.total_score DESC, j.published_at DESC, j.relevance_score DESC LIMIT %s""",
            (active_pack().id, profile["id"], revision, *visible_date_bounds(max_age_days), min(max(limit, 1), 50)),
        ).fetchall()
    jobs = []
    for x in rows:
        strong_matches = json.loads(x[16]) if isinstance(x[16], str) else x[16]
        missing_skills = json.loads(x[17]) if isinstance(x[17], str) else x[17]
        pub_at = x[5].isoformat() if hasattr(x[5], "isoformat") else (str(x[5]) if x[5] is not None else None)
        checked_at = x[14].isoformat() if hasattr(x[14], "isoformat") else (str(x[14]) if x[14] is not None else None)
        jobs.append({
            "id": str(x[0]),
            "title": x[1],
            "company": x[2],
            "location": x[3],
            "url": x[4],
            "published_at": pub_at,
            "work_mode": x[6],
            "salary_min": float(x[7]) if x[7] is not None else None,
            "salary_max": float(x[8]) if x[8] is not None else None,
            "salary_currency": x[9],
            "sector": x[10],
            "hours_per_week": float(x[11]) if x[11] is not None else None,
            "schedule_text": x[12],
            "application_status": x[13],
            "application_checked_at": checked_at,
            "score": float(x[15]),
            "strong_matches": strong_matches or [],
            "missing_skills": missing_skills or [],
            "reason": x[18], "fit_assessment": json.loads(x[20] or '{}'),
            "user_application": x[19] if len(x) > 19 else None,
        })
    return {
        "profile_configured": True,
        "jobs": jobs,
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
             "description": x[4], "date": str(x[5] or x[6]) if (x[5] or x[6]) else None}
            for x in rows]


def job_history(job_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Muestra cómo cambió una oferta y cuándo fue observada."""
    with connection() as conn:
        rows = conn.execute(
            """SELECT observed_at, content_hash, is_active, snapshot
            FROM job_observations WHERE job_id=%s ORDER BY observed_at DESC LIMIT %s""",
            (job_id, min(max(limit, 1), 100)),
        ).fetchall()
    return [{"observed_at": str(x[0]), "content_hash": x[1],
             "is_active": bool(x[2]), "snapshot": json.loads(x[3]) if isinstance(x[3], str) else x[3]} for x in rows]


def market_history(limit: int = 90) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """SELECT snapshot_date, metric_name, dimensions, metric_value
            FROM market_snapshots ORDER BY snapshot_date DESC, metric_name LIMIT %s""",
            (min(max(limit, 1), 500),),
        ).fetchall()
    return [{"date": str(x[0]), "metric": x[1], "dimensions": json.loads(x[2]) if isinstance(x[2], str) else x[2], "value": float(x[3])} for x in rows]


def skill_history(limit: int = 180) -> list[dict[str, Any]]:
    """Snapshots históricos de demanda por skill, para comparar periodos."""
    with connection() as conn:
        rows = conn.execute(
            """SELECT snapshot_date, json_extract(dimensions, '$.skill') AS skill, metric_value
            FROM market_snapshots
            WHERE metric_name='skill_jobs' AND json_extract(dimensions, '$.skill') IS NOT NULL
            ORDER BY snapshot_date ASC, skill ASC LIMIT %s""",
            (min(max(limit, 1), 2000),),
        ).fetchall()
    return [{"date": str(x[0]), "skill": x[1], "value": int(x[2])} for x in rows]


def applications(limit: int = 50) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """SELECT a.id, a.job_id, j.title, c.name, a.status, a.notes, a.applied_at, a.updated_at,
            (SELECT source_url FROM job_sources js WHERE js.job_id=j.id ORDER BY js.last_seen_at DESC LIMIT 1) AS source_url,
            j.location, j.work_mode, j.salary_min, j.salary_max, j.salary_currency, ia.name AS primary_area
            FROM applications a JOIN jobs j ON j.id=a.job_id
            LEFT JOIN companies c ON c.id=j.company_id
            LEFT JOIN job_areas ja ON ja.job_id=j.id AND ja.is_primary=1
            LEFT JOIN industrial_areas ia ON ia.id=ja.area_id
            ORDER BY a.updated_at DESC LIMIT %s""",
            (min(max(limit, 1), 200),),
        ).fetchall()
    return [
        {
            "id": str(x[0]),
            "job_id": str(x[1]),
            "title": x[2],
            "company": x[3],
            "status": x[4],
            "notes": x[5],
            "applied_at": str(x[6]) if x[6] else None,
            "updated_at": str(x[7]),
            "url": x[8],
            "location": x[9],
            "work_mode": x[10],
            "salary_min": float(x[11]) if x[11] is not None else None,
            "salary_max": float(x[12]) if x[12] is not None else None,
            "salary_currency": x[13],
            "primary_area": x[14],
        }
        for x in rows
    ]


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
        "relevance_tier",
        "relevance_score",
        "relevance_evidence",
        "description",
        "hours_per_week",
        "schedule_text",
        "application_status",
        "application_checked_at",
        "user_status",
        "user_reason",
        "is_favorite",
        "user_application",
    )
    result = dict(zip(keys, row, strict=True))
    result["id"] = str(result["id"])
    for key in ("salary_min", "salary_max"):
        if result[key] is not None:
            result[key] = float(result[key])
    if result["published_at"] is not None:
        if hasattr(result["published_at"], "isoformat"):
            result["published_at"] = result["published_at"].isoformat()
        else:
            result["published_at"] = str(result["published_at"])
    result["is_favorite"] = bool(result["is_favorite"])
    return result
