import pytest

from radar.careers import (
    CareerPackError,
    effective_weights,
    list_packs,
    load_pack,
    parse_pack,
)
from radar.classify import classify
from radar.db.repository import ingest_jobs, recompute_scores, save_profile
from radar.domain.models import RawJob
from radar.settings import set_json_setting
from radar.taxonomy import infer_relevance


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "radar.db"))
    monkeypatch.delenv("RADAR_CAREER", raising=False)


def _job(title, description=""):
    return RawJob("t", title, "ACME", "https://e.com/" + title, location="Lima", description=description)


def test_packs_are_valid_and_distinct():
    ids = {p.id for p in list_packs()}
    assert {"industrial_engineering", "sistemas_software"} <= ids
    for pack in list_packs():
        assert abs(sum(pack.weights.values()) - 1) < 1e-9


def test_same_engine_classifies_by_pack():
    systems = load_pack("sistemas_software")
    industrial = load_pack("industrial_engineering")
    job = _job("Desarrollador Backend Java", "Spring Boot, APIs REST, PostgreSQL y Docker")
    result = classify(job, systems)
    assert result.primary_area.value == "Desarrollo de software"
    assert {n for n, _ in result.skills} >= {"Java", "Spring Boot", "APIs REST", "PostgreSQL", "Docker"}
    assert infer_relevance(job, result.primary_area.value, systems).tier == "core"
    # El mismo texto no es núcleo para Ingeniería Industrial.
    other = classify(job, industrial)
    assert infer_relevance(job, other.primary_area.value, industrial).tier != "core"


def test_industrial_pack_keeps_previous_behavior():
    pack = load_pack("industrial_engineering")
    job = _job("Practicante de Mejora Continua", "Requiere Excel, Power BI y Lean")
    assert classify(job, pack).primary_area.value == "Operaciones y productividad"
    seller = _job("Asesor comercial", "Ingeniería Industrial")
    assert classify(seller, pack).primary_area.value == "Ventas / Comercial"


def test_invalid_pack_is_rejected():
    with pytest.raises(CareerPackError):
        parse_pack({"id": "x", "name": "x", "areas": {}, "area_rules": {}, "skills": {},
                    "scoring": {"area": 1}})
    with pytest.raises(CareerPackError):
        load_pack("../etc/passwd")


def test_user_weights_are_normalized_and_change_scores():
    base = effective_weights()
    assert abs(sum(base.values()) - 1) < 1e-9
    set_json_setting("score_weights", {"location": 0.9})
    tuned = effective_weights()
    assert tuned["location"] > base["location"] and abs(sum(tuned.values()) - 1) < 1e-9


def test_ingest_and_score_use_active_career_pack():
    from radar.settings import set_setting

    set_setting("career", "sistemas_software")
    ingest_jobs([_job("Desarrollador Python", "Django, SQL y Git")])
    profile_id = save_profile("Ana", None, ["Desarrollo de software"], ["Lima"], [], {"Python": "advanced"})
    assert recompute_scores(profile_id) == 1


def test_custom_career_is_created_classified_and_stays_local(tmp_path):
    from radar.careers import active_pack, save_custom_pack, user_packs_dir

    pack = save_custom_pack(
        "Enfermería",
        {"Emergencias": ["triaje", "urgencias"], "Cuidados intensivos": ["uci"]},
        ["BLS", "Manejo de bombas de infusión"],
    )
    assert pack.id == "custom_enfermeria"
    assert user_packs_dir().parent == tmp_path and (user_packs_dir() / "custom_enfermeria.json").is_file()
    job = _job("Enfermera de Urgencias", "Triaje y BLS vigente")
    result = classify(job, pack)
    assert result.primary_area.value == "Emergencias"
    assert {n for n, _ in result.skills} == {"BLS"}
    assert infer_relevance(job, "Emergencias", pack).tier == "core"
    from radar.settings import set_setting

    set_setting("career", pack.id)
    assert active_pack().id == pack.id
    # Se guarda en el catálogo de la base sin romper por skills que ya existían con otro nombre.
    ingest_jobs([_job("Enfermera UCI", "uci")])
    save_custom_pack("Otra", {"Datos": ["sql"]}, ["Sql"])
    ingest_jobs([_job("Analista", "sql")])


