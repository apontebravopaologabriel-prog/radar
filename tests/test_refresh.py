import time
from dataclasses import replace
from datetime import UTC, datetime
from threading import Event

import pytest
from fastapi.testclient import TestClient

from radar import refresh
from radar.api import app
from radar.careers import load_pack
from radar.db.repository import save_profile
from radar.domain.models import RawJob


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
    pack = replace(load_pack("industrial_engineering"), queries=("analista BI",), market_queries=("analista BI",))
    monkeypatch.setattr(refresh, "active_pack", lambda: pack)
    monkeypatch.setattr(refresh, "_sources", lambda: ["computrabajo", "jobspy"])
    monkeypatch.setattr(refresh, "_state", refresh.refresh_status())
    monkeypatch.delitem(refresh._state, "market_ids", raising=False)
    searching = Event()
    release = Event()
    calls = []

    class SimulatedSource:
        def __init__(self, name):
            self.name = name

        def search(self, query, location, limit):
            calls.append((self.name, query, location, limit))
            if self.name == "computrabajo":
                searching.set()
                assert release.wait(5), "Test did not release the simulated source"
                raise RuntimeError("fuente caída")
            return [RawJob(self.name, "Analista BI", "Ejemplo", "https://example.com/bi",
                           location=location, description="Power BI", published_at=datetime.now(UTC))]

    monkeypatch.setattr("radar.source_fetch.fetch_jobs",
                        lambda source, query, location, limit, timeout: SimulatedSource(source).search(query, location, limit))
    api = TestClient(app)
    assert "market_ids" not in api.get("/api/refresh/status").json()
    assert api.post("/api/refresh", json={"limit": 51}).status_code == 422
    assert api.post("/api/refresh", json={"market_ids": ["missing_market"]}).status_code == 422

    try:
        started = api.post("/api/refresh", json={"places": ["Miraflores"], "limit": 5})
        assert started.status_code == 202
        assert started.json()["total"] == 2 and started.json()["market_ids"] == [pack.id]
        assert searching.wait(5), "Simulated source did not start"
        running = api.get("/api/refresh/status").json()
        assert running["running"] and running["current"] == "computrabajo · analista BI · Lima"
        assert running["started_at"] and running["finished_at"] is None
        assert api.post("/api/refresh", json={}).status_code == 409
    finally:
        release.set()
        state = _wait()

    assert api.get("/api/refresh/status").json() == state
    assert state["done"] == state["total"] == 2 and state["created"] == 1
    assert state["errors"] == ["fuente caída"] and state["current"] is None
    assert state["finished_at"] >= state["started_at"]
    assert calls == [(source, "analista BI", "Lima", 5) for source in ("computrabajo", "jobspy")]
    assert [job["title"] for job in api.get("/api/jobs").json()["jobs"]] == ["Analista BI"]


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


def test_all_three_markets_use_broad_queries_fairly_without_duplicate_downloads(monkeypatch):
    from radar.careers import load_pack
    ids = ['industrial_engineering', 'sistemas_software', 'ingenieria_mecanica']
    packs = [load_pack(key) for key in ids]
    seen = []
    monkeypatch.setattr(refresh, '_sources', lambda: ['computrabajo'])
    monkeypatch.setattr(refresh, '_run_step', lambda step: seen.append(step) or {})
    refresh.start_refresh(market_ids=ids)
    _wait()
    assert [step['query'] for step in seen[:3]] == [p.market_queries[0] for p in packs]
    expected = {q for p in packs for q in (*p.queries, *p.market_queries)}
    assert {step['query'] for step in seen} == expected
    assert len(seen) == len(expected)
    assert all(step['limit'] == 50 for step in seen)
    assert all(step['market_ids'] == [p.id for p in packs if step['query'] in (*p.queries, *p.market_queries)] for step in seen)
    assert load_pack('ingenieria_mecanica').name == 'Ingeniería Mecánica'
