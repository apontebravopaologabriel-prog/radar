from __future__ import annotations

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
) -> dict[str, int]:
    source = resolve_source(source_name)
    jobs = list(source.search(query, location, limit))
    recent_jobs, discarded = filter_recent_jobs(jobs, max_age_days)
    stats = ingest_jobs(recent_jobs)
    stats["discarded_stale_or_undated"] = discarded
    stats["max_age_days"] = max_age_days
    return stats
