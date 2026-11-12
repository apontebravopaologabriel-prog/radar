"""Deterministic market questions over the same active offers as the map."""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from radar.careers import CareerPackError, load_pack
from radar.db.database import connection
from radar.db.queries import list_jobs
from radar.freshness import PERU_UTC_OFFSET_HOURS, visible_date_bounds
from radar.geolocation import infer_location, with_location
from radar.normalize import normalize_text

router = APIRouter(prefix="/api/analytics", tags=["analysis"])
Dimension = Literal["area", "skill", "seniority", "work_mode", "district", "company", "source", "publication", "salary"]


class AnalysisScope(BaseModel):
    market_id: str = "industrial_engineering"
    geo_scope: Literal["lima_callao"] | None = None
    profile_mode: Literal["market", "saved"] = "market"
    max_age_days: int = Field(default=7, ge=1, le=365)
    search: str | None = None
    area: str | None = None
    skill: str | None = None
    source: str | None = None
    seniority: str | None = None
    work_mode: str | None = None
    relevance_tier: str | None = "market"
    min_salary: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    max_salary: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    district: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    radius_km: float | None = Field(default=None, gt=0, le=100, allow_inf_nan=False)
    empty: bool = False

    @model_validator(mode="after")
    def validate_scope(self):
        if self.min_salary is not None and self.max_salary is not None and self.min_salary > self.max_salary:
            raise ValueError("El mínimo no puede superar el máximo")
        geo = (self.latitude, self.longitude, self.radius_km)
        if any(v is not None for v in geo) and not all(v is not None for v in geo):
            raise ValueError("El radio necesita latitud y longitud")
        if self.district and self.radius_km is not None:
            raise ValueError("Elige distrito o radio")
        return self


class Breakdown(BaseModel):
    value: str
    count: int


class SalaryGroup(BaseModel):
    currency: str
    period: str
    count: int
    median: float
    bins: list[Breakdown]


class Overview(BaseModel):
    scope: AnalysisScope
    start_date: str
    end_date: str
    total: int
    employers: int
    salary_count: int
    salary_share: float
    areas: list[Breakdown]
    skills: list[Breakdown]
    skill_groups: dict[str, list[Breakdown]]
    seniorities: list[Breakdown]
    work_modes: list[Breakdown]
    districts: list[Breakdown]
    companies: list[Breakdown]
    sources: list[Breakdown]
    publications: list[Breakdown]
    salaries: list[SalaryGroup]


def publication_day(value: str) -> str:
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo:
        stamp = stamp.astimezone(timezone(timedelta(hours=PERU_UTC_OFFSET_HOURS)))
    return stamp.date().isoformat()


def _distance(latitude: float, longitude: float, job: dict) -> float:
    delta_lat = math.radians(job["latitude"] - latitude)
    delta_lon = math.radians(job["longitude"] - longitude)
    h = math.sin(delta_lat / 2) ** 2 + math.cos(math.radians(latitude)) * math.cos(math.radians(job["latitude"])) * math.sin(delta_lon / 2) ** 2
    return 2 * 6371 * math.atan2(math.sqrt(h), math.sqrt(max(0, 1 - h)))


