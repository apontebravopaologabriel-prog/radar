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
    li_job = JobSpySource()._row_to_job({"site": "linkedin", "title": "Analista", "job_url": "https://www.linkedin.com/jobs/view/1"})
    assert li_job.source == "JobSpy/LinkedIn"


def test_bumeran_and_empleos_peru_map_to_rawjob():
    from radar.sources.bumeran import BumeranSource
    from radar.sources.empleos_peru import EmpleosPeruSource

    bm_payload = {"content": [{"id": 111, "titulo": "Analista de Procesos", "empresa": "ACME", "localizacion": "San Isidro, Lima", "detalle": "<p>Mejora continua y S/ 2,500</p>", "fechaPublicacion": "hoy"}]}
    bm_jobs = [BumeranSource()._to_job(item) for item in BumeranSource._extract_jobs(bm_payload)]
    assert len(bm_jobs) == 1
    assert bm_jobs[0].source == "Bumeran"
    assert bm_jobs[0].external_id == "111"
    assert "San Isidro" in (bm_jobs[0].location or "")
    assert bm_jobs[0].published_at is not None

    ep_payload = {"vacantes": [{"idVacante": "EP-99", "titulo": "Asistente de Operaciones", "empresa": "Textil Perú", "distrito": "Ate", "departamento": "Lima", "descripcion": "Control de producción", "remuneracion": 1800, "fechaPublicacion": "2026-10-10"}]}
    ep_jobs = [EmpleosPeruSource()._to_job(item) for item in EmpleosPeruSource._extract_jobs(ep_payload)]
    assert len(ep_jobs) == 1
    assert ep_jobs[0].source == "Empleos Perú"
    assert ep_jobs[0].url == "https://mtpe-candidatos.empleosperu.gob.pe/search-jobs?jobId=EP-99"
    assert ep_jobs[0].salary_min == 1800.0
    assert ep_jobs[0].salary_currency == "PEN"

    ep_ubigeo = EmpleosPeruSource()._to_job({
        "id": "EP-100",
        "positionTitle": "Analista de Créditos - Trujillo",
        "companyName": "ACME",
        "location": {"COUNTRY": "PE", "DEPARTMENT": "13", "PROVINCE": "1301", "DISTRICT": "130101"},
        "companyDescription": "Misión corporativa",
        "jobDescription": "Evaluar cartera",
    })
    assert "Trujillo" in (ep_ubigeo.location or "")
    assert ep_ubigeo.url == "https://mtpe-candidatos.empleosperu.gob.pe/search-jobs?jobId=EP-100"
    assert "Evaluar cartera" in (ep_ubigeo.description or "")
    assert "Empresa: Misión corporativa" in (ep_ubigeo.description or "")


def test_native_computrabajo_cards_and_public_detail():
    from radar.sources.computrabajo_native import cards, detail

    html = '''<article class="box_offer" data-id="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"><h2><a class="js-o-link" href="/ofertas-de-trabajo/oferta-1#detalle">Ingeniero mecánico</a></h2><a offer-grid-article-company-url="1">ACME</a><p class="fs16 fc_base mt5"><span class="mr10">Bellavista, Callao</span></p><p class="fs13 fc_aux">Hoy</p></article>'''
    [card] = cards(html)
    assert card['url'] == 'https://pe.computrabajo.com/ofertas-de-trabajo/oferta-1'
    assert card['location'] == 'Bellavista, Callao' and card['publishedDate'] == 'Hoy'
    payload = detail({'o': {'ld':'<p>Diseñar componentes</p><p>SolidWorks</p>', 't':'Ingeniero', 'lha':'https://candidato.pe.computrabajo.com/apply'}})
    assert payload['description'] == 'Diseñar componentes\nSolidWorks' and 'applyUrl' not in payload


def test_native_computrabajo_challenge_is_an_error_not_empty_market():
    import pytest

    from radar.sources.computrabajo_native import cards

    with pytest.raises(RuntimeError, match='tarjetas'):
        cards('<html><title>Verify you are human</title></html>')
    assert cards('<html>No se encontraron ofertas</html>') == []


