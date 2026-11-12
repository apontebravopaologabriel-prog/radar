from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Any

from radar.careers import CareerPack, active_pack, effective_weights, list_packs
from radar.classify import classify, infer_seniority
from radar.db.database import connection, database_path
from radar.domain.models import RawJob
from radar.enrichment import extract_schedule, infer_sector, infer_work_mode, normalize_salary
from radar.geolocation import infer_location
from radar.normalize import (
    clean_description,
    content_hash,
    fingerprint,
    normalize_company_key,
    normalize_text,
)
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
        orphans = conn.execute("SELECT count(*),coalesce(sum(j.is_active),0) FROM jobs j WHERE NOT EXISTS (SELECT 1 FROM job_sources s WHERE s.job_id=j.id)").fetchone()
        identity_conflicts = conn.execute("SELECT count(*) FROM (SELECT source_id,external_id FROM job_sources WHERE external_id IS NOT NULL AND external_id<>'' GROUP BY source_id,external_id HAVING count(DISTINCT job_id)>1)").fetchone()[0]
        jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    return {
        "jobs": jobs,
        "source_links": source_links,
        "jobs_without_source": orphans[0], "active_jobs_without_source": orphans[1],
        "source_identity_conflicts": identity_conflicts,
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


def _write_areas(conn, job_id: str, classified) -> None:
    """Reemplaza las áreas de una oferta por la clasificación vigente (primaria + hasta dos secundarias)."""
    conn.execute("DELETE FROM job_areas WHERE job_id=%s", (job_id,))
    for idx, area in enumerate([classified.primary_area, *classified.secondary_areas]):
        area_id = conn.execute("SELECT id FROM industrial_areas WHERE name=%s", (area.value,)).fetchone()
        if area_id:
            conn.execute(
                "INSERT INTO job_areas(job_id,area_id,is_primary,confidence,evidence) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (job_id, area_id[0], idx == 0, area.confidence, area.evidence),
            )


def ingest_jobs(jobs: list[RawJob], pack: CareerPack | None = None, *, run_id: str | None = None,
                query: str = "batch", context: dict | None = None) -> dict[str, int]:
    pack = pack or active_pack()
    stats = {"found": len(jobs), "created": 0, "updated": 0, "duplicates": 0}
    with connection() as conn:
        run = run_id or conn.execute(
            "INSERT INTO ingestion_runs(query, context, jobs_found) VALUES (%s, %s, %s) RETURNING id",
            (query, json.dumps(context or {}), len(jobs)),
        ).fetchone()[0]
        conn.execute("SAVEPOINT ingestion_batch")
        try:
            for raw in jobs:
                if not raw.url:
                    continue
                if raw.external_id is not None:
                    raw = replace(raw, external_id=str(raw.external_id).strip() or None)
                source_id = get_source_id(conn, raw.source)
                company_id = None
                if raw.company:
                    company_id = conn.execute(
                        "INSERT INTO companies(name, normalized_name) VALUES (%s,%s) ON CONFLICT(normalized_name) DO UPDATE SET updated_at=now() RETURNING id",
                        (raw.company, normalize_text(raw.company)),
                    ).fetchone()[0]
                # Stable source identity wins over a mutable title/location fingerprint.
                appearances = conn.execute(
                    "SELECT DISTINCT job_id FROM job_sources WHERE source_id=%s AND (source_url=%s OR (external_id IS NOT NULL AND external_id=%s))",
                    (source_id, raw.url, raw.external_id),
                ).fetchall()
                if len(appearances) > 1:
                    raise ValueError("La URL y el identificador del portal apuntan a ofertas distintas; requiere revisión")
                fp = fingerprint(raw)
                existing = appearances[0] if appearances else conn.execute(
                    "SELECT id FROM jobs WHERE canonical_fingerprint=%s ORDER BY created_at LIMIT 1",
                    (fp,),
                ).fetchone()
                if existing and not appearances and raw.external_id:
                    distinct_publication = conn.execute(
                        "SELECT 1 FROM job_sources WHERE job_id=%s AND source_id=%s AND external_id IS NOT NULL AND external_id<>%s LIMIT 1",
                        (existing[0], source_id, raw.external_id),
                    ).fetchone()
                    if distinct_publication:
                        fp = hashlib.sha256(f"{fp}|{raw.source}|{raw.external_id}".encode()).hexdigest()
                        existing = conn.execute("SELECT id FROM jobs WHERE canonical_fingerprint=%s", (fp,)).fetchone()
                retained_description = False
                retained_title = False
                if existing and normalize_text(raw.title) in {"", "sin titulo"}:
                    previous_title = conn.execute("SELECT title FROM jobs WHERE id=%s", (existing[0],)).fetchone()[0]
                    raw = replace(raw, title=previous_title)
                    retained_title = True
                if existing and not (raw.description or "").strip():
                    previous = conn.execute("SELECT description_raw FROM jobs WHERE id=%s", (existing[0],)).fetchone()[0]
                    if previous:
                        raw = replace(raw, description=previous)
                        retained_description = True
                text_salary = extract_salary(raw.description, raw.title)
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
                seniority = infer_seniority(raw)
                sector = infer_sector(raw)
                hours_per_week, schedule_text = extract_schedule(raw)
                classified = classify(raw, pack)
                relevance = infer_relevance(
                    raw,
                    classified.primary_area.value,
                    pack,
                    [area.value for area in classified.secondary_areas],
                )
                application_status = raw.application_status if raw.application_status in {"unknown", "open", "closed", "expired"} else "unknown"
                application_source = raw.application_status_source if application_status != "unknown" else "unknown"
                if existing:
                    job_id = existing[0]
                    stats["duplicates"] += 1
                    conn.execute(
                        """UPDATE jobs SET updated_at=now(),
                        is_active=CASE WHEN COALESCE(NULLIF(%s, 'unknown'), application_status) IN ('closed', 'expired') THEN 0 ELSE 1 END,
                        content_hash=%s,
                        title=%s,title_normalized=%s,location=COALESCE(%s,location),
                        location_normalized=COALESCE(%s,location_normalized),company_id=COALESCE(%s,company_id),
                        description_raw=%s, description_clean=%s, salary_min=%s, salary_max=%s,
                        salary_currency=%s, salary_period=%s, salary_source=%s,
                        seniority=%s, work_mode=%s, sector=%s, sector_confidence=%s,
                        relevance_tier=%s, relevance_score=%s, relevance_evidence=%s,
                        hours_per_week=%s, schedule_text=%s,
                        application_status=COALESCE(NULLIF(%s, 'unknown'), application_status),
                        application_checked_at=COALESCE(%s, application_checked_at),
                        application_status_source=COALESCE(NULLIF(%s, 'unknown'), application_status_source),
                        published_at=COALESCE(%s, published_at) WHERE id=%s""",
                        (application_status, content_hash(raw), raw.title, normalize_text(raw.title), raw.location or None,
                         normalize_text(raw.location) if raw.location else None, company_id, raw.description, clean_description(raw.description), salary_min,
                         salary_max, salary_currency, salary_period, salary_source, seniority, work_mode,
                         sector, 0.75 if sector else None, relevance.tier, relevance.score, relevance.evidence,
                         hours_per_week, schedule_text,
                         application_status, raw.application_checked_at, application_source,
                         raw.published_at, job_id),
                    )
                    _write_areas(conn, job_id, classified)
                    stats["updated"] += 1
                else:
                    clean_desc = clean_description(raw.description)
                    title_norm = normalize_text(raw.title)
                    c_hash = content_hash(raw)
                    dup_parent = _find_canonical_duplicate(
                        conn,
                        source_id=source_id,
                        content_digest=c_hash,
                        company_name=raw.company,
                        company_id=company_id,
                        title_norm=title_norm,
                        description_clean=clean_desc,
                        location_text=raw.location,
                    )
                    dup_status = "merged" if dup_parent else "canonical"
                    row = conn.execute(
                        """INSERT INTO jobs(company_id,title,title_normalized,location,location_normalized,country,description_raw,description_clean,
                        salary_min,salary_max,salary_currency,salary_period,salary_source,published_at,seniority,work_mode,employment_type,sector,sector_confidence,relevance_tier,relevance_score,relevance_evidence,hours_per_week,schedule_text,application_status,application_checked_at,application_status_source,canonical_fingerprint,content_hash,duplicate_group_id,duplicate_status)
                        VALUES (%s,%s,%s,%s,%s,'PE',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (
                            company_id,
                            raw.title,
                            title_norm,
                            raw.location,
                            normalize_text(raw.location),
                            raw.description,
                            clean_desc,
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
                            c_hash,
                            dup_parent,
                            dup_status,
                        ),
                    ).fetchone()
                    job_id = row[0]
                    stats["created"] += 1
                    _write_areas(conn, job_id, classified)
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
                from radar.markets import project_job

                project_job(conn, job_id, raw)
                conn.execute(
                    """INSERT INTO job_sources(job_id,source_id,external_id,source_url,raw_payload)
                    VALUES (%s,%s,%s,%s,%s) ON CONFLICT(source_id,source_url) DO UPDATE SET last_seen_at=now(),
                    external_id=COALESCE(EXCLUDED.external_id,external_id),raw_payload=EXCLUDED.raw_payload, is_active=TRUE""",
                    (job_id, source_id, raw.external_id, raw.url, json.dumps(_json_safe(raw.raw_payload), default=str)),
                )
                conn.execute(
                    """INSERT INTO job_observations(job_id,source_id,content_hash,snapshot)
                    VALUES (%s,%s,%s,%s)""",
                    (job_id, source_id, content_hash(raw), json.dumps({
                        "title": raw.title, "company": raw.company, "location": raw.location,
                        "published_at": raw.published_at, "url": raw.url, "source": raw.source,
                        "description_retained_from_previous_observation": retained_description,
                        "title_retained_from_previous_observation": retained_title,
                    }, default=str)),
                )
            conn.execute(
                "UPDATE ingestion_runs SET finished_at=now(),jobs_created=%s,jobs_updated=%s,duplicates_detected=%s,status='success' WHERE id=%s",
                (stats["created"], stats["updated"], stats["duplicates"], run),
            )
            conn.execute("RELEASE SAVEPOINT ingestion_batch")
            conn.commit()
        except Exception as exc:
            conn.execute("ROLLBACK TO SAVEPOINT ingestion_batch")
            conn.execute("RELEASE SAVEPOINT ingestion_batch")
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


REPAIR_BATCH = 200  # confirmaciones frecuentes: la base no queda bloqueada para la app durante minutos


def _same(old: Any, new: Any) -> bool:
    if old is None or new is None:
        return old is None and new is None
    try:
        return abs(float(old) - float(new)) < 1e-9
    except (TypeError, ValueError):
        return old == new


def repair_data_quality() -> dict[str, int]:
    """Backfill inferred metadata for jobs captured before enrichment existed.

    Recalcula todo, pero solo escribe las ofertas cuyo resultado cambió (antes reescribía las ~6 000 en una sola
    transacción de minutos) y confirma por lotes."""
    pack = active_pack()
    stats = {"jobs_checked": 0, "work_modes_repaired": 0, "salaries_cleared": 0, "salaries_repaired": 0, "sectors_added": 0,
             "sectors_reclassified": 0, "schedules_added": 0, "classifications_rebuilt": 0, "jobs_unchanged": 0}
    with connection() as conn:
        area_ids = {name: area_id for area_id, name in conn.execute("SELECT id, name FROM industrial_areas").fetchall()}
        skill_ids = {name: skill_id for skill_id, name in conn.execute("SELECT id, name FROM skills").fetchall()}
        current_areas: dict[str, set[tuple]] = {}
        for job_id, area_id, primary, evidence in conn.execute("SELECT job_id, area_id, is_primary, evidence FROM job_areas").fetchall():
            current_areas.setdefault(job_id, set()).add((area_id, bool(primary), evidence))
        current_skills: dict[str, set[tuple]] = {}
        for job_id, skill_id, requirement, evidence in conn.execute("SELECT job_id, skill_id, requirement_type, evidence FROM job_skills").fetchall():
            current_skills.setdefault(job_id, set()).add((skill_id, requirement, evidence))
        rows = conn.execute(
            """SELECT id, title, location, description_raw, work_mode,
            salary_min, salary_max, salary_currency, salary_period, salary_source, sector,
            hours_per_week, schedule_text, sector_confidence, relevance_tier, relevance_score, relevance_evidence,
            seniority
            FROM jobs"""
        ).fetchall()
        pending = 0
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
            seniority = infer_seniority(raw)
            inferred_sector = infer_sector(raw)
            sector = inferred_sector or row[10]
            hours_per_week, schedule_text = extract_schedule(raw)
            classified = classify(raw, pack)
            relevance = infer_relevance(
                raw,
                classified.primary_area.value,
                pack,
                [area.value for area in classified.secondary_areas],
            )
            text_salary = extract_salary(raw.description, raw.title)
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
            sector_confidence = 0.75 if sector else None
            new_job = (mode, salary_min, salary_max, salary_currency, salary_period, salary_source, sector, sector_confidence,
                       relevance.tier, relevance.score, relevance.evidence, hours_per_week, schedule_text, seniority)
            old_job = (row[4], row[5], row[6], row[7], row[8], row[9], row[10], row[13], row[14], row[15], row[16], row[11], row[12], row[17])
            new_areas = {(area_ids[a.value], idx == 0, a.evidence)
                         for idx, a in enumerate([classified.primary_area, *classified.secondary_areas]) if a.value in area_ids}
            new_skills = {(skill_ids[skill], evidence.requirement_type, evidence.evidence)
                          for skill, evidence in classified.skills if skill in skill_ids}
            job_changed = not all(_same(old, new) for old, new in zip(old_job, new_job, strict=True))
            derived_changed = new_areas != current_areas.get(row[0], set()) or new_skills != current_skills.get(row[0], set())
            if not job_changed and not derived_changed:
                stats["jobs_unchanged"] += 1
                continue
            if job_changed:
                conn.execute(
                    """UPDATE jobs SET work_mode=%s, salary_min=%s, salary_max=%s,
                    salary_currency=%s, salary_period=%s, salary_source=%s,
                    sector=%s, sector_confidence=%s, relevance_tier=%s, relevance_score=%s,
                    relevance_evidence=%s, hours_per_week=%s, schedule_text=%s, seniority=%s WHERE id=%s""",
                    (*new_job[:6], sector, sector_confidence, relevance.tier, relevance.score, relevance.evidence,
                     hours_per_week, schedule_text, seniority, row[0]),
                )
            if derived_changed:
                # Rebuild derived areas/skills so classifier fixes apply to old jobs too.
                conn.execute("DELETE FROM job_areas WHERE job_id=%s", (row[0],))
                conn.execute("DELETE FROM job_skills WHERE job_id=%s", (row[0],))
                for idx, area in enumerate([classified.primary_area, *classified.secondary_areas]):
                    if area.value in area_ids:
                        conn.execute(
                            "INSERT INTO job_areas(job_id,area_id,is_primary,confidence,evidence) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                            (row[0], area_ids[area.value], idx == 0, area.confidence, area.evidence),
                        )
                for skill, evidence in classified.skills:
                    if skill in skill_ids:
                        conn.execute(
                            "INSERT INTO job_skills(job_id,skill_id,requirement_type,importance,confidence,evidence) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                            (row[0], skill_ids[skill], evidence.requirement_type, 0.7, evidence.confidence, evidence.evidence),
                        )
                stats["classifications_rebuilt"] += 1
            pending += 1
            if pending >= REPAIR_BATCH:
                conn.commit()
                pending = 0
        conn.commit()
    return stats


def expire_stale_jobs(stale_after_days: int = 45) -> int:
    """Desactiva ofertas que ninguna fuente volvió a ver en stale_after_days o cerradas/vencidas.

    El filtro de frescura de list_jobs ya oculta ofertas viejas de la vista,
    pero is_active nunca bajaba, así que la tabla crecía sin límite. Un valor
    generoso evita apagar ofertas que solo tardan un poco en refrescarse.
    """
    with connection() as conn:
        cursor = conn.execute(
            """UPDATE jobs SET is_active = 0, updated_at = now()
            WHERE is_active = 1
            AND (
                application_status IN ('closed', 'expired')
                OR (published_at IS NOT NULL AND date(published_at) < date('now', '-' || %s || ' days'))
                OR NOT EXISTS (
                    SELECT 1 FROM job_sources js
                    WHERE js.job_id = jobs.id
                    AND date(js.last_seen_at) >= date('now', '-' || %s || ' days')
                )
            )""",
            (stale_after_days, stale_after_days),
        )
        conn.commit()
        return cursor.rowcount


_GENERIC_COMPANIES = frozenset({
    "",
    "importante empresa del sector",
    "confidencial",
    "empresa confidencial",
    "anonimo",
    "empresa del rubro",
    "sin empresa",
})


def _parse_dt_days(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _within_window(dt_a: Any, dt_b: Any, window_days: int) -> bool:
    a, b = _parse_dt_days(dt_a), _parse_dt_days(dt_b)
    if not a or not b:
        return True
    return abs((a - b).days) <= window_days


def _desc_similar(a: str | None, b: str | None, threshold: float = 0.85) -> bool:
    ta, tb = (a or "")[:600].lower(), (b or "")[:600].lower()
    if not ta or not tb:
        return ta == tb
    if ta == tb:
        return True
    return SequenceMatcher(None, ta, tb).ratio() >= threshold


def _geo_bucket(location_text: str | None) -> str:
    pt = infer_location(location_text)
    if pt is None:
        return "unlocated"
    if (pt.place_id and pt.place_id.startswith("pe:lima-callao:")) or normalize_text(pt.label) in {"lima", "callao"}:
        return "lima_callao"
    return normalize_text(pt.label)


def _find_canonical_duplicate(
    conn,
    *,
    source_id: str,
    content_digest: str,
    company_name: str | None,
    company_id: str | None,
    title_norm: str,
    description_clean: str,
    location_text: str | None = None,
    window_days: int = 30,
) -> str | None:
    """Return an existing recent canonical job ID from another portal if this offer is a cross-portal duplicate."""
    target_geo = _geo_bucket(location_text)
    if len(description_clean) >= 40:
        for row_id, row_loc in conn.execute(
            """SELECT id, location FROM jobs
            WHERE duplicate_status='canonical' AND content_hash=%s
              AND coalesce(published_at, created_at) >= datetime('now', '-' || %s || ' days')
              AND NOT EXISTS (SELECT 1 FROM job_sources js WHERE js.job_id = jobs.id AND js.source_id = %s)
            ORDER BY created_at ASC LIMIT 10""",
            (content_digest, window_days, source_id),
        ).fetchall():
            if _geo_bucket(row_loc) == target_geo:
                return row_id

    comp_key = normalize_company_key(company_name)
    if not title_norm or comp_key in _GENERIC_COMPANIES:
        return None

    if company_id:
        for row_id, row_loc in conn.execute(
            """SELECT id, location FROM jobs
            WHERE duplicate_status='canonical' AND company_id=%s AND title_normalized=%s
              AND coalesce(published_at, created_at) >= datetime('now', '-' || %s || ' days')
              AND NOT EXISTS (SELECT 1 FROM job_sources js WHERE js.job_id = jobs.id AND js.source_id = %s)
            ORDER BY created_at ASC LIMIT 10""",
            (company_id, title_norm, window_days, source_id),
        ).fetchall():
            if _geo_bucket(row_loc) == target_geo:
                return row_id

    candidates = conn.execute(
        """SELECT j.id, c.name, j.description_clean, j.location
        FROM jobs j LEFT JOIN companies c ON c.id = j.company_id
        WHERE j.duplicate_status='canonical' AND j.title_normalized=%s
          AND coalesce(j.published_at, j.created_at) >= datetime('now', '-' || %s || ' days')
          AND NOT EXISTS (SELECT 1 FROM job_sources js WHERE js.job_id = j.id AND js.source_id = %s)
        ORDER BY j.created_at ASC LIMIT 15""",
        (title_norm, window_days, source_id),
    ).fetchall()
    for cand_id, cand_comp, cand_desc, cand_loc in candidates:
        if _geo_bucket(cand_loc) != target_geo:
            continue
        if normalize_company_key(cand_comp) == comp_key and _desc_similar(description_clean, cand_desc):
            return cand_id
    return None


def deduplicate_jobs(window_days: int = 30) -> dict[str, int]:
    """Group and mark cross-portal/district duplicates as 'merged' without deleting historical offers."""
    with connection() as conn:
        user_touched = {
            row[0]
            for query in (
                "SELECT job_id FROM applications",
                "SELECT job_id FROM processes WHERE job_id IS NOT NULL",
                "SELECT job_id FROM job_user_favorites",
                "SELECT job_id FROM job_user_status",
                "SELECT job_id FROM cv_documents WHERE job_id IS NOT NULL",
            )
            for row in conn.execute(query).fetchall()
        }
        rows = conn.execute(
            """SELECT j.id, j.company_id, c.name, j.title_normalized, j.content_hash,
                      j.description_clean, coalesce(j.published_at, j.created_at) AS ref_dt,
                      j.salary_min, j.created_at, j.location
            FROM jobs j
            LEFT JOIN companies c ON c.id = j.company_id
            WHERE j.duplicate_status = 'canonical'"""
        ).fetchall()

        # Priority: user activity first, then salary present, longest description, oldest created_at.
        rows.sort(
            key=lambda r: (
                0 if r[0] in user_touched else 1,
                0 if r[7] is not None else 1,
                -len(r[5] or ""),
                str(r[8] or ""),
            )
        )

        by_hash: dict[str, list[tuple[str, Any, str]]] = {}
        by_comp_title: dict[tuple[str, str], list[tuple[str, Any, str]]] = {}
        by_compkey_title: dict[tuple[str, str], list[tuple[str, Any, str, str]]] = {}
        merges: list[tuple[str, str]] = []

        for job_id, comp_id, comp_name, title_norm, c_hash, desc_clean, ref_dt, _, _, loc_val in rows:
            canonical_id: str | None = None
            comp_key = normalize_company_key(comp_name)
            is_generic = comp_key in _GENERIC_COMPANIES
            geo_b = _geo_bucket(loc_val)

            if c_hash and len(desc_clean or "") >= 40:
                for cid, c_dt, c_geo in by_hash.get(c_hash, ()):
                    if geo_b == c_geo and _within_window(ref_dt, c_dt, window_days):
                        canonical_id = cid
                        break

            if not canonical_id and comp_id and title_norm and not is_generic:
                for cid, c_dt, c_geo in by_comp_title.get((comp_id, title_norm), ()):
                    if geo_b == c_geo and _within_window(ref_dt, c_dt, window_days):
                        canonical_id = cid
                        break

            if not canonical_id and title_norm and not is_generic:
                for cid, c_dt, c_desc, c_geo in by_compkey_title.get((comp_key, title_norm), ()):
                    if geo_b == c_geo and _within_window(ref_dt, c_dt, window_days) and _desc_similar(desc_clean, c_desc):
                        canonical_id = cid
                        break

            # Never merge a job with user activity into another job.
            if canonical_id and job_id not in user_touched:
                merges.append((canonical_id, job_id))
                continue

            if c_hash and len(desc_clean or "") >= 40:
                by_hash.setdefault(c_hash, []).append((job_id, ref_dt, geo_b))
            if comp_id and title_norm and not is_generic:
                by_comp_title.setdefault((comp_id, title_norm), []).append((job_id, ref_dt, geo_b))
            if title_norm and not is_generic:
                by_compkey_title.setdefault((comp_key, title_norm), []).append((job_id, ref_dt, desc_clean or "", geo_b))

        for canonical_id, dup_id in merges:
            conn.execute(
                "UPDATE jobs SET duplicate_status='merged', duplicate_group_id=%s, updated_at=now() WHERE id=%s",
                (canonical_id, dup_id),
            )
        conn.commit()
    return {"scanned": len(rows), "merged": len(merges)}


def compact_database(raw_payload_days: int = 30) -> dict[str, Any]:
    """Prune redundant observations, stale raw payloads and orphaned market rows, then VACUUM."""
    db_file = database_path()
    size_before = round(db_file.stat().st_size / (1024 * 1024), 2) if db_file.exists() else 0.0
    active_markets = [p.id for p in list_packs()]

    with connection() as conn:
        if active_markets:
            placeholders = ",".join(["%s"] * len(active_markets))
            orphaned = conn.execute(
                f"DELETE FROM job_market_classifications WHERE market_id NOT IN ({placeholders})",
                tuple(active_markets),
            ).rowcount
        else:
            orphaned = 0

        obs_pruned = conn.execute(
            """DELETE FROM job_observations
            WHERE id NOT IN (
                SELECT max_id FROM (
                    SELECT MAX(id) AS max_id
                    FROM job_observations
                    GROUP BY job_id, source_id
                )
            )"""
        ).rowcount

        raw_cleared = conn.execute(
            """UPDATE job_sources SET raw_payload = '{}'
            WHERE raw_payload <> '{}'
              AND last_seen_at < datetime('now', '-' || %s || ' days')""",
            (raw_payload_days,),
        ).rowcount
        conn.commit()
        conn.execute("VACUUM")
        conn.execute("ANALYZE")

    size_after = round(db_file.stat().st_size / (1024 * 1024), 2) if db_file.exists() else 0.0
    return {
        "size_before_mb": size_before,
        "size_after_mb": size_after,
        "orphaned_classifications_deleted": orphaned,
        "observations_pruned": obs_pruned,
        "raw_payloads_cleared": raw_cleared,
    }


def save_profile(
    name: str,
    education: str | None,
    areas: list[str],
    locations: list[str],
    work_modes: list[str],
    skills: dict[str, str],
    remove_skills: list[str] | None = None,
    reason: str | None = None,
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
        for skill in remove_skills or []:
            row = conn.execute(
                "SELECT id FROM skills WHERE normalized_name=%s OR lower(name)=lower(%s)",
                (normalize_text(skill).replace(" ", "-"), skill),
            ).fetchone()
            if row:
                conn.execute("DELETE FROM user_skills WHERE profile_id=%s AND skill_id=%s", (profile_id, row[0]))
        version = conn.execute(
            "SELECT COALESCE(MAX(version_number), 0) + 1 FROM profile_versions WHERE profile_id=%s",
            (profile_id,),
        ).fetchone()[0]
        current_skills = dict(conn.execute(
            "SELECT s.name, us.level FROM user_skills us JOIN skills s ON s.id=us.skill_id WHERE us.profile_id=%s",
            (profile_id,),
        ).fetchall())
        conn.execute(
            "INSERT INTO profile_versions(profile_id,version_number,snapshot,change_reason) VALUES (%s,%s,%s,%s)",
            (profile_id, version, json.dumps({"name": name, "education": education, "target_roles": areas, "preferred_locations": locations, "preferred_work_modes": work_modes, "skills": current_skills}), reason or "explicit profile update"),
        )
        conn.commit()
    recompute_scores(profile_id)
    return str(profile_id)


def recompute_scores(profile_id: str) -> int:
    """Compute evidence outside transactions and replace only unchanged input revisions."""
    from collections import defaultdict

    from radar import cv_targets
    from radar.db.queries import get_profile
    from radar.markets import backfill_market
    from radar.scoring import SCORING_VERSION, profile_fingerprint, scoring_profile

    pack = active_pack()
    backfill_market(pack.id)
    weights = effective_weights(pack)
    account = get_profile()
    if not account or account["id"] != str(profile_id):
        return 0
    profile = scoring_profile(account, cv_targets.load_profile())
    profile["skill_aliases"] = pack.skill_aliases
    revision = profile_fingerprint(profile, weights, pack.id)
    with connection() as conn:
        updated_at = conn.execute("SELECT updated_at FROM user_profile WHERE id=%s", (profile_id,)).fetchone()[0]
        jobs = conn.execute(
            """SELECT j.id,j.title,j.location,j.work_mode,j.description_raw,j.content_hash,
            json_extract(m.areas,'$[0].name'),m.skills
            FROM jobs j JOIN job_market_classifications m ON m.job_id=j.id AND m.market_id=%s
            WHERE j.is_active=1 AND j.duplicate_status='canonical'""", (pack.id,)
        ).fetchall()
        skills = defaultdict(set)
        requirements = defaultdict(dict)
        for row in jobs:
            for item in json.loads(row[7]):
                if item["name"] in pack.skills and pack.skills[item["name"]].type != "soft":
                    skills[row[0]].add(item["name"])
                    requirements[row[0]][item["name"]] = item["requirement_type"]
        jobs = [row[:7] for row in jobs]
    count = 0
    for offset in range(0, len(jobs), 50):
        prepared = []
        for job_id, title, location, work_mode, description, old_hash, area in jobs[offset:offset+50]:
            raw = RawJob("stored", title, None, "", location=location, work_mode=work_mode, description=description)
            result = score_job(raw, {**profile, "skill_requirement_types": requirements[job_id]}, skills[job_id], area, weights)
            result.assessment.update(profile_hash=revision, content_hash=old_hash, market_id=pack.id, weights=weights)
            prepared.append((job_id, old_hash, result))
        # A factual CV or preference edit during computation must not overwrite its newer scores.
        if profile_fingerprint(scoring_profile(get_profile() or {}, cv_targets.load_profile()), effective_weights(), active_pack().id) != revision:
            return count
        with connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for job_id, old_hash, result in prepared:
                changed = conn.execute(
                    """INSERT INTO job_scores(job_id,profile_id,algorithm_version,total_score,area_score,skills_score,
                    seniority_score,education_score,location_score,preference_score,strong_matches,missing_skills,reason,assessment)
                    SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                    WHERE EXISTS (SELECT 1 FROM jobs WHERE id=%s AND content_hash IS %s)
                    AND EXISTS (SELECT 1 FROM user_profile WHERE id=%s AND updated_at IS %s)
                    ON CONFLICT(job_id,profile_id) DO UPDATE SET algorithm_version=excluded.algorithm_version,
                    total_score=excluded.total_score,area_score=excluded.area_score,skills_score=excluded.skills_score,
                    seniority_score=excluded.seniority_score,education_score=excluded.education_score,
                    location_score=excluded.location_score,preference_score=excluded.preference_score,
                    strong_matches=excluded.strong_matches,missing_skills=excluded.missing_skills,
                    reason=excluded.reason,assessment=excluded.assessment,computed_at=now()""",
                    (job_id,profile_id,SCORING_VERSION,result.total,result.area,result.skills,result.seniority,
                     result.education,result.location,result.preference,json.dumps(result.strong_matches),
                     json.dumps(result.missing_skills),result.reason,json.dumps(result.assessment,ensure_ascii=False),
                     job_id,old_hash,profile_id,updated_at),
                ).rowcount
                count += changed
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


def untrack_application(job_id: str) -> bool:
    """Quita el seguimiento de una oferta (p. ej. «Ya postulé» marcado por error). Solo borra tu registro personal,
    nunca la oferta; si había carpeta de postulación, queda como preparada y sin fecha de envío."""
    with connection() as conn:
        row = conn.execute("SELECT id FROM applications WHERE job_id=%s", (job_id,)).fetchone()
        if row is None:
            return False
        conn.execute("DELETE FROM application_events WHERE application_id=%s", (row[0],))
        conn.execute("DELETE FROM applications WHERE id=%s", (row[0],))
        conn.execute("UPDATE application_packages SET status='prepared', applied_at=NULL, updated_at=now() WHERE job_id=%s", (job_id,))
        conn.commit()
    return True


def track_application(job_id: str, status: str = "saved", notes: str | None = None) -> str:
    statuses = {"new", "reviewed", "saved", "ignored", "applied", "responded", "interview", "offer", "rejected", "expired"}
    if status not in statuses:
        raise ValueError(f"status inválido: {status}")
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute("SELECT id, status FROM applications WHERE job_id=%s", (job_id,)).fetchone()
        if existing:
            application_id, previous = existing
            conn.execute("UPDATE applications SET status=%s, notes=COALESCE(%s, notes), applied_at=CASE WHEN %s='applied' THEN COALESCE(applied_at,now()) ELSE applied_at END, updated_at=now() WHERE id=%s", (status, notes, status, application_id))
            if previous != status:
                conn.execute("INSERT INTO application_events(application_id,from_status,to_status,notes) VALUES (%s,%s,%s,%s)", (application_id, previous, status, notes))
        else:
            application_id = conn.execute("INSERT INTO applications(job_id,status,notes,applied_at) VALUES (%s,%s,%s,CASE WHEN %s='applied' THEN now() ELSE NULL END) RETURNING id", (job_id, status, notes, status)).fetchone()[0]
            conn.execute("INSERT INTO application_events(application_id,to_status,notes) VALUES (%s,%s,%s)", (application_id, status, notes))
        stage = {"responded": "contact", "interview": "interview", "offer": "offer"}.get(status)
        if stage:
            conn.execute(
                """INSERT INTO processes (job_id, source_application_id, company, title, url, stage)
                   SELECT j.id, %s, COALESCE(NULLIF(c.name, ''), 'Empresa no indicada'), j.title,
                       (SELECT source_url FROM job_sources WHERE job_id=j.id ORDER BY last_seen_at DESC LIMIT 1),
                       %s
                   FROM jobs j LEFT JOIN companies c ON c.id=j.company_id WHERE j.id=%s
                   ON CONFLICT(job_id) DO UPDATE SET stage=excluded.stage, archived_at=NULL, updated_at=now()
                   WHERE processes.stage <> excluded.stage
                     AND (excluded.stage <> 'contact' OR processes.stage='closed')""",
                (application_id, stage, job_id),
            )
        conn.commit()
    return str(application_id)
