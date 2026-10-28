from datetime import UTC, datetime

from radar.classify import classify, infer_seniority
from radar.db.repository import _json_safe
from radar.domain.models import RawJob
from radar.enrichment import extract_schedule, infer_sector, infer_work_mode, normalize_salary
from radar.freshness import filter_recent_jobs, is_recent
from radar.geolocation import infer_location
from radar.importers import load_job_file
from radar.links import google_maps_search_url
from radar.normalize import fingerprint, normalize_text
from radar.salary import extract_salary
from radar.scoring import score_job
from radar.sources.computrabajo import ComputrabajoSource
from radar.sources.jobspy import JobSpySource
from radar.taxonomy import infer_relevance


def test_google_maps_search_url_uses_company_and_location():
    url = google_maps_search_url("GRUPO INNOVA", "San Isidro")
    assert url == "https://www.google.com/maps/search/?api=1&query=GRUPO%20INNOVA%2C%20San%20Isidro%2C%20Per%C3%BA"
    assert google_maps_search_url(None, "Lima") is None


def test_normalization_and_fingerprint_are_stable():
    assert normalize_text("  Mejora contínua  ") == "mejora continua"
    a = RawJob("x", "Practicante de Procesos", "ACME", "https://example.com/1", location="Lima")
    b = RawJob("y", "Practicante de Procesos", "ACME", "https://example.com/2", location="Lima")
    assert fingerprint(a) == fingerprint(b)


def test_classification_keeps_evidence():
    job = RawJob(
        "x",
        "Practicante de Mejora Continua",
        "ACME",
        "https://example.com",
        description="Requiere Excel, Power BI y Lean",
    )
    result = classify(job)
    assert result.primary_area.value == "Operaciones y productividad"
    assert {name for name, _ in result.skills} >= {"Excel", "Power BI", "Lean"}
    assert all(item.evidence for _, item in result.skills)
    assert infer_seniority(job) == "intern"


def test_commercial_title_is_not_classified_as_industrial():
    result = classify(RawJob(
        "x",
        "Ejecutivo Comercial",
        "ACME",
        "https://example.com",
        description="Coordinar con operaciones y procesos internos.",
    ))
    assert result.primary_area.value == "Ventas / Comercial"
    assert result.primary_area.confidence >= 0.9


def test_industrial_title_can_keep_commercial_context_as_secondary():
    result = classify(RawJob(
        "x",
        "Coordinador de Operaciones",
        "ACME",
        "https://example.com",
        description="Relación comercial con clientes industriales.",
    ))
    assert result.primary_area.value == "Operaciones y productividad"


def test_relevance_prioritizes_industrial_core_and_excludes_generic_sales():
    core = infer_relevance(
        RawJob("x", "Analista de Procesos", "ACME", "https://example.com", description="Automatización y mejora continua."),
        "Procesos",
    )
    commercial = infer_relevance(
        RawJob("x", "Ejecutivo Comercial", "ACME", "https://example.com", description="Ingeniería Industrial como requisito."),
        "Ventas / Comercial",
    )
    assert core.tier == "core"
    assert core.score >= 0.8
    assert commercial.tier == "out_of_focus"
    assert "excluido" in commercial.evidence


def test_relevance_does_not_treat_education_only_as_core():
    result = infer_relevance(
        RawJob("x", "Asistente administrativo", "ACME", "https://example.com", description="Se requiere Ingeniería Industrial."),
        "Procesos",
    )
    assert result.tier == "adjacent"


def test_classification_does_not_match_sop_inside_soporte():
    result = classify(RawJob("x", "Soporte junior ERP", "ACME", "https://example.com", description="Soporte de usuarios y sistemas."))
    assert not any(name == "S&OP" for name, _ in result.skills)


def test_score_is_traceable_and_bounded():
    job = RawJob("x", "Practicante de Procesos", "ACME", "https://example.com", location="Lima")
    result = score_job(
        job,
        {"skills": {"Excel": "advanced"}, "areas": ["Procesos"], "locations": ["Lima"]},
        {"Excel", "SQL"},
        "Procesos",
    )
    assert 0 <= result.total <= 100
    assert result.strong_matches == ["Excel"]
    assert result.missing_skills == ["SQL"]


def test_salary_extraction_requires_explicit_currency():
    result = extract_salary("Remuneración: S/ 1,200 a S/ 1,500 mensuales")
    assert result is not None
    assert result.minimum == 1200
    assert result.maximum == 1500
    assert result.currency == "PEN"
    assert result.period == "mensuales"
    assert extract_salary("Código de oferta 2026 y celular 999999999") is None
    range_result = extract_salary("Remuneración mensual: S/ 1,300 a S/ 1,500")
    assert range_result is not None
    assert range_result.minimum == 1300
    assert range_result.maximum == 1500
    nearby_period = extract_salary("Trabajo con atención por horas. Remuneración: S/ 3,500 mensuales")
    assert nearby_period is not None
    assert nearby_period.period == "mensuales"
    assert extract_salary("S/565; horario part-time") is not None
    assert extract_salary("S/565; horario part-time").minimum == 565


