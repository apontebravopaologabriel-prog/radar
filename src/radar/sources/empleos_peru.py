from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any

from radar.domain.models import RawJob

BASE_URL = "https://mtpe-candidatos.empleosperu.gob.pe"
REQUEST_TIMEOUT = 20.0

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def _strip_html(raw: str | None) -> str:
    if not raw:
        return ""
    text = re.sub(r"<br\s*/?>|</p>|</li>", "\n", str(raw), flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


class EmpleosPeruSource:
    """Adaptador público sin sesión para Empleos Perú (MTPE - mtpe-candidatos.empleosperu.gob.pe)."""

    name = "Empleos Perú"

    def __init__(self, base_url: str = BASE_URL, timeout: float = REQUEST_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def search(self, query: str, location: str | None = None, limit: int = 25) -> list[RawJob]:
        items = self._search_api(query, location, limit)
        if not items:
            items = self._search_html(query, location, limit)
        return [self._to_job(item) for item in items[:limit]]

    def _search_api(self, query: str, location: str | None, limit: int) -> list[dict[str, Any]]:
        clean_limit = min(max(limit, 1), 50)
        # Search by positionTitle first
        search_words = [w.strip() for w in query.split() if len(w.strip()) > 3]
        term = search_words[0] if search_words else query.strip()
        endpoints = [
            f"{self.base_url}/api/jobs?positionTitle={urllib.parse.quote(term)}&limit={clean_limit}",
            f"{self.base_url}/api/jobs?positionTitle={urllib.parse.quote(query)}&limit={clean_limit}",
            f"{self.base_url}/api/jobs?what={urllib.parse.quote(query)}&limit={clean_limit}",
            f"{self.base_url}/api/jobs?limit={clean_limit}",
        ]
        for url in endpoints:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": _USER_AGENT,
                    "Accept": "application/json, text/plain, */*",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                    data = json.loads(raw)
                    items = self._extract_jobs(data)
                    if items:
                        return items
            except (urllib.error.URLError, TimeoutError, ValueError, OSError):
                continue
        return []

    def _search_html(self, query: str, location: str | None, limit: int) -> list[dict[str, Any]]:
        params = urllib.parse.urlencode({"q": query, "ubicacion": location or "Lima"})
        req = urllib.request.Request(
            f"{self.base_url}/search-jobs?{params}",
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                page = resp.read().decode("utf-8", errors="replace")
                return self._extract_from_html(page, base_url=self.base_url)[:limit]
        except (urllib.error.URLError, TimeoutError, OSError):
            return []

    @staticmethod
    def _extract_jobs(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        for key in ("data", "vacantes", "convocatorias", "content", "items", "results", "jobs"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                for inner in ("content", "vacantes", "items", "results", "data"):
                    inner_val = value.get(inner)
                    if isinstance(inner_val, list):
                        return [item for item in inner_val if isinstance(item, dict)]
        return []

    @classmethod
    def _extract_from_html(cls, html_text: str, base_url: str = BASE_URL) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        for match in re.finditer(
            r'<a[^>]+href=["\'](?P<href>[^"\']*?(?:vacante|convocatoria|vacancy|jobs)[^"\']*?(?P<id>[a-zA-Z0-9_\-]+)[^"\']*)["\'][^>]*>(?P<body>.*?)</a>',
            html_text,
            flags=re.DOTALL | re.IGNORECASE,
        ):
            href = match.group("href")
            url = href if href.startswith("http") else f"{base_url.rstrip('/')}/{href.lstrip('/')}"
            body = _strip_html(match.group("body"))
            lines = [line.strip() for line in body.splitlines() if line.strip()]
            jobs.append(
                {
                    "id": match.group("id"),
                    "titulo": lines[0] if lines else "Vacante en Empleos Perú",
                    "url": url,
                    "descripcion": "\n".join(lines[1:]) if len(lines) > 1 else None,
                }
            )
        return jobs

    def _to_job(self, item: dict[str, Any]) -> RawJob:
        offer_id = (
            str(
                item.get("id")
                or item.get("idVacante")
                or item.get("codigoVacante")
                or item.get("offerId")
                or ""
            ).strip()
            or None
        )
        raw_url = item.get("url") or item.get("urlDetalle") or item.get("link")
        if raw_url and str(raw_url).startswith("/"):
            url = f"{self.base_url}{raw_url}"
        elif raw_url:
            url = str(raw_url)
        elif offer_id:
            url = f"{self.base_url}/search-jobs/vacancy-details/{offer_id}"
        else:
            url = ""

        title = _strip_html(
            item.get("positionTitle") or item.get("titulo") or item.get("title") or item.get("puesto")
        ) or "Sin título"
        company = (
            item.get("companyName")
            or item.get("empresa")
            or item.get("company")
            or item.get("razonSocial")
            or item.get("nombreEmpresa")
        )
        location = (
            item.get("ubicacion")
            or item.get("location")
            or ", ".join(filter(None, (item.get("distrito"), item.get("provincia"), item.get("departamento"))))
            or "Lima"
        )
        if isinstance(location, dict):
            location = "Lima"

        detail = _strip_html(
            item.get("jobDescription")
            or item.get("companyDescription")
            or item.get("descripcion")
            or item.get("description")
            or item.get("funciones")
            or item.get("requisitos")
        )

        contract = item.get("contractType")
        workday_name = contract.get("name") if isinstance(contract, dict) else (item.get("tipoJornada") or item.get("employmentType"))

        hours = item.get("hoursPerWeek")
        hours_name = hours.get("name") if isinstance(hours, dict) else None

        salary_min = item.get("salaryMin") or item.get("remuneracionMinima")
        salary_max = item.get("salaryMax") or item.get("remuneracionMaxima")
        salary_packages = item.get("offeredRemunerationPackages")
        if isinstance(salary_packages, list) and salary_packages and salary_min is None:
            first_pkg = salary_packages[0]
            if isinstance(first_pkg, dict):
                pkg_min = first_pkg.get("minimumAmount")
                pkg_max = first_pkg.get("maximumAmount")
                if isinstance(pkg_min, (int, float)) and pkg_min > 0:
                    salary_min = float(pkg_min)
                if isinstance(pkg_max, (int, float)) and pkg_max > 0:
                    salary_max = float(pkg_max)

        salary_raw = item.get("remuneracion") or item.get("salario") or item.get("salary")
        if isinstance(salary_raw, (int, float)) and salary_min is None:
            salary_min = float(salary_raw)

        modality = item.get("modalidad") or item.get("workMode")
        extra_lines = [
            f"Modalidad: {modality}" if modality else None,
            f"Jornada: {workday_name}" if workday_name else None,
            f"Horas: {hours_name}" if hours_name else None,
            f"Remuneración: {salary_min} a {salary_max}" if salary_min and salary_max else (f"Remuneración: {salary_min}" if salary_min else None),
        ]
        description = "\n".join(filter(None, [detail, *[line for line in extra_lines if line]])) or None

        published = self._parse_published_at(
            item.get("datePosted") or item.get("fechaPublicacion") or item.get("publishedAt")
        )
        return RawJob(
            source=self.name,
            title=title,
            company=str(company).strip() if company else None,
            url=url,
            external_id=offer_id,
            location=str(location).strip() if location else "Lima",
            description=description,
            published_at=published,
            salary_min=float(salary_min) if isinstance(salary_min, (int, float)) else None,
            salary_max=float(salary_max) if isinstance(salary_max, (int, float)) else None,
            salary_currency=item.get("salaryCurrency") or item.get("moneda") or ("PEN" if salary_min else None),
            employment_type=str(workday_name) if workday_name else None,
            work_mode=str(modality) if modality else None,
            raw_payload=item,
        )

    @staticmethod
    def _parse_published_at(value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        text = str(value).strip().lower()
        now = datetime.now(UTC)
        if text in {"hoy", "today"}:
            return now
        if text == "ayer":
            return now - timedelta(days=1)
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(text[:10], fmt).replace(tzinfo=UTC)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(text.replace("z", "+00:00"))
        except ValueError:
            return None
