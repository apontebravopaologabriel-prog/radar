from __future__ import annotations

import json
import math

from radar.classify import classify, infer_seniority
from radar.db.database import connection
from radar.domain.models import RawJob
from radar.enrichment import extract_schedule, infer_sector, infer_work_mode, normalize_salary
from radar.normalize import clean_description, content_hash, fingerprint, normalize_text
from radar.salary import extract_salary
from radar.scoring import score_job
from radar.taxonomy import infer_relevance


def audit_data_quality() -> dict:
    """Return a read-only, reproducible quality audit for the current market."""
    with connection() as conn:
        exact = conn.execute(
            "SELECT COUNT(*) FROM (SELECT canonical_fingerprint FROM jobs GROUP BY canonical_fingerprint HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        same_role = conn.execute(
            """SELECT COUNT(*) FROM (
                SELECT company_id, title_normalized FROM jobs
                GROUP BY company_id, title_normalized HAVING COUNT(*) > 1
            )"""
        ).fetchone()[0]
        multiple_primary = conn.execute(
            """SELECT COUNT(*) FROM (
                SELECT job_id FROM job_areas WHERE is_primary=1 GROUP BY job_id HAVING COUNT(*) > 1
            )"""
        ).fetchone()[0]
        commercial_titles = conn.execute(
            """SELECT COUNT(*) FROM jobs
            WHERE (lower(title) LIKE 'venta%' OR lower(title) LIKE '% venta%'
               OR lower(title) LIKE '%comercial%' OR lower(title) LIKE '%vendedor%'
               OR lower(title) LIKE '%sales%' OR lower(title) LIKE '%account executive%'
               OR lower(title) LIKE '%key account%')
              AND lower(title) NOT LIKE '%inventario%'
              AND lower(title) NOT LIKE '%postventa%'"""
        ).fetchone()[0]
        commercial_in_target = conn.execute(
            """SELECT COUNT(*) FROM jobs j
            JOIN job_areas ja ON ja.job_id=j.id AND ja.is_primary=1
            JOIN industrial_areas ia ON ia.id=ja.area_id
            WHERE ia.name <> 'Ventas / Comercial'
              AND (lower(j.title) LIKE 'venta%' OR lower(j.title) LIKE '% venta%'
                OR lower(j.title) LIKE '%comercial%' OR lower(j.title) LIKE '%vendedor%'
                OR lower(j.title) LIKE '%sales%' OR lower(j.title) LIKE '%account executive%'
                OR lower(j.title) LIKE '%key account%')
              AND lower(j.title) NOT LIKE '%inventario%'
              AND lower(j.title) NOT LIKE '%postventa%'"""
        ).fetchone()[0]
        source_links = conn.execute("SELECT COUNT(*) FROM job_sources").fetchone()[0]
        jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    return {
        "jobs": jobs,
        "source_links": source_links,
        "exact_duplicate_groups": exact,
        "same_company_title_groups": same_role,
        "jobs_with_multiple_primary_areas": multiple_primary,
        "commercial_title_jobs": commercial_titles,
        "commercial_titles_in_target_areas": commercial_in_target,
    }


def _json_safe(value):
    """Convert pandas/NumPy NaN values into JSON null before PostgreSQL insertion."""
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def get_source_id(conn, source_name: str):
    row = conn.execute("SELECT id FROM sources WHERE name=%s", (source_name,)).fetchone()
    if not row:
        row = conn.execute(
            "INSERT INTO sources(name, source_type) VALUES (%s, 'manual') RETURNING id",
            (source_name,),
        ).fetchone()
    return row[0]


