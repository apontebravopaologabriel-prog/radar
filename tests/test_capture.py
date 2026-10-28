import time

import pytest

from radar import capture
from radar.careers import load_pack


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "radar.db"))
    monkeypatch.delenv("RADAR_CITIES", raising=False)


def test_plan_uses_pack_queries_for_lima_and_short_queries_for_cities():
    pack = load_pack("industrial_engineering")
    steps = capture.plan_steps(["Arequipa"], True, pack.market_queries, pack.queries)
    lima = [s for s in steps if s["location"] == "Lima"]
    assert len(lima) == 2 * len(pack.market_queries) == 32 and {s["limit"] for s in lima} == {50}
    arequipa = [s for s in steps if s["location"] == "Arequipa"]
    assert len(arequipa) == 2 * len(pack.queries) and {s["limit"] for s in arequipa} == {25}
    no_ct = capture.plan_steps([], False, pack.market_queries, pack.queries)
    assert {s["source"] for s in no_ct} == {"jobspy"}


def test_cities_come_from_argument_or_environment(monkeypatch):
    assert capture._cities("Arequipa, Trujillo,") == ["Arequipa", "Trujillo"]
    monkeypatch.setenv("RADAR_CITIES", "Piura")
    assert capture._cities(None) == ["Piura"]
    assert capture._cities("") == []


def test_one_failing_or_hanging_step_does_not_stop_the_capture(monkeypatch):
    calls = []

    def fake_ingestion(source, query, location, limit, max_age):
        calls.append((source, query))
        if source == "computrabajo" and len(calls) % 2 == 0:
            raise RuntimeError("portal caído")
        if query == "analista de operaciones":
            time.sleep(2)  # excede el tiempo de paso
        return {"created": 2}

    monkeypatch.setattr("radar.pipeline.run_ingestion", fake_ingestion)
    logs: list[str] = []
    summary = capture.run_capture(log=logs.append, step_timeout=0.3)
    pack = load_pack("industrial_engineering")
    assert summary["steps"] == 2 * len(pack.market_queries)
    assert any("analista de operaciones" in item for item in summary["failed"])
    assert any("portal caído" in line for line in logs) and any("sin respuesta" in line for line in logs)
    assert summary["created"] > 0 and len(calls) == summary["steps"]
    assert logs[-2].startswith("SUMMARY:") and "failed" in logs[-2]
    assert any(line.startswith("[backup: sqlite]") for line in logs)  # los pasos de calidad corren siempre


def test_computrabajo_can_be_disabled_by_environment(monkeypatch):
    seen = set()
    monkeypatch.setattr("radar.pipeline.run_ingestion", lambda source, *a: seen.add(source) or {"created": 0})
    monkeypatch.setenv("RADAR_COMPUTRABAJO_ENABLED", "0")
    capture.run_capture(log=lambda _: None)
    assert seen == {"jobspy"}


def test_local_maintenance_is_never_abandoned_by_the_step_timeout(monkeypatch):
    """Regresión: repair-data tardó más que el límite, se abandonó y su hilo siguió bloqueando la base."""
    import time as _time

    monkeypatch.setattr("radar.pipeline.run_ingestion", lambda *a: {"created": 0})
    finished = []

    def slow_repair():
        _time.sleep(0.5)
        finished.append(True)
        return {}

    monkeypatch.setattr("radar.db.repository.repair_data_quality", slow_repair)
    logs: list[str] = []
    summary = capture.run_capture(log=logs.append, step_timeout=0.1, computrabajo=False)
    assert finished == [True] and not any("repair-data" in item for item in summary["failed"])
