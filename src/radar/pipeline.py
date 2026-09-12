from __future__ import annotations

from radar.db.repository import ingest_jobs
from radar.freshness import DEFAULT_MAX_AGE_DAYS, filter_recent_jobs
from radar.sources.computrabajo import ComputrabajoSource
from radar.sources.jobspy import JobSpySource


def run_ingestion(
    source_name: str,
    query: str,
    location: str | None,
    limit: int = 25,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> dict[str, int]:
    source = ComputrabajoSource() if source_name.lower() == "computrabajo" else JobSpySource()
    jobs = list(source.search(query, location, limit))
    recent_jobs, discarded = filter_recent_jobs(jobs, max_age_days)
    stats = ingest_jobs(recent_jobs)
    stats["discarded_stale_or_undated"] = discarded
    stats["max_age_days"] = max_age_days
    return stats
