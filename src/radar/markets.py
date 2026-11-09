"""Independent, deterministic projections of canonical offers into career markets."""

from __future__ import annotations

import hashlib
import json
import threading
from functools import cache

from radar.careers import list_packs, load_pack
from radar.classification_text import CLASSIFIER_VERSION
from radar.classify import classify
from radar.domain.models import RawJob
from radar.normalize import content_hash
from radar.taxonomy import infer_relevance

_PACK_HASHES: dict[tuple[int, str], tuple[object, str]] = {}


def pack_hash(pack) -> str:
    key = (id(pack), CLASSIFIER_VERSION)
    cached = _PACK_HASHES.get(key)
    if cached is not None and cached[0] is pack:
        return cached[1]
    from dataclasses import asdict

    digest = hashlib.sha256(json.dumps([CLASSIFIER_VERSION, asdict(pack)], sort_keys=True,
                                       default=lambda x: sorted(x)).encode()).hexdigest()
    _PACK_HASHES[key] = (pack, digest)
    return digest


def _projection_values(job_id, raw, pack, version=None):
    classified = classify(raw, pack)
    relevance = infer_relevance(raw, classified.primary_area.value, pack,
                                [area.value for area in classified.secondary_areas])
    areas = [{"name": area.value, "evidence": area.evidence, "confidence": area.confidence}
             for area in [classified.primary_area, *classified.secondary_areas]]
    skills = [{"name": name, "evidence": evidence.evidence, "requirement_type": evidence.requirement_type}
              for name, evidence in classified.skills]
    return (job_id, pack.id, version or pack_hash(pack), content_hash(raw), relevance.tier, relevance.score,
            relevance.evidence, json.dumps(areas, ensure_ascii=False), json.dumps(skills, ensure_ascii=False))


def _write_projection(conn, values, expected_hash=...):
    guard = ""
    parameters = values
    if expected_hash is not ...:
        guard = " WHERE EXISTS (SELECT 1 FROM jobs WHERE id=%s AND content_hash IS %s)"
        parameters = (*values, values[0], expected_hash)
    return conn.execute(
        """INSERT INTO job_market_classifications
        (job_id,market_id,rules_hash,content_hash,relevance_tier,relevance_score,relevance_evidence,areas,skills)
        SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s""" + guard + """
        ON CONFLICT(job_id,market_id) DO UPDATE SET rules_hash=excluded.rules_hash,
        content_hash=excluded.content_hash,relevance_tier=excluded.relevance_tier,
        relevance_score=excluded.relevance_score,relevance_evidence=excluded.relevance_evidence,
        areas=excluded.areas,skills=excluded.skills,computed_at=now()""", parameters,
    ).rowcount


def project_job(conn, job_id: str, raw: RawJob, packs=None) -> None:
    """Replace all derived values atomically with the containing ingestion transaction."""
    for pack in packs if packs is not None else list_packs():
        _write_projection(conn, _projection_values(job_id, raw, pack))


@cache
def _backfill_lock(database: str):
    return threading.Lock()


_BACKFILL_WARM: dict[tuple[str, str], tuple[int, int, str]] = {}


def _db_stamp(db_file) -> tuple[int, int]:
    try:
        db_mtime = db_file.stat().st_mtime_ns
    except OSError:
        db_mtime = 0
    try:
        wal_mtime = db_file.with_name(f"{db_file.name}-wal").stat().st_mtime_ns
    except OSError:
        wal_mtime = 0
    return (db_mtime, wal_mtime)


