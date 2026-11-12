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

_STOPWORDS = frozenset({"de", "del", "en", "la", "el", "los", "las", "para", "con", "por", "un", "una", "y", "o", "e"})

_UBIGEO_DEPARTMENTS = {
    "01": "Amazonas", "02": "Áncash", "03": "Apurímac", "04": "Arequipa", "05": "Ayacucho",
    "06": "Cajamarca", "07": "Callao", "08": "Cusco", "09": "Huancavelica", "10": "Huánuco",
    "11": "Ica", "12": "Junín", "13": "Trujillo, La Libertad", "14": "Chiclayo, Lambayeque",
    "15": "Lima", "16": "Iquitos, Loreto", "17": "Puerto Maldonado, Madre de Dios", "18": "Moquegua",
    "19": "Cerro de Pasco, Pasco", "20": "Piura", "21": "Puno", "22": "Tarapoto, San Martín",
    "23": "Tacna", "24": "Tumbes", "25": "Pucallpa, Ucayali",
}

_LIMA_CALLAO_UBIGEO = {
    "070101": "Callao", "070102": "Bellavista, Callao", "070103": "Carmen de la Legua Reynoso, Callao",
    "070104": "La Perla, Callao", "070105": "La Punta, Callao", "070106": "Ventanilla, Callao",
    "070107": "Mi Perú, Callao",
    "150101": "Cercado de Lima", "150102": "Ancón, Lima", "150103": "Ate, Lima",
    "150104": "Barranco, Lima", "150105": "Breña, Lima", "150106": "Carabayllo, Lima",
    "150107": "Chaclacayo, Lima", "150108": "Chorrillos, Lima", "150109": "Cieneguilla, Lima",
    "150110": "Comas, Lima", "150111": "El Agustino, Lima", "150112": "Independencia, Lima",
    "150113": "Jesús María, Lima", "150114": "La Molina, Lima", "150115": "La Victoria, Lima",
    "150116": "Lince, Lima", "150117": "Los Olivos, Lima", "150118": "Lurigancho, Lima",
    "150119": "Lurín, Lima", "150120": "Magdalena del Mar, Lima", "150121": "Pueblo Libre, Lima",
    "150122": "Miraflores, Lima", "150123": "Pachacámac, Lima", "150124": "Pucusana, Lima",
    "150125": "Puente Piedra, Lima", "150126": "Punta Hermosa, Lima", "150127": "Punta Negra, Lima",
    "150128": "Rímac, Lima", "150129": "San Bartolo, Lima", "150130": "San Borja, Lima",
    "150131": "San Isidro, Lima", "150132": "San Juan de Lurigancho, Lima",
    "150133": "San Juan de Miraflores, Lima", "150134": "San Luis, Lima",
    "150135": "San Martín de Porres, Lima", "150136": "San Miguel, Lima",
    "150137": "Santa Anita, Lima", "150138": "Santa María del Mar, Lima",
    "150139": "Santa Rosa, Lima", "150140": "Santiago de Surco, Lima",
    "150141": "Surquillo, Lima", "150142": "Villa El Salvador, Lima",
    "150143": "Villa María del Triunfo, Lima",
}

_LIMA_PROVINCES_UBIGEO = {
    "1502": "Barranca", "1505": "Cañete", "1506": "Huaral", "1508": "Huacho",
}


def _resolve_ubigeo(loc: dict[str, Any]) -> str:
    district = str(loc.get("DISTRICT") or "").strip()
    if district in _LIMA_CALLAO_UBIGEO:
        return _LIMA_CALLAO_UBIGEO[district]
    province = str(loc.get("PROVINCE") or "").strip()
    if province in _LIMA_PROVINCES_UBIGEO:
        return _LIMA_PROVINCES_UBIGEO[province]
    dept = str(loc.get("DEPARTMENT") or "").strip()
    return _UBIGEO_DEPARTMENTS.get(dept, "Lima")


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
        words = [w.strip() for w in query.split() if len(w.strip()) > 2 and w.strip().lower() not in _STOPWORDS]
        candidates = [query.strip()]
        if len(words) >= 2:
            candidates.append(" ".join(words[:2]))
        if words and words[-1].lower() not in {"practicante", "asistente", "analista", "auxiliar", "ingeniero", "supervisor", "jefe", "especialista", "coordinador"}:
            candidates.append(words[-1])
        endpoints = [
            f"{self.base_url}/api/jobs?positionTitle={urllib.parse.quote(term)}&limit={clean_limit}"
            for term in dict.fromkeys(c for c in candidates if c)
        ] + [
            f"{self.base_url}/api/jobs?what={urllib.parse.quote(query)}&limit={clean_limit}",
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
                        return [self._enrich_detail(item) for item in items[:limit]]
            except (urllib.error.URLError, TimeoutError, ValueError, OSError):
                continue
        return []

    def _enrich_detail(self, item: dict[str, Any]) -> dict[str, Any]:
        if item.get("jobDescription") or item.get("descripcion") or item.get("description"):
            return item
        offer_id = str(item.get("id") or item.get("idVacante") or "").strip()
        if not offer_id or not re.fullmatch(r"[a-zA-Z0-9_\-]{8,64}", offer_id):
            return item
        req = urllib.request.Request(
            f"{self.base_url}/api/jobs/{urllib.parse.quote(offer_id)}",
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json, text/plain, */*"},
        )
        try:
            with urllib.request.urlopen(req, timeout=min(self.timeout, 10.0)) as resp:
                detail = json.loads(resp.read().decode("utf-8", errors="replace"))
                if isinstance(detail, dict):
                    return {**item, **{k: v for k, v in detail.items() if v is not None}}
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            pass
        return item

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
            url = f"{self.base_url}/search-jobs?jobId={urllib.parse.quote(offer_id)}"
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
            location = _resolve_ubigeo(location)

        role_detail = _strip_html(
            item.get("jobDescription")
            or item.get("descripcion")
            or item.get("description")
            or item.get("funciones")
            or item.get("requisitos")
        )
        company_desc = _strip_html(item.get("companyDescription"))
        detail = "\n".join(filter(None, [
            role_detail,
            f"Empresa: {company_desc}" if company_desc else None,
        ]))

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
