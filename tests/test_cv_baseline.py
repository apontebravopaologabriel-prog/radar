import json
from datetime import UTC, datetime

import pytest

from radar import cv_baseline, cv_targets
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
                   "to": "2027-07", "skills": ["Python"]}],
    "tools_declared_in_db": {"Power BI": "basic"},
}


@pytest.fixture
def job(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "radar.db"))
    (tmp_path / "cv_master.json").write_text(json.dumps(PROFILE), encoding="utf-8")
    ingest_jobs([RawJob(source="test", title="Analista", company="ACME", url="https://e.com/1",
                        location="Miraflores, Lima", description=DESCRIPTION,
                        published_at=datetime.now(UTC))])
    with connection() as conn:
        return conn.execute("SELECT id FROM jobs").fetchone()[0]


def _by_key(job_id):
    return {i["key"]: i for i in cv_baseline.baseline(job_id)}


def test_skill_status_comes_from_evidence(job):
    items = _by_key(job)
    assert items["excel"]["status"] == "cubierto" and "certificado" in items["excel"]["reason"]
    assert items["power-bi"]["status"] == "parcial"
    assert items["python"]["status"] == "parcial"
    assert all(i["source"] == "codigo" for i in items.values())


def test_experience_and_degree_blockers(job):
    items = _by_key(job)
    assert items["experiencia-previa"]["status"] == "falta"
    assert items["experiencia-previa"]["blocker"] is True
    assert "3" in items["experiencia-previa"]["quote"]
    # Pide egresado/bachiller y no acepta estudiantes: aún cursas la carrera.
    assert items["formacion"]["status"] == "falta" and items["formacion"]["blocker"] is True


def test_readiness_and_low_data(job):
    result = cv_baseline.readiness(cv_baseline.baseline(job), DESCRIPTION)
    assert result["blockers"] >= 1 and result["low_data"] is False
    assert cv_baseline.readiness([], "corta")["low_data"] is True


def test_selection_is_favorites_and_ranked(job):
    assert cv_baseline.ranked_selection() == []
    set_job_favorite(job)
    [target] = cv_baseline.ranked_selection()
    assert target["id"] == job and target["location"]["km_from_home"] is not None


def test_code_status_overrides_agent_status(job):
    cv_targets.save_target(job, {"sections": {"tools": [
        {"text": "Excel", "origin": "tipico", "key": "excel", "status": "falta"},
        {"text": "Git", "origin": "tipico", "key": "git", "status": "falta"}]}, "gaps": []})
    target = cv_baseline.combined_target(job)
    tools = {i["key"]: i for i in target["sections"]["tools"]}
    assert tools["excel"]["status"] == "cubierto" and tools["excel"]["status_source"] == "codigo"
    assert tools["git"]["status_source"] == "agente"
    matrix = cv_targets.build_matrix([target])
    rows = {r["key"]: r for r in matrix["rows"]}
    assert rows["git"]["agent_cells"] == [job] and rows["excel"]["agent_cells"] == []


def test_soft_skills_are_listed_but_not_scored_and_quotes_are_clean(job):
    with connection() as conn:
        soft = conn.execute("SELECT id FROM skills WHERE skill_type='soft' LIMIT 1").fetchone()[0]
        conn.execute(
            "INSERT INTO job_skills(job_id, skill_id, requirement_type, confidence, evidence) "
            "VALUES (%s, %s, 'unknown', 0.7, %s)", (job, soft, "**texto** -------- sucio " * 20))
    assert "comunicación" not in " ".join(i["label"].lower() for i in cv_baseline.baseline(job))
    assert cv_baseline.soft_skills(job)
    quote = cv_baseline._clean_quote("**texto** ---------- sucio " * 20)
    assert "*" not in quote and "--" not in quote and len(quote) <= 141


def test_cv_mentions_use_the_same_aliases_as_the_offer(job):
    # "Microsoft 365" es alias de Excel en el pack de carrera: el CV que solo dice eso debe contar.
    profile = {**PROFILE, "certifications": [], "tools_declared_in_db": {},
               "experience": [{"role": "Auxiliar", "company": "JAS", "from": "2023-01", "to": "2024-12",
                               "bullets": ["Reportes en Microsoft 365"], "skills": []}]}
    items = {i["key"]: i for i in cv_baseline.baseline(job, profile)}
    assert items["excel"]["status"] == "cubierto"
    assert "24 meses" in items["excel"]["reason"]


def _years_item(job, experience):
    profile = {**PROFILE, "experience": experience}
    return {i["key"]: i for i in cv_baseline.baseline(job, profile)}["experiencia-previa"]


def test_years_only_fully_count_when_related_to_the_offer_skills(job):
    unrelated = [{"role": "Cajero", "company": "Tienda", "from": "2020-01", "to": "2024-12",
                  "bullets": ["Atención al cliente"], "skills": []}]
    item = _years_item(job, unrelated)
    assert item["status"] == "parcial" and item["blocker"] is False
    assert "solo ~0.0" in item["reason"]
    related = [{"role": "Analista", "company": "ACME", "from": "2020-01", "to": "2024-12",
                "bullets": ["Reportes en Excel"], "skills": []}]
    item = _years_item(job, related)
    assert item["status"] == "cubierto" and item["blocker"] is False


def test_applied_jobs_list_follows_application_status(job):
    from radar.db.queries import list_applied_jobs
    from radar.db.repository import track_application

    assert list_applied_jobs() == []
    track_application(job, "saved")
    assert list_applied_jobs() == []
    track_application(job, "applied")
    assert [row["id"] for row in list_applied_jobs()] == [job]
    track_application(job, "rejected")
    assert list_applied_jobs() == []


def test_untrack_application_removes_only_the_tracking(job):
    from radar.db.queries import list_applied_jobs
    from radar.db.repository import track_application, untrack_application

    track_application(job, "applied")
    assert untrack_application(job) is True and list_applied_jobs() == []
    assert untrack_application(job) is False
    with connection() as conn:
        assert conn.execute("SELECT count(*) FROM jobs WHERE id=%s", (job,)).fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM application_events").fetchone()[0] == 0