def scoped_jobs(scope: AnalysisScope) -> list[dict[str, Any]]:
    filters = scope.model_dump(exclude={"district", "latitude", "longitude", "radius_km", "empty"})
    try:
        rows = list_jobs(limit=None, include_applied=False, include_hidden=False, **filters)
    except (CareerPackError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    if scope.empty:
        return []
    target = infer_location(scope.district) if scope.district else None
    if scope.district and (not target or target.precision != "district"):
        return []
    result = []
    for row in rows:
        if row.get("user_application") == "ignored":
            continue
        job = with_location(row)
        if target and job["district"] != target.label:
            continue
        if scope.radius_km is not None:
            if job["latitude"] is None or job["longitude"] is None:
                continue
            if _distance(scope.latitude, scope.longitude, job) > scope.radius_km:
                continue
        result.append(job)
    return result


def _salary_period(value: str | None) -> str:
    """Normalize explicit equivalent units without inventing a missing period."""
    value = (value or "").strip().lower()
    aliases = {
        "month": {"month", "monthly", "mes", "mensual", "mensuales"},
        "year": {"year", "yearly", "annual", "annually", "anual", "anuales", "año"},
        "week": {"week", "weekly", "semana", "semanal", "semanales"},
        "day": {"day", "daily", "día", "diario", "diaria", "diarios", "diarias"},
        "hour": {"hour", "hourly", "hora", "por hora"},
        "fortnight": {"fortnight", "quincena", "quincenal", "quincenales"},
    }
    return next((unit for unit, names in aliases.items() if value in names), value or "unknown")


def _annotated_jobs(scope: AnalysisScope) -> list[dict[str, Any]]:
    rows = scoped_jobs(scope)
    # Keep SQLite's variable limit safe on all supported platforms.
    with connection() as conn:
        for start in range(0, len(rows), 400):
            batch = rows[start:start + 400]
            ids = [job["id"] for job in batch]
            placeholders = ",".join("%s" for _ in ids)
            metadata = {
                str(row[0]): (row[1], json.loads(row[2]))
                for row in conn.execute(
                    f"SELECT j.id,j.salary_period,m.skills FROM jobs j JOIN job_market_classifications m "
                    f"ON m.job_id=j.id AND m.market_id=%s WHERE j.id IN ({placeholders})",
                    [scope.market_id, *ids],
                ).fetchall()
            }
            sources: dict[str, set[str]] = defaultdict(set)
            for job_id, name in conn.execute(
                f"SELECT js.job_id,s.name FROM job_sources js JOIN sources s ON s.id=js.source_id "
                f"WHERE js.job_id IN ({placeholders})", ids,
            ).fetchall():
                sources[str(job_id)].add(name)
            for job in batch:
                period, skills = metadata.get(job["id"], (None, []))
                job["skill_types"] = {item["name"]: item.get("skill_type") for item in skills}
                job["skills"] = sorted(job["skill_types"])
                job["sources"] = sorted(sources[job["id"]])
                job["publication"] = publication_day(job["published_at"])
                job["salary_period"] = _salary_period(period)
                job["salary_currency"] = job["salary_currency"] or "unknown"
    return rows


def _breakdown(values) -> list[Breakdown]:
    counts = Counter(value for value in values if value)
    return [Breakdown(value=value, count=count) for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def _salary_midpoint(job: dict) -> float | None:
    low, high = job["salary_min"], job["salary_max"]
    values = [v for v in (low, high) if v is not None]
    if not values or any(not math.isfinite(v) or v <= 0 for v in values) or (low is not None and high is not None and low > high):
        return None
    return sum(values) / len(values)


def _salary_bin(value: float) -> str:
    if value < 1500:
        return "< 1,500"
    if value < 2500:
        return "1,500–2,499"
    if value < 4000:
        return "2,500–3,999"
    if value < 6000:
        return "4,000–5,999"
    return "6,000+"


_ANONYMOUS_COMPANY = re.compile(
    r"(?:importante empresa(?: del sector(?: .*)?)?|(?:empresa )?confidencial|no indicad[ao]|sin nombre)"
)


def _identified_company(name: str | None) -> bool:
    normalized = normalize_text(name).strip(" .,:;–-")
    return bool(normalized) and _ANONYMOUS_COMPANY.fullmatch(normalized) is None


_SKILL_GROUPS = {"technical": "technical", "methodology": "knowledge", "domain": "knowledge",
                 "soft": "soft", "language": "language"}


def _skill_groups(scope: AnalysisScope, rows: list[dict]) -> dict[str, list[Breakdown]]:
    # Older projections contain the detected name but omit its type.
    catalog = {normalize_text(name): skill for name, skill in load_pack(scope.market_id).skills.items()}
    names: dict[str, list[str]] = defaultdict(list)
    for job in rows:
        for name, kind in job["skill_types"].items():
            skill = catalog.get(normalize_text(name))
            catalog_kind = skill.type if skill else None
            group = (skill.analysis_group if skill and skill.analysis_group in {"technical", "knowledge"} else None)
            group = group or _SKILL_GROUPS.get(catalog_kind) or _SKILL_GROUPS.get(kind, "other")
            names[group].append(name)
    return {group: _breakdown(values) for group, values in names.items()}


def _overview(scope: AnalysisScope, rows: list[dict]) -> Overview:
    start, end = visible_date_bounds(scope.max_age_days)
    last = (datetime.fromisoformat(end) - timedelta(days=1)).date().isoformat()
    days = Counter(job["publication"] for job in rows)
    publications = [Breakdown(value=(datetime.fromisoformat(start) + timedelta(days=i)).date().isoformat(),
                              count=days[(datetime.fromisoformat(start) + timedelta(days=i)).date().isoformat()])
                    for i in range(scope.max_age_days)]
    salaries: dict[tuple[str, str], list[float]] = defaultdict(list)
    for job in rows:
        midpoint = _salary_midpoint(job)
        if midpoint is not None:
            salaries[(job["salary_currency"], job["salary_period"])].append(midpoint)
    groups = []
    for (currency, period), values in sorted(salaries.items()):
        values.sort()
        n = len(values)
        median = (values[(n - 1) // 2] + values[n // 2]) / 2
        counts = Counter(_salary_bin(v) for v in values)
        groups.append(SalaryGroup(currency=currency, period=period, count=n, median=median,
                                  bins=[Breakdown(value=label, count=counts[label]) for label in ("< 1,500", "1,500–2,499", "2,500–3,999", "4,000–5,999", "6,000+")]))
    salary_count = sum(g.count for g in groups)
    companies = _breakdown(job["company"] for job in rows if _identified_company(job["company"]))
    return Overview(
        scope=scope, start_date=start, end_date=last, total=len(rows),
        employers=len(companies), salary_count=salary_count,
        salary_share=salary_count / len(rows) if rows else 0,
        areas=_breakdown(job["primary_area"] or "No indicada" for job in rows),
        skills=_breakdown(skill for job in rows for skill in job["skills"]),
        skill_groups=_skill_groups(scope, rows),
        seniorities=_breakdown(job["seniority"] or "unknown" for job in rows),
        work_modes=_breakdown(job["work_mode"] or "unknown" for job in rows),
        districts=_breakdown(job["district"] or "Sin distrito" for job in rows),
        companies=companies,
        sources=_breakdown(source for job in rows for source in job["sources"]),
        publications=publications, salaries=groups,
    )


@router.get("/overview", response_model=Overview)
def overview(scope: Annotated[AnalysisScope, Query()]):
    return _overview(scope, _annotated_jobs(scope))


def matching_jobs(scope: AnalysisScope, dimension: Dimension | None, value: str | None) -> list[dict]:
    rows = _annotated_jobs(scope)
    if dimension is None:
        return rows
    def matches(job):
        if dimension in {"skill", "source"}:
            return value in job["skills" if dimension == "skill" else "sources"]
        if dimension == "salary":
            midpoint = _salary_midpoint(job)
            return midpoint is not None and value == json.dumps([job["salary_currency"], job["salary_period"], _salary_bin(midpoint)], ensure_ascii=False, separators=(",", ":"))
        column, fallback = {"area": ("primary_area", "No indicada"), "company": ("company", "No indicada"),
                            "district": ("district", "Sin distrito"), "publication": ("publication", ""),
                            "seniority": ("seniority", "unknown"), "work_mode": ("work_mode", "unknown")}[dimension]
        return (job[column] or fallback) == value
    return [job for job in rows if matches(job)]
