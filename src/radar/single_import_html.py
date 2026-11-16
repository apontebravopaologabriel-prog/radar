"""Extracción de metadatos y JSON-LD desde HTML público y slugs de URLs."""

from __future__ import annotations

import html
import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

_TITLE_SUFFIX_RE = re.compile(
    r"\s*(?:\||-|\u2013|\u2014)\s*(?:Computrabajo[^|]*|LinkedIn[^|]*|Indeed[^|]*|Bumeran[^|]*|Laborum[^|]*|Empleos\s*Per[uú][^|]*|Postula\s+ahora.*)$",
    re.IGNORECASE,
)


def _strip_html(raw: str | None) -> str:
    if not raw:
        return ""
    text = re.sub(r"<(script|style|noscript|header|footer|nav|svg)[^>]*>.*?</\1>", " ", str(raw), flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<br\s*/?>|</p>|</li>|</div>|</h[1-6]>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _source_name_from_url(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if "computrabajo" in host:
        return "Computrabajo"
    if "bumeran" in host:
        return "Bumeran"
    if "laborum" in host:
        return "Laborum"
    if "empleosperu" in host or host.endswith(".gob.pe"):
        return "Empleos Perú"
    if "linkedin" in host:
        return "JobSpy/LinkedIn"
    if "indeed" in host:
        return "JobSpy/Indeed"
    if "glassdoor" in host:
        return "JobSpy/Glassdoor"
    return "Web"


def _slug_title_and_location(url: str) -> tuple[str | None, str | None]:
    path = urlparse(url).path.strip("/")
    if not path:
        return None, None
    last = path.split("/")[-1]
    last = re.sub(r"\.html?$", "", last, flags=re.IGNORECASE)
    # Computrabajo: oferta-de-trabajo-de-<titulo>-en-<ubicacion>-<HEXID>
    ct_match = re.match(
        r"^oferta-de-trabajo-de-(?P<title>.+?)(?:-en-(?P<loc>[a-z0-9-]+?))?-(?P<id>[A-Fa-f0-9]{16,40})$",
        last,
        flags=re.IGNORECASE,
    )
    if ct_match:
        raw_title = ct_match.group("title").replace("-", " ").strip()
        raw_loc = (ct_match.group("loc") or "").replace("-", " ").strip()
        return (raw_title.capitalize() if raw_title else None), (raw_loc.title() if raw_loc else None)
    # Bumeran / generic: <titulo>-<id>
    bm_match = re.match(r"^(?P<title>.+?)-(?P<id>\d{6,15}|[a-f0-9]{16,40})$", last, flags=re.IGNORECASE)
    if bm_match:
        raw_title = re.sub(r"-+", " ", bm_match.group("title")).strip()
        if len(raw_title) >= 4:
            return raw_title.capitalize(), None
    return None, None


def _parse_json_ld_job_posting(html_text: str) -> dict[str, Any] | None:
    for match in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html_text,
        flags=re.DOTALL | re.IGNORECASE,
    ):
        raw_json = match.group(1).strip()
        if not raw_json:
            continue
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            continue
        candidates: list[Any] = []
        if isinstance(parsed, list):
            candidates.extend(parsed)
        elif isinstance(parsed, dict):
            candidates.append(parsed)
            if isinstance(parsed.get("@graph"), list):
                candidates.extend(parsed["@graph"])
        for entry in candidates:
            if not isinstance(entry, dict):
                continue
            kind = entry.get("@type")
            if kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind):
                return entry
    return None


