from __future__ import annotations

from datetime import UTC, datetime

from radar.domain.models import RawJob

DEFAULT_MAX_AGE_DAYS = 14


def is_recent(
    published_at: datetime | None,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    today: datetime | None = None,
) -> bool:
    """Return True only for dated jobs published from today backwards."""
    if max_age_days < 0:
        raise ValueError("max_age_days debe ser mayor o igual a cero")
    if published_at is None:
        return False
    reference_date = (today or datetime.now(UTC)).date()
    age = (reference_date - published_at.date()).days
    return 0 <= age <= max_age_days


def filter_recent_jobs(
    jobs: list[RawJob], max_age_days: int = DEFAULT_MAX_AGE_DAYS
) -> tuple[list[RawJob], int]:
    """Filter undated, future and stale jobs while preserving them upstream."""
    recent = [job for job in jobs if is_recent(job.published_at, max_age_days)]
    return recent, len(jobs) - len(recent)
