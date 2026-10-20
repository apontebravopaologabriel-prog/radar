from datetime import UTC, datetime

import pytest

from radar.db.database import connection
from radar.db.queries import (
    get_profile,
    list_jobs,
    market_summary,
    recommendations,
    skill_overview,
)
from radar.db.repository import expire_stale_jobs, ingest_jobs, save_profile
from radar.domain.models import RawJob


@pytest.fixture(autouse=True)
def seeded_db(tmp_path, monkeypatch):
    """Isolated SQLite database seeded with one job and a matching profile."""
    monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "radar.db"))
    job = RawJob(
        source="test",
        title="Practicante de Mejora Continua",
        company="ACME",
        url="https://example.com/1",
        location="Lima",
        description="Requiere Excel, Power BI y Lean",
        published_at=datetime.now(UTC),
    )
    ingest_jobs([job])
    save_profile("Test", None, ["Mejora continua"], ["Lima"], ["hybrid"], {"Excel": "advanced"})


def test_sqlite_queries_work():
    jobs = list_jobs(limit=10)
    assert isinstance(jobs, list)
    assert len(jobs) > 0
    first = jobs[0]
    assert "id" in first
    assert "title" in first
    assert "company" in first
    assert "is_favorite" in first
    assert isinstance(first["is_favorite"], bool)


def test_sqlite_market_summary():
    summary = market_summary()
    assert summary["total_active_jobs"] > 0
    assert len(summary["by_area"]) > 0
    assert len(summary["top_skills"]) > 0


def test_sqlite_profile_and_recommendations():
    prof = get_profile()
    assert prof is not None
    assert isinstance(prof["target_roles"], list)
    assert isinstance(prof["locations"], list)
    assert isinstance(prof["work_modes"], list)

    recs = recommendations(limit=5)
    assert recs["profile_configured"] is True
    assert len(recs["jobs"]) > 0
    job = recs["jobs"][0]
    assert isinstance(job["strong_matches"], list)
    assert isinstance(job["missing_skills"], list)

    # Si se marca como postulado, ya no sale en recomendaciones por defecto
    from radar.db.repository import track_application
    track_application(job["id"], "applied")
    recs_after = recommendations(limit=5)
    assert not any(j["id"] == job["id"] for j in recs_after["jobs"])
    # Con include_applied=True sí aparece
    recs_with_applied = recommendations(limit=5, include_applied=True)
    assert any(j["id"] == job["id"] for j in recs_with_applied["jobs"])


def test_sqlite_skill_overview():
    overview = skill_overview(max_age_days=60)
    assert overview["total_jobs"] > 0
    assert len(overview["skills"]) > 0


def test_expire_stale_jobs_deactivates_only_unseen_jobs():
    with connection() as conn:
        conn.execute(
            "UPDATE job_sources SET last_seen_at = datetime('now', '-90 days')"
        )
        conn.commit()

    deactivated = expire_stale_jobs(stale_after_days=45)
    assert deactivated == 1

    jobs = list_jobs(limit=10, max_age_days=365)
    assert len(jobs) == 0

    with connection() as conn:
        still_active = conn.execute("SELECT count(*) FROM jobs WHERE is_active=1").fetchone()[0]
    assert still_active == 0


def test_repair_data_only_rewrites_what_changed_and_is_idempotent():
    from radar.db.database import connection
    from radar.db.repository import ingest_jobs, repair_data_quality
    from radar.domain.models import RawJob

    ingest_jobs([
        RawJob("t", "Practicante de Logística", "ACME", "https://e.com/1", location="Lima",
               description="Gestión de inventarios con Excel y SQL. Modalidad híbrida. Sueldo S/ 1500 mensual."),
        RawJob("t", "Analista de Calidad", "ACME", "https://e.com/2", location="Lima", description="Lean Six Sigma y Power BI"),
    ])
    total = repair_data_quality()["jobs_checked"]  # la base de la prueba ya trae una oferta sembrada
    second = repair_data_quality()
    assert second["jobs_unchanged"] == total and second["classifications_rebuilt"] == 0
    with connection() as conn:  # dañar los datos derivados de una oferta: el siguiente repair los reconstruye
        job_id = conn.execute("SELECT id FROM jobs WHERE title = 'Practicante de Logística'").fetchone()[0]
        conn.execute("DELETE FROM job_skills WHERE job_id=%s", (job_id,))
        conn.execute("UPDATE jobs SET work_mode='unknown', sector=NULL WHERE id=%s", (job_id,))
    third = repair_data_quality()
    assert third["classifications_rebuilt"] == 1 and third["jobs_unchanged"] == total - 1
    with connection() as conn:
        assert conn.execute("SELECT count(*) FROM job_skills WHERE job_id=%s", (job_id,)).fetchone()[0] >= 1
        assert conn.execute("SELECT work_mode FROM jobs WHERE id=%s", (job_id,)).fetchone()[0] == "hybrid"
