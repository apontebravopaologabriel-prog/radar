"""Paraphrased diagnostic cases; these are regressions, not an accuracy estimate."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from radar.careers import CareerPackError, load_pack, parse_pack
from radar.classification_text import job_text
from radar.classify import classify
from radar.domain.models import RawJob
from radar.taxonomy import infer_relevance


def result(title, description, market="sistemas_software"):
    pack = load_pack(market)
    raw = RawJob("test", title, "Example", "https://example.com/role", description=description)
    classified = classify(raw, pack)
    relevance = infer_relevance(raw, classified.primary_area.value, pack,
                                [a.value for a in classified.secondary_areas])
    return classified, relevance


@pytest.mark.parametrize(("title", "description"), [
    ("Asistente de inventario", "Funciones: Contar stock y conciliar inventarios.\nEmpresa: Movemos contenedores y almacenamos contenedores maritimos."),
    ("Supervisor de Infraestructura", "Funciones: Supervisar pintura, soldadura y gasfiteria de edificios."),
    ("Analista de costos e inventarios", "Funciones: Registrar movimientos en Dynamics 365 y conciliar activos en Dynamics 365.\nRequisitos: Bachiller en Contabilidad."),
    ("Asistente administrativo", "Requisitos: Experiencia implementando SAP y ERP. Python, AWS, Docker y Power BI."),
    ("Planificador de produccion", "Requisitos: Python, Java, AWS, cloud, Kubernetes.\nFunciones: Planificar la produccion y las compras."),
    ("Analista de laboratorio clinico", "Funciones: Procesar muestras biologicas y controlar reactivos.\nRequisitos: Tecnologo Medico, sistemas de gestion de calidad."),
    ("Analista QA textil", "Funciones: Revisar calidad de prendas y procesos de costura."),
    ("Soporte comercial", "Funciones: Atender solicitudes comerciales y emitir cotizaciones.\nRequisitos: Manejo de bases de datos y Power BI."),
    ("Asistente", "No desarrolla software. No implementa SAP. No realiza despliegues con Docker."),
    ("Analista de importaciones", "Gestionar contenedores maritimos y revisar contenedores en el puerto."),
    ("Responsable de mantenimiento", "Mantenimiento de infraestructura fisica, pintura de infraestructura y reparaciones civiles."),
    ("Contador", "Conciliar facturas y registrar operaciones en SAP.\nEmpresa: Desarrollamos software y desplegamos aplicaciones con Docker."),
    ("Asistente de marketing", "Requisitos: Ingenieria de Sistemas o Industrial.\nFunciones: Coordinar eventos."),
    ("Supervisor de Mantenimiento", "Garantizar procedimientos de seguridad y de software de gestion de mantenimiento."),
    ("Analista de Planeamiento Financiero", "Consolidar informacion de aplicaciones, desarrollando modelos financieros."),
    ("Jefe de Mantenimiento", "Identificar vulnerabilidades y fortalecer controles internos de la tienda."),
    ("Supervisor Zonal", "Supervisar vigilancia privada e identificar vulnerabilidades y riesgos de los servicios."),
    ("Desarrollador Curricular", "Disenar contenidos educativos y recursos digitales."),
    ("Asistente de Sistemas Integrados de Gestion", "Auditorias ISO, calidad y seguimiento de acciones correctivas."),
    ("Auxiliar de Almacen", "Gestionar la base de datos de inventarios y actualizar los registros."),
    ("Supervisor", "Supervisar agentes de seguridad y coordinar turnos."),
    ("Planificador", "Sobre nosotros.\nDesarrollamos aplicaciones de maquinaria minera.\nFunciones:\nPlanificar el armado de equipos."),
    ("Programador de Ruta Nacional", "Programar rutas y asignar flota de transporte."),
    ("Programador de Flota", "Coordinar viajes y transporte de materiales."),
    ("Senior Project Planner", "Develop and maintain project schedules using planning software such as Primavera."),
    ("Modelador Mecanico de Estructuras y Tuberias", "Diseno industrial segun normas como ASME, AISC y AWS."),
])
def test_unrelated_roles_do_not_enter_systems(title, description):
    _, relevance = result(title, description)
    assert relevance.tier == "out_of_focus"


@pytest.mark.parametrize(("title", "description", "area"), [
    ("Desarrollador Backend", "Requisitos: Java y Docker", "Desarrollo de software"),
    ("Analista", "Funciones: Desarrollar aplicaciones web con Python.", "Desarrollo de software"),
    ("DevOps Engineer", "Requisitos: Docker y Kubernetes", "DevOps y SRE"),
    ("Especialista", "Funciones: Automatizar despliegues con Docker y Kubernetes.", "DevOps y SRE"),
    ("Cloud Engineer", "AWS", "Infraestructura y cloud"),
    ("Administrador", "Funciones: Administrar servidores Linux y configurar Windows Server.", "Infraestructura y cloud"),
    ("Analista Funcional SAP", "Requisitos: Industrial o Sistemas", "Análisis de sistemas y producto"),
    ("Analista", "Funciones: Configurar modulos SAP y levantar requerimientos funcionales.", "Análisis de sistemas y producto"),
    ("Analista de datos", "Power BI", "Data / BI"),
    ("Analista Administrativo", "Funciones: Construir dashboards en Power BI y automatizar controles.", "Data / BI"),
    ("Data Engineer", "Python", "Datos e inteligencia artificial"),
    ("Especialista", "Funciones: Desarrollar modelos predictivos con machine learning.", "Datos e inteligencia artificial"),
    ("Analista de ciberseguridad", "SIEM", "Ciberseguridad"),
    ("QA Automation", "Selenium", "Calidad y pruebas (QA)"),
    ("Tecnico informatico", "Funciones: Instalar equipos de computo.", "Soporte TI y redes"),
    ("Scrum Master", "Software", "Gestión de proyectos TI"),
    ("Consultor de SAP ABAP", "Requirements: ABAP", "Análisis de sistemas y producto"),
    ("Infrastructure engineer", "Requirements: Linux", "Infraestructura y cloud"),
    ("Specialist", "Responsibilities:\nDevelop web applications with Python.", "Desarrollo de software"),
    ("Analista de Soporte de Aplicaciones", "Atender incidentes", "Soporte TI y redes"),
])
def test_real_digital_occupations_remain_in_their_market(title, description, area):
    classified, relevance = result(title, description)
    assert classified.primary_area.value == area
    assert relevance.tier in {"core", "adjacent"}


def test_shared_role_keeps_independent_market_evidence():
    desc = ("Requisitos: Ingenieria Industrial o Sistemas.\nFunciones: Configurar modulos SAP, "
            "relevar procesos logisticos y optimizar la cadena de suministro.")
    for market in ("industrial_engineering", "sistemas_software"):
        _, relevance = result("Analista Funcional SAP", desc, market)
        assert relevance.tier in {"core", "adjacent"}


def test_industrial_occupations_are_separated_from_trade_and_clinical_roles():
    for title, desc in [
        ("Supervisor de produccion industrial", "Planificar produccion y supervisar productividad. Requiere Industrial."),
        ("Planificador de mantenimiento", "Planificar presupuesto, analizar MTBF y disponibilidad de activos."),
    ]:
        assert result(title, desc, "industrial_engineering")[1].tier in {"core", "adjacent"}
    for title, desc in [
        ("Responsable de mantenimiento", "Buscamos operarios de mantenimiento. Lubricar y reparar componentes."),
        ("Analista de laboratorio clinico", "Analistas de laboratorio clinico. Procesamiento de muestras biologicas, calidad e inventarios."),
    ]:
        assert result(title, desc, "industrial_engineering")[1].tier == "out_of_focus"


@pytest.mark.parametrize("title", [
    "Tecnico de aire acondicionado", "Tecnico general de mantenimiento",
    "Tecnico de refrigeracion", "Mecanico de mantenimiento",
])
def test_physical_trade_titles_do_not_become_industrial_engineering_roles(title):
    _, relevance = result(title, "Reparar y lubricar equipos de mantenimiento industrial.", "industrial_engineering")
    assert relevance.tier == "out_of_focus"


def test_secondary_area_and_target_title_cannot_override_the_primary_occupation():
    pack = load_pack("sistemas_software")
    raw = RawJob("test", "Analista", "Example", "https://example.com", description="Datos y software")
    assert infer_relevance(raw, "Ventas / Comercial", pack, ["Desarrollo de software"]).tier == "out_of_focus"
    industrial = load_pack("industrial_engineering")
    assert infer_relevance(replace(raw, title="Servicios generales"), "Otras", industrial).tier == "out_of_focus"
    assert infer_relevance(raw, "Procesos", pack).tier == "out_of_focus"


def test_context_terms_use_word_boundaries():
    pack = replace(load_pack("sistemas_software"), area_evidence_rules={}, context_terms=("ti", "api"))
    raw = RawJob("test", "Asistente", "Example", "https://example.com", description="Actividades y capital")
    assert infer_relevance(raw, "Desarrollo de software", pack).score == 0.68


def test_sections_keep_requirements_and_resume_duties_after_employer_text():
    text = job_text("Empresa: Administramos servidores Linux.\n**FUNCIONES:**\nConfigurar modulos SAP.\n"
                    "**REQUISITOS:** Python y Docker.\nBeneficios: Cursos de Power BI.")
    assert text.duties == ("configurar modulos sap",)
    assert "python" in text.requirements
    assert "servidores" not in text.role and "cursos" not in text.role


def test_new_rules_are_validated_and_optional_for_custom_packs():
    from dataclasses import asdict

    # Loading old packs remains covered by the existing custom-pack tests.
    raw = {"id": "x", "name": "X", "areas": {"core": ["A"]}, "area_rules": {"A": ["alpha"]},
           "skills": {}, "scoring": asdict(load_pack("sistemas_software"))["weights"]}
    for rule in [{"title_any": "software"}, {"duty_groups": [{"actions": [], "objects": ["sap"]}]}]:
        with pytest.raises(CareerPackError):
            parse_pack({**raw, "area_evidence_rules": {"A": rule}})


def test_ingestion_and_rebuild_share_versioned_context_rules(tmp_path, monkeypatch):
    from radar import markets
    from radar.db.database import connection
    from radar.db.queries import list_jobs
    from radar.db.repository import ingest_jobs

    monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "radar.db"))
    raw = RawJob("test", "Asistente de inventario", "Example", "https://example.com/stock",
                 description="Contenedores maritimos y contenedores del puerto.", published_at=datetime.now(UTC))
    ingest_jobs([raw])
    assert not list_jobs(market_id="sistemas_software", relevance_tier="core")
    monkeypatch.setattr(markets, "CLASSIFIER_VERSION", "future-engine")
    assert markets.backfill_market("sistemas_software") == 1
    assert markets.backfill_market("sistemas_software") == 0
    with connection() as conn:
        assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1


def test_full_market_scope_includes_bridges_but_excludes_unrelated_roles():
    from radar.db.queries import list_jobs
    from radar.db.repository import ingest_jobs
    from radar.markets import market_skills

    today = datetime.now(UTC)
    ingest_jobs([
        RawJob("test", "Desarrollador Java", "Example", "https://example.com/java", description="Java", published_at=today),
        RawJob("test", "Analista de Power BI", "Example", "https://example.com/bi", description="Power BI", published_at=today),
        RawJob("test", "Asistente de inventario", "Example", "https://example.com/stock", description="Contenedores maritimos", published_at=today),
    ])
    filters = {"market_id": "sistemas_software", "relevance_tier": "market", "max_age_days": 7}
    jobs = list_jobs(**filters)
    assert {job["title"] for job in jobs} == {"Desarrollador Java", "Analista de Power BI"}
    assert market_skills(**filters)["total_jobs"] == len(jobs)


def test_maintenance_backs_up_before_writing_and_preserves_personal_state(monkeypatch):
    import sqlite3
    from pathlib import Path

    from radar import maintenance
    from radar.db.database import connection
    from radar.db.repository import ingest_jobs
    from radar.markets import pack_hash

    ingest_jobs([RawJob("test", "Asistente de inventario", "Example", "https://example.com/stock",
                       description="Contenedores maritimos.")])
    with connection() as conn:
        job_id = conn.execute("SELECT id FROM jobs").fetchone()[0]
        conn.execute("UPDATE jobs SET relevance_tier='core',relevance_evidence='old rules'")
        conn.execute("UPDATE job_market_classifications SET rules_hash='old'")
        conn.execute("INSERT INTO job_user_favorites(job_id,note) VALUES (%s,'keep')", (job_id,))
    saved = maintenance.reclassify_jobs()
    assert Path(saved["backup"]).exists()
    with sqlite3.connect(saved["backup"]) as before:
        assert before.execute("SELECT relevance_evidence FROM jobs").fetchone()[0] == "old rules"
    with connection() as conn:
        assert conn.execute("SELECT note FROM job_user_favorites").fetchone()[0] == "keep"
        rows = conn.execute("SELECT market_id,rules_hash,relevance_tier FROM job_market_classifications").fetchall()
    assert all(h == pack_hash(load_pack(m)) for m, h, _ in rows)
    assert next(t for m, _, t in rows if m == "sistemas_software") == "out_of_focus"

    def failed_backup():
        raise OSError("Backup unavailable")

    monkeypatch.setattr("radar.system.backup_database", failed_backup)
    monkeypatch.setattr(maintenance, "_stored", lambda: pytest.fail("Must not read/modify classification after backup fails"))
    with pytest.raises(OSError, match="Backup unavailable"):
        maintenance.reclassify_jobs()