def test_job_file_import_maps_portal_fields(tmp_path):
    path = tmp_path / "linkedin.csv"
    path.write_text("title,company,url,location,work_mode\nAnalista BI,ACME,https://example.com/job,Lima,hybrid\n")
    jobs = load_job_file(str(path), "linkedin")
    assert jobs[0].source == "linkedin"
    assert jobs[0].title == "Analista BI"
    assert jobs[0].work_mode == "hybrid"


def test_job_file_import_maps_publication_date(tmp_path):
    path = tmp_path / "jobs.json"
    path.write_text('[{"title":"Analista","url":"https://example.com","published_at":"2026-09-11T10:00:00"}]')
    jobs = load_job_file(str(path), "linkedin")
    assert jobs[0].published_at is not None


def test_computrabajo_parses_relative_publication_date():
    parsed = ComputrabajoSource._parse_published_at("Hace 2 días")
    assert parsed is not None
    assert (datetime.now(UTC).date() - parsed.date()).days == 2
    recent = ComputrabajoSource._parse_published_at("Hace 41 minutos")
    assert recent is not None
    assert 0 <= (datetime.now(UTC) - recent).total_seconds() < 3600
    job = ComputrabajoSource()._to_job({
        "title": "Analista",
        "company": "ACME",
        "url": "https://computrabajo.com/oferta",
        "publishedDate": "Hace 1 hora",
    })
    assert job.published_at is not None


def test_computrabajo_detail_is_extracted_without_replacing_public_url():
    source = ComputrabajoSource()
    detail = source._extract_detail({"structuredContent": {"job": {
        "offerId": "ABC123",
        "description": "Funciones de procesos y mejora continua.",
        "salary": "S/ 1,650 mensuales",
        "workday": "Presencial",
        "contractType": "Planilla",
    }}})
    merged = source._merge_detail(
        {"offerId": "ABC123", "url": "https://pe.computrabajo.com/oferta-publica", "publishedDate": "Ayer"},
        detail,
    )
    job = source._to_job(merged)
    assert job.url == "https://pe.computrabajo.com/oferta-publica"
    assert "mejora continua" in (job.description or "")
    assert "Jornada: Presencial" in (job.description or "")
    assert job.employment_type == "Planilla"


def test_freshness_excludes_old_undated_and_future_jobs():
    from datetime import datetime

    today = datetime(2026, 9, 11, tzinfo=UTC)
    recent = RawJob("x", "A", "C", "https://a", published_at=datetime(2026, 9, 1, tzinfo=UTC))
    old = RawJob("x", "B", "C", "https://b", published_at=datetime(2026, 8, 27, tzinfo=UTC))
    future = RawJob("x", "C", "C", "https://c", published_at=datetime(2026, 9, 12, tzinfo=UTC))
    undated = RawJob("x", "D", "C", "https://d")
    assert is_recent(recent.published_at, 14, today)
    assert not is_recent(old.published_at, 14, today)
    assert not is_recent(future.published_at, 14, today)
    assert filter_recent_jobs([recent, old, future, undated], 14, today)[1] == 3


def test_json_safe_converts_nan_to_null():
    assert _json_safe({"empty": float("nan"), "nested": [float("nan"), "ok"]}) == {
        "empty": None,
        "nested": [None, "ok"],
    }


def test_enrichment_infers_mode_sector_and_schedule():
    job = RawJob(
        "x",
        "Asistente de logística",
        "ACME",
        "https://example.com",
        location="Lima",
        description="Modalidad híbrida. Apoyo en operaciones logísticas y 20 horas semanales.",
    )
    assert infer_work_mode(job) == "hybrid"
    assert infer_sector(job) == "Logística y transporte"
    assert extract_schedule(job)[0] == 20


def test_explicit_onsite_wins_over_ambiguous_remote_mention():
    job = RawJob("x", "Especialista ERP", "ACME", "https://example.com", work_mode="remote", description="Evaluamos trabajo remoto, pero el horario es presencial de lunes a viernes.")
    assert infer_work_mode(job) == "onsite"


def test_salary_normalization_rejects_malformed_pen_value():
    assert normalize_salary(4, None, "PEN", "mensual") == (None, None, None)
    assert normalize_salary(100, None, "PEN", "mensual") == (None, None, None)


def test_geolocation_resolves_common_lima_aliases():
    assert infer_location("Lurin, LIM, PE").label == "Lurín"
    assert infer_location("Vitarte, LIM, PE").label == "Ate"
    assert infer_location("Ventanilla, CAL, PE").label == "Ventanilla"
    assert infer_location("Campoy, LIM, PE").label == "San Juan de Lurigancho"
    assert infer_location("Santa Clara, LIM, PE").label == "Ate"
    assert infer_location("Chaclacayo, LIM, PE").label == "Chaclacayo"
    assert infer_location("Barranco, LIM, PE").label == "Barranco"


