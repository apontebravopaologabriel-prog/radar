from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any

from radar.domain.models import RawJob

BASE_URL = "https://www.bumeran.com.pe"
SEARCH_API_URL = f"{BASE_URL}/api/avisos/searchV2"
REQUEST_TIMEOUT = 20.0
# The public search matches every term (AND), so a long phrase of the pack returns nothing even when the
# market has offers for that role. Retry with progressively shorter prefixes before reporting an empty page.
QUERY_WORD_LIMITS = (4, 3, 2)
_STOPWORDS = frozenset({"de", "del", "la", "el", "los", "las", "y", "e", "en", "para", "con", "a", "al", "por"})

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", " ", text.lower())
    return re.sub(r"[\s_]+", "-", cleaned).strip("-")


class BumeranUnavailable(RuntimeError):
    """Bumeran did not answer at all. An answer without offers is still a successful, empty search."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _query_variants(query: str) -> list[str]:
    """La frase completa y luego prefijos más cortos, sin dejar de ser una consulta con sentido."""
    words = query.split()
    variants = [query]
    for size in QUERY_WORD_LIMITS:
        if size >= len(words):
            continue
        head = words[:size]
        while head and head[-1].lower() in _STOPWORDS:
            head.pop()
        if len([word for word in head if word.lower() not in _STOPWORDS]) < 2:
            continue
        candidate = " ".join(head)
        if candidate.lower() not in {variant.lower() for variant in variants}:
            variants.append(candidate)
    return variants


def _strip_html(raw: str | None) -> str:
    if not raw:
        return ""
    text = re.sub(r"<br\s*/?>|</p>|</li>", "\n", str(raw), flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


class BumeranSource:
    """Adaptador público sin sesión para Bumeran Perú (bumeran.com.pe)."""

    name = "Bumeran"

    def __init__(self, base_url: str = BASE_URL, timeout: float = REQUEST_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def search(self, query: str, location: str | None = None, limit: int = 25) -> list[RawJob]:
        for text in _query_variants(query):
            errors: list[Exception] = []
            answered = False
            for fetch in (self._search_api, self._search_html):
                try:
                    items = fetch(text, location, limit)
                except Exception as exc:  # noqa: BLE001 - decided below: an answer or a source failure
                    errors.append(exc)
                    continue
                answered = True
                if items:
                    return [self._to_job(item) for item in items[:limit]]
            if not answered:
                # Shortening the phrase cannot fix a portal that is not answering; fail the step instead
                # of reporting an empty market (docs/data-sources.md).
                raise BumeranUnavailable(f"Bumeran no respondió: {str(errors[-1])[:200]}",
                                         getattr(errors[-1], "code", None)) from errors[-1]
        return []

    def _search_api(self, query: str, location: str | None, limit: int) -> list[dict[str, Any]]:
        search_text = f"{query} {location}".strip() if location and location.lower() != "lima" else query
        payload = json.dumps(
            {
                "pageSize": min(max(limit, 1), 50),
                "page": 0,
                "sort": "RECIENTES",
                "query": search_text,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/avisos/searchV2?pageSize={min(max(limit, 1), 50)}&page=0&sort=RECIENTES",
            data=payload,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "x-site-id": "BMPE",
                "Origin": self.base_url,
                "Referer": f"{self.base_url}/empleos.html",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
            return self._extract_jobs(data)

    def _search_html(self, query: str, location: str | None, limit: int) -> list[dict[str, Any]]:
        slug = _slugify(query)
        loc_slug = _slugify(location) if location else ""
        path = (
            f"/empleos-busqueda-{slug}-en-{loc_slug}.html"
            if loc_slug and loc_slug != "peru"
            else f"/empleos-busqueda-{slug}.html"
        )
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "es-PE,es;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            page = resp.read().decode("utf-8", errors="replace")
            return self._extract_from_html(page, base_url=self.base_url)[:limit]

    @staticmethod
    def _extract_jobs(payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            return []
        for key in ("content", "avisos", "jobs", "results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        data = payload.get("data")
        if isinstance(data, dict):
            for key in ("content", "avisos", "jobs", "results"):
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []

    @classmethod
    def _extract_from_html(cls, html_text: str, base_url: str = BASE_URL) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        # 1. JSON-LD JobPosting blocks
        for match in re.finditer(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html_text,
            flags=re.DOTALL | re.IGNORECASE,
        ):
            try:
                block = json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                continue
            entries = block if isinstance(block, list) else [block]
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                if entry.get("@type") == "JobPosting":
                    org = entry.get("hiringOrganization")
                    company = org.get("name") if isinstance(org, dict) else None
                    loc = entry.get("jobLocation")
                    loc_label = None
                    if isinstance(loc, dict):
                        addr = loc.get("address")
                        if isinstance(addr, dict):
                            loc_label = ", ".join(
                                filter(None, (addr.get("addressLocality"), addr.get("addressRegion")))
                            )
                    jobs.append(
                        {
                            "id": str(entry.get("identifier", {}).get("value") or entry.get("url") or ""),
                            "title": entry.get("title"),
                            "company": company,
                            "url": entry.get("url"),
                            "location": loc_label,
                            "description": entry.get("description"),
                            "publishedAt": entry.get("datePosted"),
                            "employmentType": entry.get("employmentType"),
                        }
                    )
        if jobs:
            return jobs

        # 2. Anchor cards linking to /empleos/<slug>-<id>.html
        seen_urls: set[str] = set()
        for match in re.finditer(
            r'<a[^>]+href=["\'](?P<href>(?:https://www\.bumeran\.com\.pe)?/empleos/[^"\']+?-(?P<id>\d+)\.html)["\'][^>]*>(?P<body>.*?)</a>',
            html_text,
            flags=re.DOTALL | re.IGNORECASE,
        ):
            href = match.group("href")
            url = href if href.startswith("http") else f"{base_url.rstrip('/')}{href}"
            if url in seen_urls:
                continue
            seen_urls.add(url)
            body = _strip_html(match.group("body"))
            lines = [line.strip() for line in body.splitlines() if line.strip()]
            title = lines[0] if lines else "Oferta en Bumeran"
            jobs.append(
                {
                    "id": match.group("id"),
                    "title": title,
                    "url": url,
                    "description": "\n".join(lines[1:]) if len(lines) > 1 else None,
                }
            )
        return jobs

    def _to_job(self, item: dict[str, Any]) -> RawJob:
        offer_id = str(item.get("id") or item.get("idAviso") or item.get("offerId") or "").strip() or None
        raw_url = item.get("url") or item.get("link") or item.get("detalleUrl")
        if raw_url and str(raw_url).startswith("/"):
            url = f"{self.base_url}{raw_url}"
        elif raw_url:
            url = str(raw_url)
        elif offer_id:
            slug = _slugify(str(item.get("titulo") or item.get("title") or "empleo"))
            url = f"{self.base_url}/empleos/{slug}-{offer_id}.html"
        else:
            url = ""

        title = _strip_html(item.get("titulo") or item.get("title")) or "Sin título"
        company = (
            item.get("empresa")
            or item.get("company")
            or item.get("nombreEmpresa")
            or (item.get("empresaData") or {}).get("nombre")
        )
        location = (
            item.get("localizacion")
            or item.get("location")
            or item.get("ubicacion")
            or ", ".join(filter(None, (item.get("ciudad"), item.get("provincia"), item.get("departamento"))))
            or "Lima"
        )
        detail = _strip_html(
            item.get("detalle") or item.get("description") or item.get("descripcion") or item.get("resumen")
        )
        modality = item.get("modalidadTrabajo") or item.get("modality") or item.get("workMode")
        workday = item.get("tipoTrabajo") or item.get("employmentType") or item.get("workday")
        salary_label = item.get("salario") or item.get("salary")
        extra_lines = [
            f"Modalidad: {modality}" if modality else None,
            f"Jornada: {workday}" if workday else None,
            f"Salario: {salary_label}" if salary_label else None,
        ]
        description = "\n".join(filter(None, [detail, *[line for line in extra_lines if line]])) or None
        published = self._parse_published_at(
            item.get("fechaPublicacion")
            or item.get("fechaHoraPublicacion")
            or item.get("publishedAt")
            or item.get("datePosted")
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
            salary_min=item.get("salaryMin") or item.get("salarioMinimo"),
            salary_max=item.get("salaryMax") or item.get("salarioMaximo"),
            salary_currency=item.get("salaryCurrency") or item.get("moneda"),
            employment_type=str(workday) if workday else None,
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
        if text in {"hoy", "today", "publicado hoy"}:
            return now
        if text in {"ayer", "publicado ayer"}:
            return now - timedelta(days=1)
        relative = re.search(r"hace\s+(\d+)\s+(minuto|hora|día|dia|semana|mes)(?:es|s)?", text)
        if relative:
            amount = int(relative.group(1))
            unit = relative.group(2)
            if unit == "minuto":
                return now - timedelta(minutes=amount)
            if unit == "hora":
                return now - timedelta(hours=amount)
            if unit in {"día", "dia"}:
                return now - timedelta(days=amount)
            if unit == "semana":
                return now - timedelta(weeks=amount)
            return now - timedelta(days=amount * 30)
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text[:10], fmt).replace(tzinfo=UTC)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(text.replace("z", "+00:00"))
        except ValueError:
            return None
