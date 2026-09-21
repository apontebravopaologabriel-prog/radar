import json
from datetime import UTC, datetime

import pytest

from radar import cv_baseline, cv_plan, tools
from radar.db.database import connection
from radar.db.queries import set_job_favorite
from radar.db.repository import ingest_jobs
from radar.domain.models import RawJob

DESCRIPTION = (
    "Buscamos analista con Excel, Power BI y Python. Experiencia mínima de 3 años en análisis. "
    "Egresado o bachiller de Ingeniería Industrial. " * 6
)
PROFILE = {
    "home_district": "La Victoria",
    "certifications": [{"name": "Microsoft Office Specialist: Excel", "issuer": "UNI", "date": "2025-02"}],
    "experience": [{"role": "Auxiliar", "company": "JAS", "from": "2023-01", "to": "2024-12",
                    "bullets": ["Controles en Excel"], "skills": []}],
    "education": [{"institution": "UPC", "program": "Ingeniería Industrial", "status": "en curso",
                   "to": "2027-07", "skills": []}],
    "gaps_of_evidence": ["Sin proyecto de Python demostrable"],
}


@pytest.fixture
def job(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "radar.db"))
    (tmp_path / "cv_master.json").write_text(json.dumps(PROFILE), encoding="utf-8")
    ingest_jobs([RawJob(source="test", title="Analista", company="ACME", url="https://e.com/1",
                        location="Miraflores, Lima", description=DESCRIPTION,
                        published_at=datetime.now(UTC))])
    with connection() as conn:
        job_id = conn.execute("SELECT id FROM jobs").fetchone()[0]
    set_job_favorite(job_id)
    return job_id


def test_plan_ranks_open_skills_and_separates_structural_gaps(job):
    plan = cv_plan.closure_plan()
    assert plan["targets"] == 1
    rows = {r["key"]: r for r in plan["plan"]}
    assert {"python", "power-bi"} <= set(rows)
    assert "excel" not in rows  # ya cubierto por el certificado
    assert all(r["unlocks"] == 1 and r["gain_points"] >= 0 for r in rows.values())
    assert rows["python"]["gain_points"] > 0
    assert {s["key"] for s in plan["structural"]} >= {"experiencia-previa", "formacion"}
    gains = [r["gain_points"] for r in plan["plan"]]
    assert gains == sorted(gains, reverse=True)


def test_close_gap_with_project_updates_cv_readiness_and_timeline(job):
    before = cv_baseline.ranked_selection()[0]["readiness"]["percent"]
    result = cv_plan.close_gap("Python", "proyecto", "Automatización de reportes",
                               description="Script que consolida reportes semanales de inventario", date="2026-08")
    assert result["counted"] is True and result["gap_note_removed"] is True
    [progress] = result["progress"]
    assert progress["before"] == before and progress["after"] > before
    items = {i["key"]: i for i in cv_baseline.baseline(job)}
    assert items["python"]["status"] == "cubierto" and "proyecto" in items["python"]["reason"]
    assert "python" not in {r["key"] for r in cv_plan.closure_plan()["plan"]}
    [closed] = cv_plan.closure_plan()["closed"]
    assert closed["type"] == "project" and "Python" in closed["detail"]


def test_close_gap_rejects_unsupported_evidence(job):
    with pytest.raises(ValueError, match="descripción"):
        cv_plan.close_gap("Python", "proyecto", "Algo", description="corto")
    with pytest.raises(ValueError, match="kind"):
        cv_plan.close_gap("Python", "curso", "Algo")
    with pytest.raises(ValueError, match="AAAA-MM"):
        cv_plan.close_gap("Python", "certificado", "Python Institute", date="ayer")


def test_certificate_not_naming_the_skill_reports_no_effect(job):
    result = cv_plan.close_gap("Python", "certificado", "Curso de liderazgo", issuer="UPC", date="2026-01")
    assert result["counted"] is False and "mencionar la skill" in result["note"]


def test_reconciles_fit_and_readiness():
    assert "falta evidencia" in cv_baseline.read_of(70, 30, False)
    assert "encaja poco" in cv_baseline.read_of(30, 80, False)
    assert "postular" in cv_baseline.read_of(75, 80, False)
    assert cv_baseline.read_of(None, 80, False) is None
    assert cv_baseline.read_of(70, 30, True) is None


def test_new_tools_are_registered_and_write_flag_is_set():
    assert not tools.REGISTRY["get_closure_plan"].write
    assert tools.REGISTRY["close_gap"].write and tools.REGISTRY["close_gap"].chat
