"""Importación individual de una oferta desde su URL pública."""

from __future__ import annotations

import contextlib
import html
import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from radar.db.database import connection
from radar.db.queries import get_job, set_job_favorite, set_job_user_status
from radar.db.repository import (
    ingest_jobs,
    recompute_scores,
    track_application,
    untrack_application,
)
from radar.domain.models import RawJob
from radar.geolocation import infer_job_location
from radar.normalize import fingerprint
from radar.security import UnsafeUrlError, ensure_public_http_url

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

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


def _extract_portal_offer_info(url: str) -> tuple[str | None, list[str], str, bool]:
    """Extrae `(raw_id, candidate_external_ids, fetch_url, is_listing_page)` desde la URL del portal."""
    from urllib.parse import parse_qs

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    qs = parse_qs(parsed.query)
    fragment = (parsed.fragment or "").strip()

    # 1. Computrabajo: offerId en #fragment (#358C78...), en path (-358C78...) o en query (?oi=358C78...)
    if "computrabajo" in host:
        offer_id: str | None = None
        if re.fullmatch(r"[A-Fa-f0-9]{16,40}", fragment):
            offer_id = fragment
        if not offer_id:
            m = re.search(r"-([A-Fa-f0-9]{16,40})(?:[/?#.]|$)", parsed.path)
            if m:
                offer_id = m.group(1)
        if not offer_id:
            for key in ("oi", "id", "offerId"):
                vals = qs.get(key) or []
                if vals and re.fullmatch(r"[A-Fa-f0-9]{16,40}", vals[0].strip()):
                    offer_id = vals[0].strip()
                    break
        is_listing = not parsed.path.lower().startswith("/ofertas-de-trabajo/")
        return offer_id, ([offer_id] if offer_id else []), url, is_listing

    # 2. LinkedIn: /jobs/view/<id> o ?currentJobId=<id>
    if "linkedin" in host:
        li_id: str | None = None
        m = re.search(r"/jobs/view/(?:[^/?#]*-)?(\d{7,15})(?:[/?#]|$)", parsed.path)
        if m:
            li_id = m.group(1)
        if not li_id and qs.get("currentJobId"):
            cand = qs["currentJobId"][0].strip()
            if cand.isdigit():
                li_id = cand
        fetch_url = f"https://www.linkedin.com/jobs/view/{li_id}" if li_id else url
        is_listing = not bool(li_id) and ("/jobs/search" in parsed.path or "/jobs/collections" in parsed.path)
        return li_id, ([f"li-{li_id}", li_id] if li_id else []), fetch_url, is_listing

    # 3. Indeed: ?jk=<id> o ?vjk=<id>
    if "indeed" in host:
        in_id: str | None = None
        for key in ("jk", "vjk"):
            vals = qs.get(key) or []
            if vals and re.fullmatch(r"[A-Za-z0-9]{10,24}", vals[0].strip()):
                in_id = vals[0].strip()
                break
        fetch_url = f"https://{host}/viewjob?jk={in_id}" if in_id else url
        is_listing = not bool(in_id) and "/viewjob" not in parsed.path
        return in_id, ([f"in-{in_id}", in_id] if in_id else []), fetch_url, is_listing

    # 4. Bumeran / Laborum: -<id>.html
    if "bumeran" in host or "laborum" in host:
        m = re.search(r"-(\d{6,15})(?:\.html?)?$", parsed.path, flags=re.IGNORECASE)
        bm_id = m.group(1) if m else None
        return bm_id, ([f"bm-{bm_id}", bm_id] if bm_id else []), url, False

    # 5. Empleos Perú: /vacancy-details/<id> (en path o en #/vacancy-details/<id>)
    if "empleosperu" in host or host.endswith(".gob.pe"):
        m = re.search(r"(?:vacancy-details|detalle-vacante|jobs)/([a-zA-Z0-9_-]{8,64})", url)
        ep_id = m.group(1) if m else None
        return ep_id, ([ep_id] if ep_id else []), url, True

    return None, [], url, False