def test_native_computrabajo_http_search_keeps_identity_and_enriches(monkeypatch):
    import httpx

    from radar.sources import computrabajo_native as native

    real_client = httpx.Client
    requests = []
    offer_id = "A" * 32
    def respond(request):
        requests.append(request)
        assert "Radar/" in request.headers["user-agent"]
        assert request.headers["accept-language"].startswith("es-PE")
        assert "cookie" not in request.headers and "authorization" not in request.headers
        if request.url.host == "pe.computrabajo.com":
            assert request.headers["accept"].startswith("text/html")
            return httpx.Response(200, text=f'''<article class="box_offer" data-id="{offer_id}"><h2><a class="js-o-link" href="/ofertas-de-trabajo/oferta-1">Analista de logística</a></h2><a offer-grid-article-company-url="1">ACME</a><p class="fs16 fc_base mt5"><span class="mr10">Lima</span></p><p class="fs13 fc_aux">Hoy</p></article>''')
        return httpx.Response(200, json={"o": {"t": "Analista", "ld": "<p>Inventarios y compras</p>"}})
    monkeypatch.setattr(native.httpx, "Client", lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(respond)))
    [job] = ComputrabajoSource().search("analista logistica", "Lima", 1)
    assert job.external_id == offer_id and job.published_at is not None
    assert job.url == "https://pe.computrabajo.com/ofertas-de-trabajo/oferta-1"
    assert "Inventarios y compras" in job.description
    assert len(requests) == 2


def test_native_computrabajo_http_403_is_not_retried_or_hidden(monkeypatch):
    import httpx
    import pytest

    from radar.sources import computrabajo_native as native

    real_client = httpx.Client
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(403, text="Forbidden")
    monkeypatch.setattr(native.httpx, "Client", lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(respond)))
    with pytest.raises(httpx.HTTPStatusError):
        native.search("analista", "Lima", 10)
    assert len(requests) == 1


def test_bumeran_shortens_an_and_query_that_returns_nothing(monkeypatch):
    from radar.sources import bumeran

    seen: list[str] = []

    def fake_api(self, query, location, limit):
        seen.append(query)
        return [{"id": 1, "titulo": "Analista de datos", "empresa": "ACME", "detalle": "<p>SQL</p>"}] if query == "analista de datos" else []

    monkeypatch.setattr(bumeran.BumeranSource, "_search_api", fake_api)
    monkeypatch.setattr(bumeran.BumeranSource, "_search_html", lambda self, query, location, limit: [])
    jobs = bumeran.BumeranSource().search("analista de datos reportes Excel", "Lima", 10)
    assert [job.title for job in jobs] == ["Analista de datos"]
    assert seen == ["analista de datos reportes Excel", "analista de datos reportes", "analista de datos"]


def test_bumeran_variants_keep_a_meaningful_query():
    from radar.sources.bumeran import _query_variants

    assert _query_variants("soporte ti") == ["soporte ti"]
    assert _query_variants("analista de datos") == ["analista de datos"]
    assert _query_variants("data scientist machine learning") == ["data scientist machine learning", "data scientist machine", "data scientist"]
    assert "analista" not in _query_variants("analista de")


def test_bumeran_silence_is_a_source_failure_not_an_empty_market(monkeypatch):
    import urllib.error

    import pytest

    from radar.sources import bumeran

    def forbidden(self, query, location, limit):
        raise urllib.error.HTTPError(query, 403, "Forbidden", None, None)

    monkeypatch.setattr(bumeran.BumeranSource, "_search_api", forbidden)
    monkeypatch.setattr(bumeran.BumeranSource, "_search_html", forbidden)
    with pytest.raises(bumeran.BumeranUnavailable) as failure:
        bumeran.BumeranSource().search("analista de datos reportes Excel", "Lima", 10)
    assert failure.value.status_code == 403
