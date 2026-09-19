import json
from datetime import UTC, datetime

import pytest

from radar import cv_targets
from radar.db.database import connection
from radar.db.repository import ingest_jobs
from radar.domain.models import RawJob


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "radar.db"))
    (tmp_path / "targets").mkdir()
    return tmp_path


@pytest.fixture
def seeded_job(data):
    ingest_jobs([RawJob(source="test", title="Analista de Datos", company="ACME", url="https://example.com/1",
                        location="Miraflores, Lima", description="Requiere SQL", published_at=datetime.now(UTC))])
    with connection() as conn:
        return conn.execute("SELECT id FROM jobs").fetchone()[0]


def _target(directory, name, items):
    payload = {"title": name, "company": name, "hypothetical": False, "photo_path": "/etc/passwd",
               "sections": {"tools": items}}
    (directory / "targets" / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_targets_are_always_hypothetical_and_hide_paths(data):
    _target(data, "a", [])
    [target] = cv_targets.load_targets()
    assert target["hypothetical"] is True
    assert "photo_path" not in target


def test_matrix_takes_worst_status_and_sorts_by_open_gaps(data):
    _target(data, "a", [
        {"text": "SQL", "key": "sql", "status": "cubierto"},
        {"text": "Python", "key": "python", "status": "parcial"},
        {"text": "Python ETL", "key": "python", "status": "falta"},
    ])
    _target(data, "b", [
        {"text": "SQL", "key": "sql", "status": "cubierto"},
        {"text": "Python", "key": "python", "status": "parcial"},
        {"text": "sin clave", "status": "falta"},
    ])
    matrix = cv_targets.build_matrix(cv_targets.load_targets())
    assert [row["key"] for row in matrix["rows"]] == ["python", "sql"]
    assert matrix["rows"][0]["cells"] == {"a": "falta", "b": "parcial"}
    assert matrix["rows"][0]["open_count"] == 2


def test_missing_data_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "radar.db"))
    assert cv_targets.load_profile() is None
    assert cv_targets.load_targets() == []
    assert cv_targets.photo_path() is None


def test_validate_target_requires_evidence_and_valid_enums():
    errors = cv_targets.validate_target({"sections": {"tools": [
        {"text": "SQL", "origin": "explicito"},
        {"text": "Python", "origin": "inferido"},
        {"text": "Excel", "origin": "tipico", "status": "cubierto"},
        {"text": "Git", "origin": "raro"},
    ]}, "gaps": [{"kind": "mañana", "action": "x"}]})
    assert len(errors) == 5


def test_save_target_sets_hypothetical_and_distance(seeded_job, tmp_path):
    (tmp_path / "cv_master.json").write_text(json.dumps({"home_district": "La Victoria"}), encoding="utf-8")
    result = cv_targets.save_target(seeded_job, {"hypothetical": False, "sections": {"tools": [
        {"text": "SQL", "origin": "explicito", "quote": "SQL", "key": "sql", "status": "falta"}]}, "gaps": []})
    assert result["saved"] is True
    [target] = cv_targets.load_targets()
    assert target["hypothetical"] is True
    assert target["location"]["km_from_home"] is not None


def test_districts_near_orders_by_distance():
    near = cv_targets.districts_near("cerca de Miraflores", 3)
    assert near[0] == {"district": "Miraflores", "km": 0.0}
    assert near[1]["km"] <= near[2]["km"]
