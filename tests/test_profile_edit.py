import json
from datetime import UTC, datetime

import pytest

from radar import cv_targets, profile_edit, tools
from radar.db import repository
from radar.db.database import connection
from radar.db.queries import get_profile
from radar.db.repository import ingest_jobs, save_profile
from radar.domain.models import RawJob

CV = {"name": "Ana Pérez", "headline": "Ingeniería Industrial", "summary": "Orientado a datos.",
      "home_district": "La Victoria", "contact": {"email": "p@example.com"},
      "preferred_locations": ["Miraflores"], "experience": [{"role": "Auxiliar", "company": "JAS"}]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "radar.db"))
    (tmp_path / "cv_master.json").write_text(json.dumps(CV), encoding="utf-8")
    ingest_jobs([RawJob(source="test", title="Analista", company="ACME", url="https://e.com/1", location="Lima",
                        description="Excel, Power BI y SQL. " * 20, published_at=datetime.now(UTC))])
    save_profile("Ana", "Técnico", ["Data/BI"], ["Miraflores"], ["hybrid"], {"Excel": "intermediate"})
    return tmp_path


def cv_file(env):
    return json.loads((env / "cv_master.json").read_text(encoding="utf-8"))


def test_partial_patch_only_touches_the_given_fields(env):
    result = profile_edit.patch({"home_district": "Miraflores"})
    assert result["changed"] == ["home_district"]
    assert result["diff"]["home_district"] == {"before": "La Victoria", "after": "Miraflores"}
    cv = cv_file(env)
    assert cv["home_district"] == "Miraflores" and cv["summary"] == "Orientado a datos." and cv["experience"]
    profile = get_profile()
    assert profile["target_roles"] == ["Data/BI"] and profile["skills"] == {"Excel": "intermediate"}
    assert result["backup"] and (env / result["backup"]).exists()


def test_unknown_district_is_reported_but_not_blocked(env):
    result = profile_edit.patch({"home_district": "Narnia"})
    assert cv_file(env)["home_district"] == "Narnia" and "no es un distrito" in result["warnings"][0]


def test_name_is_kept_in_sync_between_both_stores(env):
    assert get_profile()["name"] == "Ana"  # deriva heredada: el CV dice «Ana Pérez»
    profile_edit.patch({"name": "Ana G. Pérez", "areas_add": ["Procesos"]})
    assert cv_file(env)["name"] == "Ana G. Pérez" and get_profile()["name"] == "Ana G. Pérez"
    assert get_profile()["target_roles"] == ["Data/BI", "Procesos"]


def test_lists_and_skills_add_remove_and_replace(env):
    profile_edit.patch({"locations_add": ["San Isidro"], "locations_remove": ["miraflores"],
                        "work_modes": ["Remoto", "Presencial"], "skills": {"SQL": "basic", "excel": "advanced"}})
    profile = get_profile()
    assert profile["locations"] == ["San Isidro"]
    assert profile["work_modes"] == ["remote", "onsite"]
    assert profile["skills"] == {"Excel": "advanced", "SQL": "basic"}
    assert cv_file(env)["preferred_locations"] == ["San Isidro"]  # la copia del archivo no queda vieja
    profile_edit.patch({"skills": {"SQL": "remove"}, "areas": ["Procesos"]})
    profile = get_profile()
    assert profile["skills"] == {"Excel": "advanced"} and profile["target_roles"] == ["Procesos"]


def test_invalid_input_writes_nothing(env):
    before = (env / "cv_master.json").read_bytes()
    for bad in ({"skills": {"Klingon": "basic"}}, {"skills": {"Excel": "experto"}}, {"work_modes": ["nube"]},
                {"name": ""}, {"contact": {"email": "no-es-correo"}}, {"contact": {"fax": "1"}},
                {"areas": "no es lista"}, {"foto": "x"}, {"summary": "x" * 700}):
        with pytest.raises(ValueError):
            profile_edit.patch({"headline": "Nuevo titular", **bad})
    assert (env / "cv_master.json").read_bytes() == before and get_profile()["skills"] == {"Excel": "intermediate"}


def test_undo_restores_the_previous_state(env):
    original = profile_edit.current()
    changed = profile_edit.patch({"headline": "Otro", "home_district": "Surco", "contact": {"phone": "999", "email": ""},
                                  "locations_add": ["Callao"], "skills": {"SQL": "basic", "Excel": "advanced"}})
    assert profile_edit.current() != original
    profile_edit.patch(changed["undo"])
    restored = profile_edit.current()
    assert restored == original