def ingest_jobs(jobs: list[RawJob]) -> dict[str, int]:
    stats = {"found": len(jobs), "created": 0, "updated": 0, "duplicates": 0}
    with connection() as conn:
        run = conn.execute(
            "INSERT INTO ingestion_runs(query, jobs_found) VALUES (%s, %s) RETURNING id",
            ("batch", len(jobs)),
        ).fetchone()[0]
        try:
            for raw in jobs:
                if not raw.url:
                    continue
                source_id = get_source_id(conn, raw.source)
                company_id = None
                if raw.company:
                    company_id = conn.execute(
                        "INSERT INTO companies(name, normalized_name) VALUES (%s,%s) ON CONFLICT(normalized_name) DO UPDATE SET updated_at=now() RETURNING id",
                        (raw.company, normalize_text(raw.company)),
                    ).fetchone()[0]
                fp = fingerprint(raw)
                text_salary = extract_salary(raw.description)
                # The description is preferred when it contains an explicit
                # salary range: portals occasionally truncate structured values.
                salary_min = text_salary.minimum if text_salary else raw.salary_min
                salary_max = text_salary.maximum if text_salary else raw.salary_max
                salary_currency = text_salary.currency if text_salary else raw.salary_currency
                salary_period = text_salary.period if text_salary else raw.salary_period
                salary_min, salary_max, salary_currency = normalize_salary(
                    salary_min, salary_max, salary_currency, salary_period
                )
                salary_source = "description" if text_salary else ("direct_data" if raw.salary_min is not None or raw.salary_max is not None else "unknown")
                if salary_min is None and salary_max is None:
                    salary_source = "unknown"
                inferred_mode = infer_work_mode(raw)
                work_mode = inferred_mode if inferred_mode != "unknown" else (raw.work_mode or "unknown")
                sector = infer_sector(raw)
                hours_per_week, schedule_text = extract_schedule(raw)
                classified = classify(raw)
                relevance = infer_relevance(raw, classified.primary_area.value)
                application_status = raw.application_status if raw.application_status in {"unknown", "open", "closed", "expired"} else "unknown"
                application_source = raw.application_status_source if application_status != "unknown" else "unknown"
                existing = conn.execute(
                    "SELECT id FROM jobs WHERE canonical_fingerprint=%s ORDER BY created_at LIMIT 1",
                    (fp,),
                ).fetchone()
                if existing:
                    job_id = existing[0]
                    stats["duplicates"] += 1
                    conn.execute(
                        """UPDATE jobs SET updated_at=now(), is_active=TRUE, content_hash=%s,
                        description_raw=%s, description_clean=%s, salary_min=%s, salary_max=%s,
                        salary_currency=%s, salary_period=%s, salary_source=%s,
                        work_mode=%s, sector=%s, sector_confidence=%s,
                        relevance_tier=%s, relevance_score=%s, relevance_evidence=%s,
                        hours_per_week=%s, schedule_text=%s,
                        application_status=COALESCE(NULLIF(%s, 'unknown'), application_status),
                        application_checked_at=COALESCE(%s, application_checked_at),
                        application_status_source=COALESCE(NULLIF(%s, 'unknown'), application_status_source),
                        published_at=COALESCE(%s, published_at) WHERE id=%s""",
                        (content_hash(raw), raw.description, clean_description(raw.description), salary_min,
                         salary_max, salary_currency, salary_period, salary_source, work_mode,
                         sector, 0.75 if sector else None, relevance.tier, relevance.score, relevance.evidence,
                         hours_per_week, schedule_text,
                         application_status, raw.application_checked_at, application_source,
                         raw.published_at, job_id),
                    )
                    stats["updated"] += 1
                else:
                    row = conn.execute(
                        """INSERT INTO jobs(company_id,title,title_normalized,location,location_normalized,country,description_raw,description_clean,
                        salary_min,salary_max,salary_currency,salary_period,salary_source,published_at,seniority,work_mode,employment_type,sector,sector_confidence,relevance_tier,relevance_score,relevance_evidence,hours_per_week,schedule_text,application_status,application_checked_at,application_status_source,canonical_fingerprint,content_hash)
                        VALUES (%s,%s,%s,%s,%s,'PE',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (
                            company_id,
                            raw.title,
                            normalize_text(raw.title),
                            raw.location,
                            normalize_text(raw.location),
                            raw.description,
                            clean_description(raw.description),
                            salary_min,
                            salary_max,
                            salary_currency,
                            salary_period,
                            salary_source,
                            raw.published_at,
                            infer_seniority(raw),
                            work_mode,
                            raw.employment_type,
                            sector,
                            0.75 if sector else None,
                            relevance.tier,
                            relevance.score,
                            relevance.evidence,
                            hours_per_week,
                            schedule_text,
                            application_status,
                            raw.application_checked_at,
                            application_source,
                            fp,
                            content_hash(raw),
                        ),
                    ).fetchone()
                    job_id = row[0]
                    stats["created"] += 1
                    areas = [classified.primary_area, *classified.secondary_areas]
                    for idx, area in enumerate(areas):
                        area_id = conn.execute(
                            "SELECT id FROM industrial_areas WHERE name=%s", (area.value,)
                        ).fetchone()
                        if area_id:
                            conn.execute(
                                "INSERT INTO job_areas(job_id,area_id,is_primary,confidence,evidence) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                                (job_id, area_id[0], idx == 0, area.confidence, area.evidence),
                            )
                    for skill, evidence in classified.skills:
                        skill_id = conn.execute(
                            "SELECT id FROM skills WHERE name=%s", (skill,)
                        ).fetchone()
                        if skill_id:
                            conn.execute(
                                "INSERT INTO job_skills(job_id,skill_id,requirement_type,importance,confidence,evidence) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                                (
                                    job_id,
                                    skill_id[0],
                                    evidence.requirement_type,
                                    0.7,
                                    evidence.confidence,
                                    evidence.evidence,
                                ),
                            )
                conn.execute(
                    """INSERT INTO job_sources(job_id,source_id,external_id,source_url,raw_payload)
                    VALUES (%s,%s,%s,%s,%s) ON CONFLICT(source_id,source_url) DO UPDATE SET last_seen_at=now(), raw_payload=EXCLUDED.raw_payload, is_active=TRUE""",
                    (job_id, source_id, raw.external_id, raw.url, json.dumps(_json_safe(raw.raw_payload), default=str)),
                )
                conn.execute(
                    """INSERT INTO job_observations(job_id,source_id,content_hash,snapshot)
                    VALUES (%s,%s,%s,%s)""",
                    (job_id, source_id, content_hash(raw), json.dumps({
                        "title": raw.title, "company": raw.company, "location": raw.location,
                        "published_at": raw.published_at, "url": raw.url, "source": raw.source,
                    }, default=str)),
                )
            conn.execute(
                "UPDATE ingestion_runs SET finished_at=now(),jobs_created=%s,jobs_updated=%s,duplicates_detected=%s,status='success' WHERE id=%s",
                (stats["created"], stats["updated"], stats["duplicates"], run),
            )
            conn.commit()
        except Exception as exc:
            conn.execute(
                "UPDATE ingestion_runs SET finished_at=now(),errors=%s,status='failed' WHERE id=%s",
                (json.dumps([str(exc)]), run),
            )
            conn.commit()
            raise
    # New ingestion must immediately participate in recommendations for the
    # latest profile; otherwise jobs remain stored but invisible to scoring.
    with connection() as conn:
        profile = conn.execute(
            "SELECT id FROM user_profile ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
    if profile:
        recompute_scores(str(profile[0]))
    return stats


def repair_data_quality() -> dict[str, int]:
    """Backfill inferred metadata for jobs captured before enrichment existed."""
    stats = {"jobs_checked": 0, "work_modes_repaired": 0, "salaries_cleared": 0, "salaries_repaired": 0, "sectors_added": 0, "sectors_reclassified": 0, "schedules_added": 0, "classifications_rebuilt": 0}
    with connection() as conn:
        rows = conn.execute(
            """SELECT id, title, location, description_raw, work_mode,
            salary_min, salary_max, salary_currency, salary_period, salary_source, sector,
            hours_per_week, schedule_text
            FROM jobs"""
        ).fetchall()
        for row in rows:
            stats["jobs_checked"] += 1
            raw = RawJob(
                source="repair",
                title=row[1],
                company=None,
                url="",
                location=row[2],
                description=row[3],
                salary_min=float(row[5]) if row[5] is not None else None,
                salary_max=float(row[6]) if row[6] is not None else None,
                salary_currency=row[7],
                salary_period=row[8],
                work_mode=row[4],
                hours_per_week=float(row[11]) if row[11] is not None else None,
                schedule_text=row[12],
            )
            inferred_mode = infer_work_mode(raw)
            mode = inferred_mode if inferred_mode != "unknown" else (row[4] or "unknown")
            inferred_sector = infer_sector(raw)
            sector = inferred_sector or row[10]
            hours_per_week, schedule_text = extract_schedule(raw)
            classified = classify(raw)
            relevance = infer_relevance(raw, classified.primary_area.value)
            text_salary = extract_salary(raw.description)
            if text_salary:
                salary_min, salary_max, salary_currency = normalize_salary(
                    text_salary.minimum,
                    text_salary.maximum,
                    text_salary.currency,
                    text_salary.period,
                )
                salary_period = text_salary.period
            else:
                salary_min, salary_max, salary_currency = normalize_salary(
                    raw.salary_min, raw.salary_max, raw.salary_currency, raw.salary_period
                )
                salary_period = raw.salary_period
            if mode != row[4]:
                stats["work_modes_repaired"] += 1
            if row[5] is not None and salary_min is None and salary_max is None:
                stats["salaries_cleared"] += 1
            if (row[5], row[6], row[7]) != (salary_min, salary_max, salary_currency):
                stats["salaries_repaired"] += 1
            if row[10] is None and sector:
                stats["sectors_added"] += 1
            elif inferred_sector and inferred_sector != row[10]:
                stats["sectors_reclassified"] += 1
            if row[11] is None and hours_per_week is not None:
                stats["schedules_added"] += 1
            salary_source = "description" if text_salary else (row[9] if salary_min is not None or salary_max is not None else "unknown")
            conn.execute(
                """UPDATE jobs SET work_mode=%s, salary_min=%s, salary_max=%s,
                salary_currency=%s, salary_period=%s, salary_source=%s,
                sector=%s, sector_confidence=%s, relevance_tier=%s, relevance_score=%s,
                relevance_evidence=%s, hours_per_week=%s, schedule_text=%s WHERE id=%s""",
                (mode, salary_min, salary_max, salary_currency, salary_period, salary_source,
                 sector, 0.75 if sector else None, relevance.tier, relevance.score,
                 relevance.evidence, hours_per_week, schedule_text, row[0]),
            )
            # Rebuild derived areas/skills so classifier fixes apply to old jobs too.
            conn.execute("DELETE FROM job_areas WHERE job_id=%s", (row[0],))
            conn.execute("DELETE FROM job_skills WHERE job_id=%s", (row[0],))
            for idx, area in enumerate([classified.primary_area, *classified.secondary_areas]):
                area_id = conn.execute(
                    "SELECT id FROM industrial_areas WHERE name=%s", (area.value,)
                ).fetchone()
                if area_id:
                    conn.execute(
                        "INSERT INTO job_areas(job_id,area_id,is_primary,confidence,evidence) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                        (row[0], area_id[0], idx == 0, area.confidence, area.evidence),
                    )
            for skill, evidence in classified.skills:
                skill_id = conn.execute(
                    "SELECT id FROM skills WHERE name=%s", (skill,)
                ).fetchone()
                if skill_id:
                    conn.execute(
                        "INSERT INTO job_skills(job_id,skill_id,requirement_type,importance,confidence,evidence) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                        (row[0], skill_id[0], evidence.requirement_type, 0.7, evidence.confidence, evidence.evidence),
                    )
            stats["classifications_rebuilt"] += 1
        conn.commit()
    return stats


def save_profile(
    name: str,
    education: str | None,
    areas: list[str],
    locations: list[str],
    work_modes: list[str],
    skills: dict[str, str],
) -> str:
    areas_json = json.dumps(areas, ensure_ascii=False) if isinstance(areas, list) else areas
    locations_json = json.dumps(locations, ensure_ascii=False) if isinstance(locations, list) else locations
    work_modes_json = json.dumps(work_modes, ensure_ascii=False) if isinstance(work_modes, list) else work_modes
    with connection() as conn:
        existing = conn.execute(
            "SELECT id FROM user_profile ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        if existing:
            profile_id = existing[0]
            conn.execute(
                "UPDATE user_profile SET name=%s, education=%s, target_roles=%s, preferred_locations=%s, preferred_work_modes=%s, updated_at=now() WHERE id=%s",
                (name, education, areas_json, locations_json, work_modes_json, profile_id),
            )
        else:
            profile_id = conn.execute(
                "INSERT INTO user_profile(name,education,target_roles,preferred_locations,preferred_work_modes) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                (name, education, areas_json, locations_json, work_modes_json),
            ).fetchone()[0]
        for skill, level in skills.items():
            row = conn.execute(
                "SELECT id FROM skills WHERE normalized_name=%s",
                (normalize_text(skill).replace(" ", "-"),),
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT id FROM skills WHERE lower(name)=lower(%s)", (skill,)
                ).fetchone()
            if row:
                conn.execute(
                    "INSERT INTO user_skills(profile_id,skill_id,level,last_verified_at) VALUES (%s,%s,%s,now()) ON CONFLICT(profile_id,skill_id) DO UPDATE SET level=EXCLUDED.level, updated_at=now(), last_verified_at=now()",
                    (profile_id, row[0], level),
                )
        version = conn.execute(
            "SELECT COALESCE(MAX(version_number), 0) + 1 FROM profile_versions WHERE profile_id=%s",
            (profile_id,),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO profile_versions(profile_id,version_number,snapshot,change_reason) VALUES (%s,%s,%s,%s)",
            (profile_id, version, json.dumps({"name": name, "education": education, "target_roles": areas, "preferred_locations": locations, "preferred_work_modes": work_modes, "skills": skills}), "explicit profile update"),
        )
        conn.commit()
    recompute_scores(profile_id)
    return str(profile_id)


def recompute_scores(profile_id: str) -> int:
    with connection() as conn:
        profile_row = conn.execute(
            "SELECT target_roles, preferred_locations, preferred_work_modes FROM user_profile WHERE id=%s",
            (profile_id,),
        ).fetchone()
        if not profile_row:
            return 0
        user_skills = conn.execute(
            "SELECT s.name, us.level FROM user_skills us JOIN skills s ON s.id=us.skill_id WHERE us.profile_id=%s",
            (profile_id,),
        ).fetchall()
        target_roles = json.loads(profile_row[0]) if isinstance(profile_row[0], str) else (profile_row[0] or [])
        locations = json.loads(profile_row[1]) if isinstance(profile_row[1], str) else (profile_row[1] or [])
        work_modes = json.loads(profile_row[2]) if isinstance(profile_row[2], str) else (profile_row[2] or [])
        profile = {
            "areas": target_roles,
            "locations": locations,
            "work_modes": work_modes,
            "skills": dict(user_skills),
        }
        jobs = conn.execute(
            "SELECT id,title,location,work_mode FROM jobs WHERE is_active AND duplicate_status='canonical'"
        ).fetchall()
        count = 0
        for job_id, title, location, work_mode in jobs:
            raw = RawJob("stored", title, None, "", location=location, work_mode=work_mode)
            job_skills = {
                x[0]
                for x in conn.execute(
                    "SELECT s.name FROM job_skills js JOIN skills s ON s.id=js.skill_id WHERE js.job_id=%s",
                    (job_id,),
                ).fetchall()
            }
            area = conn.execute(
                "SELECT ia.name FROM job_areas ja JOIN industrial_areas ia ON ia.id=ja.area_id WHERE ja.job_id=%s AND ja.is_primary",
                (job_id,),
            ).fetchone()
            result = score_job(raw, profile, job_skills, area[0] if area else None)
            conn.execute(
                """INSERT INTO job_scores(job_id,profile_id,algorithm_version,total_score,area_score,skills_score,seniority_score,education_score,location_score,preference_score,strong_matches,missing_skills,reason)
                VALUES (%s,%s,'v1.0',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(job_id,profile_id) DO UPDATE SET algorithm_version='v1.0',total_score=EXCLUDED.total_score,area_score=EXCLUDED.area_score,skills_score=EXCLUDED.skills_score,seniority_score=EXCLUDED.seniority_score,education_score=EXCLUDED.education_score,location_score=EXCLUDED.location_score,preference_score=EXCLUDED.preference_score,strong_matches=EXCLUDED.strong_matches,missing_skills=EXCLUDED.missing_skills,reason=EXCLUDED.reason,computed_at=now()""",
                (
                    job_id,
                    profile_id,
                    result.total,
                    result.area,
                    result.skills,
                    result.seniority,
                    result.education,
                    result.location,
                    result.preference,
                    json.dumps(result.strong_matches),
                    json.dumps(result.missing_skills),
                    result.reason,
                ),
            )
            count += 1
        conn.commit()
    return count


def add_career_event(
    profile_id: str | None,
    event_type: str,
    title: str,
    description: str | None = None,
    started_on: str | None = None,
    ended_on: str | None = None,
) -> str:
    allowed = {"employment", "education", "course", "certification", "project", "interview", "achievement", "skill_update", "goal_update", "note"}
    if event_type not in allowed:
        raise ValueError(f"event_type inválido: {event_type}")
    with connection() as conn:
        if profile_id is None:
            row = conn.execute("SELECT id FROM user_profile ORDER BY updated_at DESC LIMIT 1").fetchone()
            profile_id = str(row[0]) if row else None
        event_id = conn.execute(
            """INSERT INTO career_events(profile_id,event_type,title,description,started_on,ended_on)
            VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
            (profile_id, event_type, title, description, started_on, ended_on),
        ).fetchone()[0]
        conn.commit()
    return str(event_id)


def capture_market_snapshot(snapshot_date: str | None = None) -> int:
    """Guarda métricas reproducibles del mercado activo para comparar periodos."""
    import json as json_module
    from datetime import UTC, datetime

    day = snapshot_date or datetime.now(UTC).date().isoformat()
    with connection() as conn:
        metrics = [("active_jobs", {}, conn.execute("SELECT count(*) FROM jobs WHERE is_active AND duplicate_status='canonical'").fetchone()[0])]
        metrics.extend(("area_jobs", {"area": row[0]}, row[1]) for row in conn.execute(
            """SELECT ia.name, count(*) FROM job_areas ja JOIN industrial_areas ia ON ia.id=ja.area_id
            JOIN jobs j ON j.id=ja.job_id WHERE j.is_active AND j.duplicate_status='canonical' AND ja.is_primary GROUP BY ia.name"""
        ).fetchall())
        metrics.extend(("skill_jobs", {"skill": row[0]}, row[1]) for row in conn.execute(
            """SELECT s.name, count(*) FROM job_skills js JOIN skills s ON s.id=js.skill_id
            JOIN jobs j ON j.id=js.job_id WHERE j.is_active AND j.duplicate_status='canonical' GROUP BY s.name"""
        ).fetchall())
        for name, dimensions, value in metrics:
            conn.execute(
                """INSERT INTO market_snapshots(snapshot_date,metric_name,dimensions,metric_value)
                VALUES (%s,%s,%s,%s) ON CONFLICT(snapshot_date,metric_name,dimensions)
                DO UPDATE SET metric_value=EXCLUDED.metric_value""",
                (day, name, json_module.dumps(dimensions), value),
            )
        conn.commit()
    return len(metrics)


def track_application(job_id: str, status: str = "saved", notes: str | None = None) -> str:
    statuses = {"new", "reviewed", "saved", "ignored", "applied", "interview", "offer", "rejected", "expired"}
    if status not in statuses:
        raise ValueError(f"status inválido: {status}")
    with connection() as conn:
        existing = conn.execute("SELECT id, status FROM applications WHERE job_id=%s", (job_id,)).fetchone()
        if existing:
            application_id, previous = existing
            conn.execute("UPDATE applications SET status=%s, notes=%s, applied_at=CASE WHEN %s='applied' THEN COALESCE(applied_at,now()) ELSE applied_at END, updated_at=now() WHERE id=%s", (status, notes, status, application_id))
            if previous != status:
                conn.execute("INSERT INTO application_events(application_id,from_status,to_status,notes) VALUES (%s,%s,%s,%s)", (application_id, previous, status, notes))
        else:
            application_id = conn.execute("INSERT INTO applications(job_id,status,notes,applied_at) VALUES (%s,%s,%s,CASE WHEN %s='applied' THEN now() ELSE NULL END) RETURNING id", (job_id, status, notes, status)).fetchone()[0]
            conn.execute("INSERT INTO application_events(application_id,to_status,notes) VALUES (%s,%s,%s)", (application_id, status, notes))
        conn.commit()
    return str(application_id)