def _lookup_existing_in_db(clean_url: str, candidate_ids: list[str]) -> dict[str, Any] | None:
    """Busca en `radar.db` si la oferta ya fue ingerida previamente por `source_url` o `external_id`."""
    with contextlib.suppress(Exception), connection() as conn:
        if candidate_ids:
            placeholders = ", ".join(["%s"] * len(candidate_ids))
            row = conn.execute(
                f"""SELECT j.title, c.name, j.location, j.description_raw, j.published_at,
                j.salary_min, j.salary_max, j.salary_currency, j.employment_type, j.work_mode,
                js.external_id, js.source_url
                FROM jobs j
                JOIN job_sources js ON js.job_id = j.id
                LEFT JOIN companies c ON c.id = j.company_id
                WHERE js.source_url = %s OR js.external_id IN ({placeholders})
                ORDER BY j.updated_at DESC LIMIT 1""",
                (clean_url, *candidate_ids),
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT j.title, c.name, j.location, j.description_raw, j.published_at,
                j.salary_min, j.salary_max, j.salary_currency, j.employment_type, j.work_mode,
                js.external_id, js.source_url
                FROM jobs j
                JOIN job_sources js ON js.job_id = j.id
                LEFT JOIN companies c ON c.id = j.company_id
                WHERE js.source_url = %s
                ORDER BY j.updated_at DESC LIMIT 1""",
                (clean_url,),
            ).fetchone()
        if row and row[0] and row[3]:
            pub: datetime | None = None
            if isinstance(row[4], datetime):
                pub = row[4]
            elif isinstance(row[4], str):
                with contextlib.suppress(ValueError):
                    pub = datetime.fromisoformat(row[4])
            return {
                "title": str(row[0]),
                "company": str(row[1]) if row[1] else None,
                "location": str(row[2]) if row[2] else None,
                "description": str(row[3]),
                "published_at": pub,
                "salary_min": float(row[5]) if row[5] is not None else None,
                "salary_max": float(row[6]) if row[6] is not None else None,
                "salary_currency": str(row[7]) if row[7] else None,
                "employment_type": str(row[8]) if row[8] else None,
                "work_mode": str(row[9]) if row[9] else None,
                "external_id": str(row[10]) if row[10] else None,
                "canonical_url": str(row[11]) if row[11] else clean_url,
            }
    return None


def _try_portal_native(url: str) -> RawJob | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    raw_id, _, _, is_listing = _extract_portal_offer_info(url)

    # 1. Empleos Perú: /vacancy-details/<id> or /detalle-vacante/<id>
    if ("empleosperu" in host or host.endswith(".gob.pe")) and raw_id:
        from radar.sources.empleos_peru import EmpleosPeruSource

        source = EmpleosPeruSource()
        api_url = f"{source.base_url}/api/jobs/{raw_id}"
        try:
            with httpx.Client(timeout=10.0, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"}) as client:
                resp = client.get(api_url)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict) and (data.get("positionTitle") or data.get("titulo")):
                        job = source._to_job(data)
                        job.url = url
                        return job
        except (httpx.HTTPError, ValueError):
            pass

    # 2. Computrabajo: offerId hexadecimal en #fragment, path o query
    if "computrabajo" in host and raw_id:
        offer_id = raw_id
        slug_title, slug_loc = (None, None) if is_listing else _slug_title_and_location(url)
        with contextlib.suppress(Exception):
            from radar.sources.computrabajo import ComputrabajoSource

            ct = ComputrabajoSource()
            proc = ct._spawn() if hasattr(ct, "_spawn") else None
            if proc is None:
                import subprocess

                proc = subprocess.Popen(
                    [ct.command, *ct.args], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
                )
            try:
                ct._rpc(
                    proc,
                    1,
                    "initialize",
                    {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "radar", "version": "1.0"},
                    },
                    timeout=12.0,
                )
                ct._notify(proc, "notifications/initialized", {})
                detail = ct._get_detail(proc, 2, offer_id)
                if detail and (detail.get("title") or detail.get("description") or slug_title):
                    summary = {
                        "offerId": offer_id,
                        "url": detail.get("url") or url,
                        "title": detail.get("title") or slug_title or "Oferta Computrabajo",
                        "location": detail.get("location") or slug_loc or "Lima",
                    }
                    merged = ct._merge_detail(summary, detail)
                    job = ct._to_job(merged)
                    job.external_id = offer_id
                    if not job.published_at:
                        job.published_at = datetime.now(UTC)
                    return job
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except Exception:  # noqa: BLE001
                    proc.kill()
    return None


def extract_raw_job_from_url(
    url: str,
    *,
    title: str | None = None,
    company: str | None = None,
    location: str | None = None,
    description: str | None = None,
    timeout: float = 12.0,
) -> RawJob:
    """Extrae un `RawJob` desde una URL pública combinando BD local, conectores nativos, JSON-LD, HTML y campos manuales."""
    clean_url = url.strip()
    ensure_public_http_url(clean_url)
    source_name = _source_name_from_url(clean_url)
    raw_id, candidate_ids, fetch_url, is_listing = _extract_portal_offer_info(clean_url)
    slug_title, slug_loc = (None, None) if is_listing else _slug_title_and_location(clean_url)

    extracted: dict[str, Any] = {}

    # Paso 0: Si la oferta ya existe en `radar.db` por `source_url` o `external_id`, reutilizar su ficha completa al instante.
    existing = _lookup_existing_in_db(clean_url, candidate_ids)
    if existing:
        extracted.update({k: v for k, v in existing.items() if v is not None})

    # Paso 1: Si es Computrabajo o Empleos Perú con ID de oferta y aún falta título/descripción, usar su conector nativo primero.
    prefer_native = source_name in {"Computrabajo", "Empleos Perú"} and bool(raw_id)
    if prefer_native and (not extracted.get("description") or not extracted.get("title")):
        native_job = _try_portal_native(clean_url)
        if native_job:
            extracted.setdefault("title", native_job.title if native_job.title != "Sin título" else None)
            extracted.setdefault("company", native_job.company)
            extracted.setdefault("location", native_job.location)
            extracted.setdefault("description", native_job.description)
            extracted.setdefault("published_at", native_job.published_at)
            extracted.setdefault("salary_min", native_job.salary_min)
            extracted.setdefault("salary_max", native_job.salary_max)
            extracted.setdefault("salary_currency", native_job.salary_currency)
            extracted.setdefault("employment_type", native_job.employment_type)
            extracted.setdefault("work_mode", native_job.work_mode)
            extracted.setdefault("external_id", native_job.external_id)

    # Paso 2: Intentar descarga HTTP pública (solo si la URL apunta a una oferta individual, nunca a un listado de búsqueda)
    if (not extracted.get("description") or not extracted.get("title")) and not is_listing:
        def _guard(request: httpx.Request) -> None:
            ensure_public_http_url(str(request.url))

        html_text = ""
        try:
            with httpx.Client(
                timeout=timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": _USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
                },
                event_hooks={"request": [_guard]},
            ) as client:
                response = client.get(fetch_url)
                if response.status_code < 400:
                    html_text = response.text
        except (httpx.HTTPError, UnsafeUrlError):
            html_text = ""

        if html_text:
            ld_entry = _parse_json_ld_job_posting(html_text)
            if ld_entry:
                extracted.update({k: v for k, v in _extract_from_json_ld(ld_entry).items() if v is not None and k not in extracted})
            meta_info = _extract_from_html_meta(html_text)
            if not extracted.get("title") and meta_info.get("title"):
                extracted["title"] = meta_info["title"]
            if not extracted.get("description") and meta_info.get("description"):
                extracted["description"] = meta_info["description"]

    # Paso 3: Fallback a conector nativo si no se probó en el Paso 1
    if not prefer_native and (not extracted.get("description") or not extracted.get("title")):
        native_job = _try_portal_native(clean_url)
        if native_job:
            extracted.setdefault("title", native_job.title if native_job.title != "Sin título" else None)
            extracted.setdefault("company", native_job.company)
            extracted.setdefault("location", native_job.location)
            extracted.setdefault("description", native_job.description)
            extracted.setdefault("published_at", native_job.published_at)
            extracted.setdefault("salary_min", native_job.salary_min)
            extracted.setdefault("salary_max", native_job.salary_max)
            extracted.setdefault("salary_currency", native_job.salary_currency)
            extracted.setdefault("employment_type", native_job.employment_type)
            extracted.setdefault("work_mode", native_job.work_mode)
            extracted.setdefault("external_id", native_job.external_id)

    final_title = (title or "").strip() or extracted.get("title") or slug_title
    final_company = (company or "").strip() or extracted.get("company")
    final_location = (location or "").strip() or extracted.get("location") or slug_loc or "Lima"
    final_description = (description or "").strip() or extracted.get("description")
    final_ext_id = extracted.get("external_id") or (candidate_ids[0] if candidate_ids else None)
    final_url = extracted.get("canonical_url") or clean_url

    if not final_title:
        raise ValueError(
            "No se pudo extraer el título de la oferta desde el enlace (el portal puede requerir sesión o bloquear accesos automáticos). "
            "Pásale al agente el título y/o pega el texto de la descripción junto con el link."
        )

    return RawJob(
        source=source_name,
        title=final_title,
        company=final_company or None,
        url=final_url,
        external_id=final_ext_id,
        location=final_location,
        description=final_description or None,
        published_at=extracted.get("published_at") or datetime.now(UTC),
        salary_min=extracted.get("salary_min"),
        salary_max=extracted.get("salary_max"),
        salary_currency=extracted.get("salary_currency"),
        employment_type=extracted.get("employment_type"),
        work_mode=extracted.get("work_mode"),
        raw_payload={"imported_from_url": clean_url, "manual_override": bool(title or description)},
    )


def fetch_and_ingest_single_job(
    url: str,
    *,
    title: str | None = None,
    company: str | None = None,
    location: str | None = None,
    description: str | None = None,
    favorite: bool = False,
    application_status: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Extrae una oferta por su URL, la guarda en `radar.db`, recalcula el encaje y aplica seguimiento opcional."""
    raw = extract_raw_job_from_url(
        url,
        title=title,
        company=company,
        location=location,
        description=description,
    )
    stats = ingest_jobs([raw])
    fp = fingerprint(raw)

    job_id: str | None = None
    with connection() as conn:
        row = conn.execute(
            """SELECT j.id FROM jobs j
            LEFT JOIN job_sources js ON js.job_id = j.id
            WHERE js.source_url IN (%s, %s)
               OR (js.external_id IS NOT NULL AND js.external_id = %s)
               OR j.canonical_fingerprint = %s
            ORDER BY j.updated_at DESC LIMIT 1""",
            (url.strip(), raw.url, raw.external_id or "", fp),
        ).fetchone()
        if row:
            job_id = str(row[0])
            # Garantizar que quede activa y con la descripción nueva si antes no tenía
            if raw.description:
                conn.execute(
                    """UPDATE jobs SET is_active = TRUE,
                    description_raw = COALESCE(%s, description_raw),
                    updated_at = now()
                    WHERE id = %s""",
                    (raw.description, job_id),
                )
            else:
                conn.execute("UPDATE jobs SET is_active = TRUE, updated_at = now() WHERE id = %s", (job_id,))
            conn.commit()
        profile = conn.execute("SELECT id FROM user_profile ORDER BY updated_at DESC LIMIT 1").fetchone()

    if not job_id:
        raise RuntimeError("La oferta fue procesada pero no se encontró su identificador en la base de datos.")

    if profile:
        recompute_scores(str(profile[0]))

    if favorite:
        set_job_favorite(job_id)

    if application_status:
        if application_status == "visible":
            untrack_application(job_id)
            set_job_user_status(job_id, "visible")
        elif application_status == "ignored":
            set_job_user_status(job_id, "hidden", "not_interested", notes)
            track_application(job_id, "ignored", notes)
        else:
            track_application(job_id, application_status, notes)

    job_data = get_job(job_id) or {}
    point = infer_job_location(
        job_data.get("location") or raw.location,
        job_data.get("title") or raw.title,
        job_data.get("description") or raw.description,
    )
    fit_score: float | None = None
    with connection() as conn:
        score_row = conn.execute(
            "SELECT total_score FROM job_scores WHERE job_id = %s ORDER BY computed_at DESC LIMIT 1",
            (job_id,),
        ).fetchone()
        if score_row and score_row[0] is not None:
            fit_score = round(float(score_row[0]), 1)

    return {
        "job_id": job_id,
        "status": "created" if stats.get("created", 0) > 0 else "updated",
        "source": raw.source,
        "title": job_data.get("title") or raw.title,
        "company": job_data.get("company") or raw.company,
        "location": job_data.get("location") or raw.location,
        "district": point.label if point else None,
        "work_mode": job_data.get("work_mode") or raw.work_mode,
        "seniority": job_data.get("seniority"),
        "primary_area": job_data.get("primary_area"),
        "salary_min": job_data.get("salary_min"),
        "salary_max": job_data.get("salary_max"),
        "salary_currency": job_data.get("salary_currency"),
        "fit_score": fit_score,
        "is_favorite": bool(job_data.get("is_favorite") or favorite),
        "application_status": application_status or job_data.get("user_application"),
        "url": raw.url,
        "radar_link": f"radar:job:{job_id}",
    }