def _extract_from_json_ld(entry: dict[str, Any]) -> dict[str, Any]:
    title = _strip_html(entry.get("title"))
    org = entry.get("hiringOrganization")
    company = org.get("name") if isinstance(org, dict) else (org if isinstance(org, str) else None)
    if isinstance(company, str) and company.strip().lower() in {"confidencial", "importante empresa"}:
        company = company.strip()

    loc_parts: list[str] = []
    job_loc = entry.get("jobLocation")
    locs = job_loc if isinstance(job_loc, list) else ([job_loc] if isinstance(job_loc, dict) else [])
    for loc in locs:
        if not isinstance(loc, dict):
            continue
        addr = loc.get("address")
        if isinstance(addr, dict):
            for key in ("addressLocality", "addressRegion"):
                val = addr.get(key)
                if isinstance(val, str) and val.strip() and val.strip() not in loc_parts:
                    loc_parts.append(val.strip())
        elif isinstance(addr, str) and addr.strip():
            loc_parts.append(addr.strip())
    location = ", ".join(loc_parts) if loc_parts else None

    description = _strip_html(entry.get("description"))
    date_posted = entry.get("datePosted")
    published_at: datetime | None = None
    if isinstance(date_posted, str) and date_posted.strip():
        try:
            published_at = datetime.fromisoformat(date_posted.strip())
            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=UTC)
        except ValueError:
            published_at = None

    emp_type = entry.get("employmentType")
    if isinstance(emp_type, list):
        emp_type = ", ".join(str(x) for x in emp_type if x)

    loc_type = str(entry.get("jobLocationType") or "").upper()
    work_mode = "remote" if "TELECOMMUTE" in loc_type else None

    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    base_salary = entry.get("baseSalary")
    if isinstance(base_salary, dict):
        salary_currency = base_salary.get("currency")
        val = base_salary.get("value")
        if isinstance(val, dict):
            raw_min = val.get("minValue") or val.get("value")
            raw_max = val.get("maxValue")
            if isinstance(raw_min, (int, float)):
                salary_min = float(raw_min)
            if isinstance(raw_max, (int, float)):
                salary_max = float(raw_max)
        elif isinstance(val, (int, float)):
            salary_min = float(val)

    return {
        "title": title or None,
        "company": company.strip() if isinstance(company, str) and company.strip() else None,
        "location": location,
        "description": description or None,
        "published_at": published_at,
        "employment_type": str(emp_type) if emp_type else None,
        "work_mode": work_mode,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": salary_currency,
    }


def _meta_content(html_text: str, attr_name: str, attr_val: str) -> str | None:
    pattern = rf'<meta[^>]+{attr_name}=["\']{re.escape(attr_val)}["\'][^>]+content=["\']([^"\']+)["\']'
    match = re.search(pattern, html_text, flags=re.IGNORECASE)
    if not match:
        pattern_rev = rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+{attr_name}=["\']{re.escape(attr_val)}["\']'
        match = re.search(pattern_rev, html_text, flags=re.IGNORECASE)
    return html.unescape(match.group(1)).strip() if match else None


def _extract_from_html_meta(html_text: str) -> dict[str, Any]:
    raw_title = (
        _meta_content(html_text, "property", "og:title")
        or _meta_content(html_text, "name", "twitter:title")
    )
    if not raw_title:
        h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", html_text, flags=re.DOTALL | re.IGNORECASE)
        if h1_match:
            raw_title = _strip_html(h1_match.group(1))
    if not raw_title:
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html_text, flags=re.DOTALL | re.IGNORECASE)
        if title_match:
            raw_title = _strip_html(title_match.group(1))

    clean_title = _TITLE_SUFFIX_RE.sub("", raw_title).strip() if raw_title else None
    if clean_title:
        # Computrabajo often prefixes "Oferta de trabajo de <Puesto> en <Ciudad>"
        ct_prefix = re.match(r"^Oferta de trabajo de\s+(.+?)(?:\s+en\s+[A-ZÁÉÍÓÚÑa-záéíóúñ\s]+)?$", clean_title)
        if ct_prefix:
            clean_title = ct_prefix.group(1).strip()

    meta_desc = (
        _meta_content(html_text, "property", "og:description")
        or _meta_content(html_text, "name", "description")
    )
    body_text = _strip_html(html_text)
    if len(body_text) > 8000:
        body_text = body_text[:8000]
    description = "\n\n".join(filter(None, [meta_desc, body_text if len(body_text) > 120 else None])) or None
    return {"title": clean_title or None, "description": description}
