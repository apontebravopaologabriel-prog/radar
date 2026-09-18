from __future__ import annotations

import re

from radar.domain.models import RawJob
from radar.normalize import normalize_text


def infer_work_mode(job: RawJob) -> str:
    """Infer the work mode when a source did not provide a reliable value."""
    payload = job.raw_payload if isinstance(job.raw_payload, dict) else {}
    text = normalize_text(
        f"{job.title} {job.location or ''} {job.description or ''} "
        f"{payload.get('work_from_home_type', '')}"
    )
    if any(
        phrase in text
        for phrase in (
            "hibrido",
            "hibrida",
            "hybrid",
            "mixto",
            "home office algunos dias",
            "dias remoto",
            "remoto y presencial",
            "presencial y remoto",
        )
    ):
        return "hybrid"
    has_onsite = any(phrase in text for phrase in ("presencial", "on site", "onsite", "in situ"))
    has_remote = any(
        phrase in text
        for phrase in ("100 remoto", "remoto", "remote", "teletrabajo", "a distancia", "home office", "work from home")
    )
    if has_onsite:
        return "onsite"
    if has_remote:
        return "remote"
    return "unknown"


SECTOR_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Finanzas y banca", ("banco", "banca", "financiera", "fintech", "afp", "seguros", "compliance")),
    ("Telecomunicaciones", ("telefonica", "telecomunicaciones", "telecom", "redes")),
    ("Automotriz y comercio", ("vehiculo", "vehiculos", "automotriz", "concesionario", "postventa")),
    ("Industria e ingeniería", ("manufactura", "planta", "electrificacion", "electrification", "sector electrico", "engineering", "automatizacion industrial")),
    ("Retail y consumo", ("retail", "tienda", "consumo masivo", "supermercado", "shopping")),
    ("Logística y transporte", ("logistica", "almacen", "warehouse", "despacho", "transporte", "supply chain")),
    ("Educación", ("educacion", "universidad", "instituto", "colegio")),
    ("Tecnología y servicios TI", ("tecnologia", "software", "sistemas", "data", "business intelligence", "cloud", "rpa")),
)


def infer_sector(job: RawJob) -> str | None:
    payload = job.raw_payload if isinstance(job.raw_payload, dict) else {}
    text = normalize_text(
        f"{job.title} {job.company or ''} {job.description or ''} "
        f"{payload.get('company_industry', '')} {payload.get('company_description', '')}"
    )
    # "Ingeniería industrial" often describes the candidate, not the employer's
    # sector. Remove that education phrase before classifying the market sector.
    text = re.sub(r"\b(?:ingenieria|ingeniero|ing)\s+industrial\b", " ", text)
    for sector, phrases in SECTOR_RULES:
        if any(phrase in text for phrase in phrases):
            return sector
    return None


def normalize_salary(
    minimum: float | None,
    maximum: float | None,
    currency: str | None,
    period: str | None,
) -> tuple[float | None, float | None, str | None]:
    """Reject malformed values such as a monthly salary captured as S/4."""
    if minimum is None and maximum is None:
        return None, None, currency
    values = [value for value in (minimum, maximum) if value is not None]
    if any(value <= 0 for value in values):
        return None, None, None
    normalized_currency = (currency or "").upper() or None
    normalized_period = (period or "").lower()
    if (
        normalized_currency == "PEN"
        and not re.search(r"hora|diari", normalized_period)
        and (any(value <= 100 for value in values) or any(value > 100_000 for value in values))
    ):
        return None, None, None
    if minimum is not None and maximum is not None and minimum > maximum:
        return maximum, minimum, normalized_currency
    return minimum, maximum, normalized_currency


def extract_schedule(job: RawJob) -> tuple[float | None, str | None]:
    """Extract weekly hours and preserve a short schedule evidence snippet."""
    text = job.description or ""
    weekly = re.search(
        r"(?P<hours>\d{1,2}(?:[.,]\d+)?)\s*(?:horas?|hrs?|h)\s*(?:semanales?|por semana|a la semana)",
        text,
        re.IGNORECASE,
    )
    hours = float(weekly.group("hours").replace(",", ".")) if weekly else job.hours_per_week
    schedule = None
    if weekly:
        start = max(0, weekly.start() - 80)
        schedule = text[start : min(len(text), weekly.end() + 100)].strip()
    elif re.search(r"lunes|martes|miercoles|jueves|viernes|sabado|domingo|am\s*-\s*pm", normalize_text(text)):
        match = re.search(
            r".{0,80}(?:lunes|martes|miercoles|jueves|viernes|sabado|domingo).{0,100}",
            text,
            re.IGNORECASE,
        )
        schedule = match.group(0).strip() if match else None
    return hours, schedule or job.schedule_text
