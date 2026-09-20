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
    assert {"industrial_engineering", "contabilidad"} <= ids
    for pack in list_packs():
        assert abs(sum(pack.weights.values()) - 1) < 1e-9


def test_same_engine_classifies_by_pack():
    accounting = load_pack("contabilidad")
    industrial = load_pack("industrial_engineering")
    job = _job("Practicante contable", "Conciliaciones bancarias, SUNAT y Excel")
    result = classify(job, accounting)
    assert result.primary_area.value == "Contabilidad" or result.primary_area.value == "Tributación"
    assert {n for n, _ in result.skills} >= {"Excel", "SUNAT", "Conciliaciones bancarias"}
    assert infer_relevance(job, result.primary_area.value, accounting).tier == "core"
    # El mismo texto no es núcleo para Ingeniería Industrial.
    other = classify(job, industrial)
    assert infer_relevance(job, other.primary_area.value, industrial).tier != "core"


def test_industrial_pack_keeps_previous_behavior():
    pack = load_pack("industrial_engineering")
    job = _job("Practicante de Mejora Continua", "Requiere Excel, Power BI y Lean")
    assert classify(job, pack).primary_area.value == "Mejora continua"
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

    set_setting("career", "contabilidad")
    ingest_jobs([_job("Asistente contable", "NIIF y Excel")])
    profile_id = save_profile("Ana", None, ["Contabilidad"], ["Lima"], [], {"Excel": "advanced"})
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