def test_no_changes_is_a_noop_and_dry_run_never_writes(env):
    assert profile_edit.patch({"headline": "Ingeniería Industrial"})["changed"] == []
    before = (env / "cv_master.json").read_bytes()
    result = profile_edit.patch({"headline": "Otro"}, dry_run=True)
    assert result["dry_run"] and (env / "cv_master.json").read_bytes() == before


def test_file_is_restored_if_the_database_write_fails(env, monkeypatch):
    before = (env / "cv_master.json").read_bytes()

    def boom(*args, **kwargs):
        raise RuntimeError("base caída")

    monkeypatch.setattr(profile_edit, "save_profile", boom)
    with pytest.raises(RuntimeError):
        profile_edit.patch({"name": "Otro Nombre", "home_district": "Surco"})
    assert (env / "cv_master.json").read_bytes() == before


def test_first_time_profile_is_created_without_touching_unrelated_data(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "radar.db"))
    ingest_jobs([RawJob(source="test", title="Analista", company="ACME", url="https://e.com/1", location="Lima",
                        description="Excel y SQL. " * 20, published_at=datetime.now(UTC))])
    with pytest.raises(ValueError, match="nombre"):
        profile_edit.patch({"areas_add": ["Procesos"]})
    profile_edit.patch({"name": "Ana", "headline": "Ingeniera"})  # solo CV: no crea perfil en la base
    assert get_profile() is None and json.loads((tmp_path / "cv_master.json").read_text(encoding="utf-8"))["name"] == "Ana"
    profile_edit.patch({"areas_add": ["Procesos"], "skills": {"Excel": "basic"}})
    assert get_profile()["name"] == "Ana" and get_profile()["skills"] == {"Excel": "basic"}


def test_completeness_and_agent_facing_pieces(env):
    assert profile_edit.get_full()["completeness"]["percent"] == 100
    profile_edit.patch({"contact": {"email": ""}})
    full = profile_edit.get_full()
    assert full["completeness"]["percent"] < 100 and [m["key"] for m in full["completeness"]["missing"]] == ["contact"]
    profile_edit.patch({"contact": {"phone": "999 111 222"}})
    assert profile_edit.get_full()["completeness"]["percent"] == 100
    lines = tools.PREVIEWS["update_profile_fields"]({"home_district": "Surco", "skills": {"SQL": "basic"}})
    assert any(line.startswith("Distrito: La Victoria → Surco") for line in lines)
    assert tools.PREVIEWS["update_profile_fields"]({"skills": {"Klingon": "basic"}})[0].startswith("No se puede aplicar")
    assert tools.REGISTRY["update_profile_fields"].write and not tools.REGISTRY["get_my_profile"].write
    assert not tools.REGISTRY["update_profile"].chat  # el reemplazo total ya no lo ve el agente de la app
    with pytest.raises(ValueError, match="al menos un campo"):
        tools.REGISTRY["update_profile_fields"].call({})


def test_declared_tools_come_from_the_database_not_from_a_stale_copy(env):
    (env / "cv_master.json").write_text(json.dumps({**CV, "tools_declared_in_db": {"Viejo": "basic"}}), encoding="utf-8")
    declared = cv_targets.load_profile()["tools_declared_in_db"]
    assert declared["Excel"] == "intermediate" and "Viejo" not in declared


def test_api_get_and_patch(env):
    from fastapi.testclient import TestClient

    from radar.api import app

    client = TestClient(app)
    assert client.get("/api/me").json()["profile"]["name"] == "Ana Pérez"
    ok = client.patch("/api/me", json={"headline": "Nuevo"})
    assert ok.status_code == 200 and ok.json()["diff"]["headline"]["after"] == "Nuevo"
    assert client.patch("/api/me", json={"skills": {"Klingon": "basic"}}).status_code == 422
    assert client.patch("/api/me", json=ok.json()["undo"]).json()["profile"]["headline"] == "Ingeniería Industrial"


def test_repository_can_remove_skills_and_versions_reflect_the_state(env):
    repository.save_profile("Ana", None, [], [], [], {"SQL": "basic"}, reason="prueba")
    repository.save_profile("Ana", None, [], [], [], {}, remove_skills=["SQL"])
    with connection() as conn:
        snapshot = json.loads(conn.execute("SELECT snapshot FROM profile_versions ORDER BY version_number DESC").fetchone()[0])
    assert "SQL" not in snapshot["skills"] and snapshot["skills"] == {"Excel": "intermediate"}
