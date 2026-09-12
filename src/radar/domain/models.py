from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class RawJob:
    source: str
    title: str
    company: str | None
    url: str
    external_id: str | None = None
    location: str | None = None
    description: str | None = None
    published_at: datetime | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    employment_type: str | None = None
    hours_per_week: float | None = None
    schedule_text: str | None = None
    work_mode: str | None = None
    application_status: str = "unknown"
    application_checked_at: datetime | None = None
    application_status_source: str = "unknown"
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Evidence:
    value: str
    confidence: float
    evidence: str
    requirement_type: str = "unknown"


@dataclass(slots=True)
class ClassifiedJob:
    primary_area: Evidence
    secondary_areas: list[Evidence] = field(default_factory=list)
    skills: list[tuple[str, Evidence]] = field(default_factory=list)
    requirements: list[Evidence] = field(default_factory=list)
