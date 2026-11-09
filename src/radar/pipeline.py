from __future__ import annotations

import json

from radar.careers import active_pack, list_packs, load_pack
from radar.db.database import connection
from radar.db.repository import ingest_jobs
from radar.freshness import DEFAULT_MAX_AGE_DAYS, filter_recent_jobs
from radar.sources.base import JobSource
from radar.sources.bumeran import BumeranSource
from radar.sources.computrabajo import ComputrabajoSource
from radar.sources.empleos_peru import EmpleosPeruSource
from radar.sources.jobspy import JobSpySource


def resolve_source(source_name: str) -> JobSource:
    key = source_name.strip().lower()
    if key == "computrabajo":
        return ComputrabajoSource()
    if key in {"bumeran", "laborum"}:
        return BumeranSource()
    if key in {"empleos", "empleos_peru", "empleosperu"}:
        return EmpleosPeruSource()
    if key in {"indeed", "linkedin", "google", "glassdoor"}:
        return JobSpySource(sites=[key])
    return JobSpySource()


def run_ingestion(
    source_name: str,
    query: str,
    location: str | None,
    limit: int = 25,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    *, search_timeout: float | None = None, market_ids: list[str] | None = None,
) -> dict[str, int]:
    pack = active_pack()
    context = {"source": source_name, "location": location, "limit": limit,
               "max_age_days": max_age_days, "reference_market_id": pack.id,
               "requested_market_ids": [load_pack(key).id for key in market_ids] if market_ids else [pack.id]}
    from radar.classification_text import CLASSIFIER_VERSION
    from radar.markets import pack_hash

    context["classifier_version"] = CLASSIFIER_VERSION
    context["classification_rules_hashes"] = {p.id: pack_hash(p) for p in list_packs()}
    with connection() as conn:
        run = conn.execute("INSERT INTO ingestion_runs(query,context) VALUES (%s,%s) RETURNING id",
                           (query, json.dumps(context))).fetchone()[0]
    try:
        source = resolve_source(source_name)
        fetch = lambda: list(source.search(query, location, limit))
        if search_timeout is not None:
            from radar.source_fetch import fetch_jobs

            jobs = fetch_jobs(source_name, query, location, limit, search_timeout)
        else:
            jobs = fetch()
        recent_jobs, discarded = filter_recent_jobs(jobs, max_age_days)
        with connection() as conn:
            conn.execute("UPDATE ingestion_runs SET jobs_found=%s WHERE id=%s", (len(jobs), run))
        stats = ingest_jobs(recent_jobs, pack, run_id=run)
    except Exception as exc:
        with connection() as conn:
            conn.execute("UPDATE ingestion_runs SET status=%s,finished_at=now(),errors=%s WHERE id=%s",
                         ("timeout" if isinstance(exc, TimeoutError) else "failed", json.dumps([str(exc)]), run))
        raise
    stats["discarded_stale_or_undated"] = discarded
    stats["max_age_days"] = max_age_days
    return stats
