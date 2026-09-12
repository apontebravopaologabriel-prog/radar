from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from radar.domain.models import RawJob


def load_job_file(path: str, source: str) -> list[RawJob]:
    """Carga CSV o JSON exportado/copiado desde un portal, sin automatizar la cuenta."""
    file_path = Path(path)
    if file_path.suffix.lower() == ".json":
        rows = json.loads(file_path.read_text(encoding="utf-8"))
    else:
        with file_path.open(newline="", encoding="utf-8-sig") as stream:
            rows = list(csv.DictReader(stream))
    if not isinstance(rows, list):
        raise TypeError("El archivo debe contener una lista JSON o filas CSV")
    return [_row_to_job(row, source) for row in rows]


def _row_to_job(row: dict[str, Any], source: str) -> RawJob:
    published = row.get("published_at") or row.get("publishedAt") or row.get("fecha_publicacion")
    if published and not isinstance(published, datetime):
        try:
            published = datetime.fromisoformat(str(published))
        except ValueError:
            published = None
    return RawJob(
        source=source,
        title=str(row.get("title") or row.get("titulo") or "Sin título"),
        company=row.get("company") or row.get("empresa"),
        url=str(row.get("url") or row.get("job_url") or row.get("enlace") or ""),
        external_id=row.get("external_id") or row.get("job_id") or row.get("id"),
        location=row.get("location") or row.get("ubicacion"),
        description=row.get("description") or row.get("descripcion"),
        published_at=published,
        salary_min=_number(row.get("salary_min") or row.get("salario_min")),
        salary_max=_number(row.get("salary_max") or row.get("salario_max")),
        salary_currency=row.get("salary_currency") or row.get("moneda"),
        salary_period=row.get("salary_period") or row.get("periodo"),
        work_mode=_work_mode(row.get("work_mode") or row.get("modalidad")),
        hours_per_week=_number(row.get("hours_per_week") or row.get("horas_semana")),
        schedule_text=row.get("schedule_text") or row.get("horario"),
        application_status=_application_status(row),
        application_checked_at=_date(row.get("application_checked_at") or row.get("fecha_verificacion")),
        application_status_source="source_page" if row.get("application_status") or row.get("estado_postulacion") else "unknown",
        raw_payload=row,
    )


def _date(value: Any) -> datetime | None:
    if not value or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _application_status(row: dict[str, Any]) -> str:
    value = row.get("application_status") or row.get("estado_postulacion") or row.get("status")
    if isinstance(value, bool):
        return "open" if value else "closed"
    normalized = str(value or "").strip().lower()
    if any(token in normalized for token in ("closed", "cerrad", "no se aceptan", "ya no")):
        return "closed"
    if any(token in normalized for token in ("expired", "expirad", "vencid")):
        return "expired"
    if any(token in normalized for token in ("open", "abiert", "accepting", "solicitar", "apply")):
        return "open"
    return "unknown"


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(str(value).replace(",", ""))


def _work_mode(value: Any) -> str | None:
    if not value:
        return None
    normalized = str(value).strip().lower()
    if "remote" in normalized or "remoto" in normalized:
        return "remote"
    if "hybrid" in normalized or "híbr" in normalized or "hibr" in normalized:
        return "hybrid"
    if "on-site" in normalized or "onsite" in normalized or "presencial" in normalized:
        return "onsite"
    return "unknown"
