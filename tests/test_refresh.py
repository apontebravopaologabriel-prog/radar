import time

import pytest
from fastapi.testclient import TestClient

from radar import refresh
from radar.api import app
from radar.db.repository import save_profile


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "radar.db"))
    monkeypatch.delenv("RADAR_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(refresh, "_sources", lambda: ["computrabajo"])


def _wait():
    for _ in range(100):
        if not refresh.refresh_status()["running"]:
            return refresh.refresh_status()
        time.sleep(0.02)
    raise AssertionError("la actualización no terminó")


def test_locations_map_districts_to_lima_and_cities_to_themselves():
    assert refresh.search_locations(["San Isidro", "Ate", "Arequipa", "Marte"]) == ["Lima", "Arequipa"]
    assert refresh.search_locations([]) == ["Lima"]
    save_profile("Ana", None, [], ["Cusco"], [], {})
    assert refresh.search_locations() == ["Cusco"]


def test_refresh_runs_steps_collects_errors_and_allows_one_at_a_time(monkeypatch):
    calls = []

    def fake(step):
        calls.append(step)
        if "logistica" in step["query"]:
            raise RuntimeError("fuente caída")
        return {"created": 3}

    monkeypatch.setattr(refresh, "_run_step", fake)
    api = TestClient(app)
    started = api.post("/api/refresh", json={"places": ["Miraflores"], "limit": 5})
    assert started.status_code == 202 and started.json()["total"] >= 1
    state = _wait()
    assert state["done"] == state["total"] and state["created"] >= 3
    assert all(c["location"] == "Lima" and c["source"] == "computrabajo" for c in calls)
    assert api.get("/api/refresh/status").json()["running"] is False


def test_custom_career_endpoint_activates_it_and_refresh_uses_its_queries(monkeypatch):
    api = TestClient(app)
    res = api.post("/api/career/custom", json={"name": "Derecho", "areas": {"Laboral": ["planillas"]},
                                                "skills": ["Redacción legal"], "queries": ["abogado laboral"]})
    assert res.status_code == 200 and res.json()["active"] == "custom_derecho"
    assert api.post("/api/career/custom", json={"name": "X", "areas": {}}).status_code == 422
    seen = []
    monkeypatch.setattr(refresh, "_run_step", lambda c: seen.append(c) or {})
    api.post("/api/refresh", json={})
    _wait()
    assert seen and all(c["query"] == "abogado laboral" for c in seen)