def test_custom_career_rejects_bad_input():
    from radar.careers import save_custom_pack

    with pytest.raises(CareerPackError):
        save_custom_pack("", {"A": []})
    with pytest.raises(CareerPackError):
        save_custom_pack("X", {})
    with pytest.raises(CareerPackError):
        save_custom_pack("X", {f"a{i}": [] for i in range(25)})


def test_free_text_profile_areas_match_classified_areas():
    from radar.scoring import area_matches

    wanted = {"procesos y mejora continua", "data/bi y reporting junior", "analista funcional o de operaciones junior"}
    assert area_matches("Procesos", wanted) and area_matches("Mejora continua", wanted)
    assert area_matches("Data / BI", wanted) and area_matches("Operaciones", wanted)
    assert not area_matches("Logística", wanted) and not area_matches(None, wanted)
    assert area_matches("Procesos", {"procesos"})  # igualdad exacta sigue funcionando


# Regresión de clasificación: títulos reales de cada paquete y el área primaria esperada.
SAMPLES = {
    "industrial_engineering": [
        ("Practicante de Mejora Continua", "Lean y Excel", "Operaciones y productividad"),
    ],
    "sistemas_software": [
        ("Desarrollador Backend Java Spring Boot", "APIs REST, microservicios, PostgreSQL", "Desarrollo de software"),
        ("Desarrollador Full Stack React Node.js", "TypeScript, Git, AWS", "Desarrollo de software"),
        ("Data Engineer", "Spark, Airflow, AWS, SQL", "Datos e inteligencia artificial"),
        ("Analista de Ciberseguridad SOC", "SIEM, ISO 27001", "Ciberseguridad"),
        ("QA Automation Engineer", "Selenium, Cypress", "Calidad y pruebas (QA)"),
        ("DevOps Engineer", "Kubernetes, Terraform, CI/CD", "DevOps y SRE"),
        ("Analista Funcional SAP", "levantamiento de requerimientos", "Análisis de sistemas y producto"),
        ("Practicante de Sistemas", "soporte y Excel", "Análisis de sistemas y producto"),
        ("Analista de Power BI", "Power BI, SQL, dashboards", "Data / BI"),
        ("Soporte TI Help Desk", "ITIL", "Soporte TI y redes"),
        ("Ejecutivo Comercial de Software", "ventas", "Ventas / Comercial"),
        ("Cajero de tienda", "", "Otras"),
    ],
}


@pytest.mark.parametrize(
    ("career", "title", "description", "expected"),
    [(career, *row) for career, rows in SAMPLES.items() for row in rows],
)
def test_pack_classification_samples(career, title, description, expected):
    assert classify(_job(title, description), load_pack(career)).primary_area.value == expected


@pytest.mark.parametrize("pack", list_packs(), ids=lambda p: p.id)
def test_every_builtin_pack_is_complete(pack):
    assert pack.queries and pack.market_queries and pack.core_areas and pack.skills
    assert pack.out_of_focus_areas >= {"Otras"}
    assert set(pack.area_rules) <= set(pack.all_areas)
    assert all(pack.area_slugs.get(area) for area in pack.all_areas), "cada área necesita slug"


def test_validate_pack_file_reports_problems(tmp_path):
    import json

    from radar.careers import validate_pack_file

    good = tmp_path / "ok.json"
    good.write_text(json.dumps({
        "id": "ok", "name": "Ok", "areas": {"core": ["A"], "out_of_focus": ["Otras"]}, "area_rules": {"A": ["alfa"]},
        "skills": {"S": {"aliases": ["s"]}}, "scoring": {"area": 0.3, "skills": 0.25, "seniority": 0.15, "education": 0.1,
                                                           "location": 0.1, "preference": 0.1},
        "queries": ["alfa"]}), encoding="utf-8")
    assert validate_pack_file(good)["errors"] == []
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"id": "bad", "name": "Bad", "areas": {"core": ["A"]}, "area_rules": {"B": ["x"]},
                               "skills": {}, "scoring": {"area": 1}}), encoding="utf-8")
    report = validate_pack_file(bad)
    assert report["errors"], report
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    assert validate_pack_file(broken)["errors"]
