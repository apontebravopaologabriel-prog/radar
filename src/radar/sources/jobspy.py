from __future__ import annotations

import math
import os
from datetime import datetime
from typing import Any

from radar.domain.models import RawJob


class JobSpySource:
    name = "JobSpy/Indeed"

    def __init__(self, sites: list[str] | None = None):
        configured = os.getenv("RADAR_JOBSPY_SITES", "indeed")
        self.sites = sites or [item.strip() for item in configured.split(",") if item.strip()]

    def search(self, query: str, location: str | None = None, limit: int = 25) -> list[RawJob]:
        try:
            from jobspy import scrape_jobs
        except ImportError as exc:
            raise RuntimeError("Instala python-jobspy para habilitar el adaptador JobSpy") from exc
        frame = scrape_jobs(
            site_name=self.sites,
            search_term=query,
            location=location,
            results_wanted=limit,
            country_indeed="Peru",
            description_format="markdown",
            verbose=0,
        )
        return [self._row_to_job(row) for row in frame.to_dict(orient="records")]

    def _row_to_job(self, row: dict[str, Any]) -> RawJob:
        published = self._clean(row.get("date_posted"))
        if published and not isinstance(published, datetime):
            published = datetime.fromisoformat(str(published))
        is_remote = self._clean(row.get("is_remote"))
        return RawJob(
            source=self.name,
            title=str(self._clean(row.get("title")) or "Sin título"),
            company=self._clean(row.get("company")),
            url=str(self._clean(row.get("job_url")) or self._clean(row.get("job_url_direct")) or ""),
            external_id=self._clean(row.get("id")) or self._clean(row.get("job_id")),
            location=self._clean(row.get("location"))
            or ", ".join(filter(None, (self._clean(row.get("city")), self._clean(row.get("state"))))),
            description=self._clean(row.get("description")),
            published_at=published,
            salary_min=self._clean(row.get("min_amount")),
            salary_max=self._clean(row.get("max_amount")),
            salary_currency=self._clean(row.get("currency")),
            salary_period=self._clean(row.get("interval")),
            employment_type=self._clean(row.get("job_type")),
            work_mode="remote" if is_remote else "unknown",
            raw_payload={key: self._clean(value) for key, value in row.items()},
        )

    @staticmethod
    def _clean(value: Any) -> Any:
        """JobSpy returns pandas NaN for missing optional values."""
        try:
            if math.isnan(value):
                return None
        except (TypeError, ValueError):
            pass
        return value
