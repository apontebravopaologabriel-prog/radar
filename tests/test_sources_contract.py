"""Contrato de las fuentes: forma de las respuestas externas que Radar espera.

Si un portal cambia su formato, estas pruebas fallan en CI en lugar de que Radar muestre datos viejos sin avisar.
"""

import json
import math
from datetime import UTC, datetime, timedelta

from radar.sources.computrabajo import ComputrabajoSource
from radar.sources.jobspy import JobSpySource

CARD = {
    "offerId": "ABC123",
    "title": "Analista de Procesos",
    "company": "ACME SAC",
    "url": "https://pe.computrabajo.com/oferta-ABC123",
    "location": "Lima, Lima",
    "publishedAt": "hace 3 días",
}
DETAIL = {
    "offerId": "ABC123",
    "description": "Requiere Excel y Power BI",
    "modality": "Presencial",
    "workday": "Tiempo completo",
    "salary": "S/ 3,000",
    "applyUrl": "https://pe.computrabajo.com/login?apply=ABC123",
}


def test_extract_jobs_from_structured_and_text_payloads():
    assert ComputrabajoSource._extract_jobs({"structuredContent": {"jobs": [CARD]}}) == [CARD]
    text = {"content": [{"type": "text", "text": json.dumps({"jobs": [CARD]})}]}
    assert ComputrabajoSource._extract_jobs(text) == [CARD]
    assert ComputrabajoSource._extract_jobs({"content": [{"type": "text", "text": "no es json"}]}) == []
    assert ComputrabajoSource._extract_jobs({}) == []


def test_extract_detail_from_structured_and_text_payloads():
    assert ComputrabajoSource._extract_detail({"structuredContent": {"job": DETAIL}}) == DETAIL
    text = {"content": [{"type": "text", "text": json.dumps({"job": DETAIL})}]}
    assert ComputrabajoSource._extract_detail(text) == DETAIL
    assert ComputrabajoSource._extract_detail({"content": []}) is None


def test_detail_keeps_public_url_and_adds_description():
    merged = ComputrabajoSource._merge_detail(CARD, DETAIL)
    assert merged["url"] == CARD["url"]
    assert merged["description"] == DETAIL["description"]
    assert ComputrabajoSource._merge_detail(CARD, None) == CARD


def test_card_maps_to_rawjob():
    job = ComputrabajoSource()._to_job(ComputrabajoSource._merge_detail(CARD, DETAIL))
    assert (job.source, job.external_id, job.company) == ("Computrabajo", "ABC123", "ACME SAC")
    assert job.url == CARD["url"]
    assert "Excel" in job.description and "Modalidad: Presencial" in job.description
    assert job.published_at is not None


def test_relative_dates_in_spanish():
    parse = ComputrabajoSource._parse_published_at
    now = datetime.now(UTC)
    assert abs(parse("hoy") - now) < timedelta(seconds=5)
    assert abs(parse("ayer") - (now - timedelta(days=1))) < timedelta(seconds=5)
    assert abs(parse("Hace 2 semanas") - (now - timedelta(weeks=2))) < timedelta(seconds=5)
    assert parse("2026-09-01T10:00:00Z").year == 2026
    assert parse("fecha rara") is None and parse(None) is None


def test_jobspy_row_handles_nan_and_remote():
    row = {
        "id": "in-1", "title": "Data Analyst", "company": "ACME", "job_url": "https://pe.indeed.com/viewjob?jk=1",
        "location": "Lima, Peru", "description": "SQL", "date_posted": "2026-09-30",
        "min_amount": math.nan, "max_amount": math.nan, "currency": math.nan, "is_remote": True,
    }
    job = JobSpySource(sites=["indeed"])._row_to_job(row)
    assert job.salary_min is None and job.salary_currency is None
    assert job.work_mode == "remote"
    assert job.published_at.year == 2026
    assert JobSpySource(sites=["indeed"])._row_to_job({"title": None}).title == "Sin título"