def test_jobspy_cleans_nan_optional_fields():
    job = JobSpySource()._row_to_job({"title": "Analista", "company": float("nan"), "job_url": "https://example.com"})
    assert job.company is None


def test_import_maps_linkedin_application_status():
    from radar.importers import _row_to_job

    job = _row_to_job({"title": "Analista", "url": "https://example.com", "application_status": "No se aceptan solicitudes"}, "linkedin")
    assert job.application_status == "closed"


def _job(title, description=""):
    return RawJob("x", title, "ACME", "https://example.com", description=description)


def test_classifier_uses_title_stems_and_ignores_generic_description_terms():
    assert classify(_job("Almacenero", "Atender requerimientos de las áreas y proyectos internos.")).primary_area.value == "Supply Chain, logística y compras"
    assert classify(_job("Analista de compras", "Elaborar requerimientos, SQL y ERP.")).primary_area.value == "Supply Chain, logística y compras"
    assert classify(_job("Asistente administrativo", "Atender requerimientos y proyectos.")).primary_area.value == "Otras"
    assert classify(_job("Practicante de Marketing", "Mejora de procesos")).primary_area.value == "Otras"


def test_salary_extraction_ignores_placeholders_and_unescapes_markdown():
    assert extract_salary("Salario: S/ 1.00") is None
    assert extract_salary("Sueldo: S/ 1 - S/ 2") is None
    escaped = extract_salary(r"Tipo de puesto: Tiempo completo. Sueldo: S/.1,200\.00 \- S/.1,500\.00 al mes")
    assert escaped is not None and (escaped.minimum, escaped.maximum) == (1200.0, 1500.0)
    mixed = extract_salary("Bono de movilidad S/ 100. Remuneración básica: S/ 1,800 a S/ 2,200 mensuales.\nSalario: S/ 1.00")
    assert mixed is not None and (mixed.minimum, mixed.maximum) == (1800.0, 2200.0)
    bare = extract_salary("Ingreso a planilla. Sueldo 1400 a 1700 según evaluación.")
    assert bare is not None and (bare.minimum, bare.maximum) == (1400.0, 1700.0)
    from_title = extract_salary("Ingreso inmediato a planilla.", "Coordinador de Operaciones (2300 a 2500)")
    assert from_title is not None and (from_title.minimum, from_title.maximum) == (2300.0, 2500.0)
    assert extract_salary("Empresa global con ingresos de $83 billion anuales.") is None


def test_seniority_prioritizes_title_and_emits_mid_and_senior():
    intern_job = _job("Practicante Pre Profesional de Procesos", "Reporta directamente al Jefe de Planta y Gerente.")
    assert infer_seniority(intern_job) == "intern"
    mid_job = _job("Analista de Mejora Continua", "Experiencia mínima de 2 años en plantas industriales.")
    assert infer_seniority(mid_job) == "mid"
    senior_job = _job("Jefe de Operaciones", "Liderar el equipo de planta.")
    assert infer_seniority(senior_job) == "senior"


def test_infer_job_location_recovers_district_without_false_positive_substrings():
    from radar.geolocation import infer_job_location

    assert infer_job_location("Lima", "Analista de Planeamiento Estratégico", "Gestión estratégica corporativa").label == "Lima"
    assert infer_job_location("Lima", "Ingeniero de Planta - Lurín", "Trabajo presencial").label == "Lurín"
    assert infer_job_location("Lima", "Analista de Logística", "Lugar de trabajo: Ate Vitarte. Horario lunes a viernes.").label == "Ate"


def test_target_titles_are_core_and_operational_titles_are_out_of_focus():
    def tier(title, area="Otras"):
        return infer_relevance(RawJob("x", title, "ACME", "https://example.com", description="Excel y SAP."), area)

    assert tier("Analista de Control de Gestión").tier == "core"
    assert tier("Analista BI / Business Intelligence").tier == "core"
    assert tier("Comprador Junior").tier == "core"
    assert tier("Supervisor de Inventarios y Almacenes").tier == "core"
    operator = tier("Operario de Almacén", "Supply Chain, logística y compras")
    assert operator.tier == "out_of_focus" and "operativo" in operator.evidence
    assert tier("Practicante de Ingeniería Industrial").tier == "adjacent"


def test_secondary_target_and_target_filter():
    from datetime import UTC, datetime

    from radar.db.queries import list_jobs
    from radar.db.repository import ingest_jobs as store

    job = infer_relevance(RawJob("x", "Analista de Compras", "ACME", "https://example.com"), "Otras")
    assert job.tier == "core" and "prioridad 2" in job.evidence
    store([
        RawJob("t", "Analista BI", "A", "https://e.com/bi", location="Lima", description="Power BI",
               published_at=datetime.now(UTC)),
        RawJob("t", "Ingeniero de Procesos", "B", "https://e.com/p", location="Lima", description="Mejora continua",
               published_at=datetime.now(UTC)),
    ])
    titles = {j["title"] for j in list_jobs(relevance_tier="target", limit=None, max_age_days=7)}
    assert "Analista BI" in titles and "Ingeniero de Procesos" not in titles