def backfill_market(market_id: str) -> int:
    """Compute outside DB transactions; serialize rebuilds and write bounded batches.

    Never upgrade a read snapshot into a writer while a capture is writing. A posting
    changed since the snapshot is skipped, so backfill cannot overwrite a newer capture.
    """
    from radar.db.database import connection, database_path

    pack = load_pack(market_id)
    version = pack_hash(pack)
    db_file = database_path().resolve()
    cache_key = (str(db_file), market_id)
    stamp = (*_db_stamp(db_file), version)
    if _BACKFILL_WARM.get(cache_key) == stamp:
        return 0

    def pending():
        with connection() as conn:
            return conn.execute(
                """SELECT j.id,j.title,c.name,j.location,j.description_raw,j.content_hash FROM jobs j
                LEFT JOIN companies c ON c.id=j.company_id
                LEFT JOIN job_market_classifications m ON m.job_id=j.id AND m.market_id=%s
                WHERE m.job_id IS NULL OR m.rules_hash<>%s
                OR (j.content_hash IS NOT NULL AND m.content_hash IS NOT j.content_hash)""", (market_id, version),
            ).fetchall()

    if not pending():
        _BACKFILL_WARM[cache_key] = (*_db_stamp(db_file), version)
        return 0
    changed = 0
    with _backfill_lock(str(db_file)):
        rows = pending()
        for offset in range(0, len(rows), 50):
            prepared = [(_projection_values(job_id, RawJob("stored", title, company, "", location=location,
                                                        description=description), pack, version), old_hash)
                        for job_id, title, company, location, description, old_hash in rows[offset:offset + 50]]
            with connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                for values, expected_hash in prepared:
                    changed += _write_projection(conn, values, expected_hash)
        if not pending():
            _BACKFILL_WARM[cache_key] = (*_db_stamp(db_file), version)
    return changed


def search_profile(market_id: str) -> dict:
    from radar.db.database import connection

    load_pack(market_id)
    with connection() as conn:
        row = conn.execute("SELECT preferences,version FROM market_search_profiles WHERE market_id=%s", (market_id,)).fetchone()
    return {"market_id": market_id, "preferences": json.loads(row[0]) if row else {},
            "version": row[1] if row else 0}


def save_search_profile(market_id: str, preferences: dict) -> dict:
    """Persist search intent separately from the person's factual identity and skills."""
    from radar.db.database import connection

    load_pack(market_id)
    allowed = {"areas", "roles", "locations", "work_modes", "seniority", "excluded_titles"}
    if set(preferences) - allowed:
        raise ValueError("Preferencias desconocidas")
    for value in preferences.values():
        if not isinstance(value, list) or len(value) > 30 or any(not isinstance(x, str) or len(x) > 120 for x in value):
            raise ValueError("Cada preferencia debe ser una lista de hasta 30 textos de 120 caracteres")
    preferences = {key: list(dict.fromkeys(item.strip() for item in values if item.strip()))
                   for key, values in preferences.items()}
    for key, allowed_values in (("work_modes", {"onsite", "hybrid", "remote"}),
                                ("seniority", {"intern", "junior", "mid", "senior"})):
        if set(preferences.get(key, [])) - allowed_values:
            raise ValueError(f"Valores inválidos en {key}")
    with connection() as conn:
        conn.execute(
            """INSERT INTO market_search_profiles(market_id,preferences) VALUES (%s,%s)
            ON CONFLICT(market_id) DO UPDATE SET preferences=excluded.preferences,
            version=market_search_profiles.version+1,updated_at=now()""",
            (market_id, json.dumps(preferences, ensure_ascii=False)),
        )
    return search_profile(market_id)


def market_skills(market_id: str, **filters) -> dict:
    """Summarize only skill evidence from the selected market and search context."""
    from collections import Counter

    from radar.db.database import connection
    from radar.db.queries import get_profile, list_jobs

    rows = list_jobs(limit=None, market_id=market_id, **filters)
    ids = json.dumps([row["id"] for row in rows])
    counts: Counter = Counter()
    required: Counter = Counter()
    with connection() as conn:
        records = conn.execute(
            "SELECT skills FROM job_market_classifications WHERE market_id=%s AND job_id IN (SELECT value FROM json_each(%s))",
            (market_id, ids),
        ).fetchall()
    for record in records:
        evidence = {item["name"]: item for item in json.loads(record[0])}
        counts.update(evidence.keys())
        required.update(name for name, item in evidence.items() if item["requirement_type"] == "required")
    pack = load_pack(market_id)
    levels = (get_profile() or {}).get("skills", {})
    return {"total_jobs": len(rows), "max_age_days": filters.get("max_age_days", 30), "skills": [
        {"name": name, "category": pack.skills[name].category or "other", "skill_type": pack.skills[name].type,
         "job_count": count, "required_count": required[name], "confidence": 0.9,
         "user_level": levels.get(name, "none"), "interest": None, "evidence": None,
         "share": round(count / len(rows), 4) if rows else 0}
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]}
