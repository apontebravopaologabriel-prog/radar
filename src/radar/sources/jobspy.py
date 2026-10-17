from __future__ import annotations

import math
import os
from datetime import datetime
from typing import Any

from radar.domain.models import RawJob


class JobSpySource:
    name = "JobSpy/Indeed"

    def __init__(self, sites: list[str] | None = None):
        configured = os.getenv("RADAR_JOBSPY_SITES", "indeed,linkedin,google")
        self.sites = sites or [item.strip() for item in configured.split(",") if item.strip()]

    def search(self, query: str, location: str | None = None, limit: int = 25) -> list[RawJob]:
        try:
            from jobspy import scrape_jobs
        except ImportError as exc:
            raise RuntimeError("Instala python-jobspy para habilitar el adaptador JobSpy") from exc
        place = location or "Lima"
        kwargs: dict[str, Any] = {
            "search_term": query,
            "location": place,
            "results_wanted": limit,
            "country_indeed": "Peru",
            "description_format": "markdown",
            "linkedin_fetch_description": "linkedin" in self.sites,
            "verbose": 0,
        }
        if "google" in self.sites:
            kwargs["google_search_term"] = f"{query} empleos en {place}, Perú"
        try:
            frame = scrape_jobs(site_name=self.sites, **kwargs)
            return [self._row_to_job(row) for row in frame.to_dict(orient="records")]
        except Exception:
            if len(self.sites) <= 1:
                raise
            collected: list[RawJob] = []
            for site in self.sites:
                try:
                    site_kwargs = {**kwargs, "linkedin_fetch_description": site == "linkedin"}
                    frame = scrape_jobs(site_name=[site], **site_kwargs)
                    collected.extend(self._row_to_job(row) for row in frame.to_dict(orient="records"))
                except Exception:  # noqa: BLE001, S112 - un portal aislado con fallo no aborta los demás
                    continue
            return collected

    def _row_to_job(self, row: dict[str, Any]) -> RawJob:
        published = self._clean(row.get("date_posted"))
        if published and not isinstance(published, datetime):
            published = datetime.fromisoformat(str(published))
        is_remote = self._clean(row.get("is_remote"))
        site = str(self._clean(row.get("site")) or "").strip().lower()
        source_map = {
            "indeed": "JobSpy/Indeed",
            "linkedin": "JobSpy/LinkedIn",
            "google": "JobSpy/Google",
            "glassdoor": "JobSpy/Glassdoor",
        }
        source_name = source_map.get(site, self.name)
        return RawJob(
            source=source_name,
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
