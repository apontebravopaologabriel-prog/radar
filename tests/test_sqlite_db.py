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


def test_old_hidden_reason_check_is_rebuilt_on_open():
    """Archivar ya no pide motivo: una base antigua reconstruye `job_user_status` al abrirse."""
    from radar.db import database as db
    from radar.db.queries import set_job_user_status

    with connection() as conn:
        conn.executescript(
            """
            ALTER TABLE job_user_status RENAME TO job_user_status_legacy;
            CREATE TABLE job_user_status (
                job_id TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
                status TEXT NOT NULL DEFAULT 'hidden' CHECK (status IN ('visible', 'hidden')),
                reason TEXT CHECK (reason IN ('closed', 'not_interested', 'applied', 'duplicate', 'other')),
                note TEXT,
                created_at TEXT NOT NULL DEFAULT (now()),
                updated_at TEXT NOT NULL DEFAULT (now()),
                CHECK (status = 'visible' OR reason IS NOT NULL)
            );
            INSERT INTO job_user_status SELECT * FROM job_user_status_legacy;
            DROP TABLE job_user_status_legacy;
            """
        )
    db._SCHEMA_READY.clear()
    with connection() as conn:
        table_sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='job_user_status'").fetchone()[0]
        job_id = conn.execute("SELECT id FROM jobs LIMIT 1").fetchone()[0]
    assert "reason IS NOT NULL" not in table_sql
    set_job_user_status(job_id, "hidden")
    from radar.db.queries import list_hidden_jobs

    assert [row["id"] for row in list_hidden_jobs()] == [job_id]


def test_deduplicate_jobs_merges_cross_portal_and_keeps_generic_companies_separate():
    from datetime import UTC, datetime, timedelta

    from radar.db.database import connection
    from radar.db.repository import deduplicate_jobs, ingest_jobs
    from radar.domain.models import RawJob

    now = datetime.now(UTC)
    desc = "Gestionar inventarios, planeamiento de demanda, SQL y Power BI para operaciones logisticas."
    ingest_jobs([
        RawJob("linkedin", "Analista de Supply Chain", "ACME Perú S.A.C.", "https://e.com/a", location="San Isidro, Lima", description=desc, published_at=now),
        RawJob("computrabajo", "Analista de Supply Chain", "ACME Perú", "https://e.com/b", location="Lima, Lima", description=desc, published_at=now - timedelta(days=2)),
        RawJob("bumeran", "Analista de Supply Chain", "ACME Perú S.A.C.", "https://e.com/c", location="Lima", description=desc, published_at=now - timedelta(days=60)),
        RawJob("bumeran", "Asistente Logístico", "Importante empresa del sector", "https://e.com/d", location="Ate, Lima", description="Apoyo en almacén de Ate y despachos.", published_at=now),
        RawJob("computrabajo", "Asistente Logístico", "Importante empresa del sector", "https://e.com/e", location="Callao", description="Apoyo en almacén de Callao y recepción.", published_at=now),
    ])
    with connection() as conn:
        # Force all to canonical first to verify deduplicate_jobs backfill behavior as well
        conn.execute("UPDATE jobs SET duplicate_status='canonical', duplicate_group_id=NULL")
        conn.commit()

    res = deduplicate_jobs(window_days=30)
    assert res["merged"] == 1
    with connection() as conn:
        statuses = dict(conn.execute("SELECT title, count(*) FROM jobs WHERE duplicate_status='canonical' GROUP BY title").fetchall())
        merged = conn.execute("SELECT title, duplicate_group_id FROM jobs WHERE duplicate_status='merged'").fetchall()
    assert statuses["Analista de Supply Chain"] == 2  # recent merged into 1, 60-day old stays canonical
    assert statuses["Asistente Logístico"] == 2  # generic company not merged
    assert len(merged) == 1 and merged[0][1] is not None


def test_ingest_jobs_marks_recent_cross_portal_duplicate_as_merged():
    from datetime import UTC, datetime

    from radar.db.database import connection
    from radar.db.repository import ingest_jobs
    from radar.domain.models import RawJob

    now = datetime.now(UTC)
    desc = "Desarrollar APIs REST en Python con FastAPI, PostgreSQL y Docker."
    ingest_jobs([RawJob("linkedin", "Backend Developer", "TechCorp", "https://e.com/10", location="Miraflores, Lima", description=desc, published_at=now)])
    ingest_jobs([RawJob("indeed", "Backend Developer", "TechCorp", "https://e.com/11", location="Lima, PE", description=desc, published_at=now)])
    with connection() as conn:
        rows = conn.execute("SELECT duplicate_status, duplicate_group_id FROM jobs WHERE title='Backend Developer' ORDER BY created_at").fetchall()
    assert rows[0][0] == "canonical"
    assert rows[1][0] == "merged" and rows[1][1] is not None


def test_compact_database_prunes_observations_and_orphaned_markets_without_deleting_jobs():
    from radar.db.database import connection
    from radar.db.repository import compact_database, ingest_jobs
    from radar.domain.models import RawJob

    ingest_jobs([RawJob("t", "Ingeniero de Procesos", "Beta SAC", "https://e.com/20", location="Lima", description="Mejora continua Lean Six Sigma.")])
    ingest_jobs([RawJob("t", "Ingeniero de Procesos", "Beta SAC", "https://e.com/20", location="Lima", description="Mejora continua Lean Six Sigma.")])
    with connection() as conn:
        job_id = conn.execute("SELECT id FROM jobs WHERE title='Ingeniero de Procesos'").fetchone()[0]
        conn.execute(
            "INSERT INTO job_market_classifications(job_id, market_id, rules_hash, content_hash, relevance_tier, relevance_score, relevance_evidence, areas, skills) VALUES (%s, 'deleted_market', 'h', 'c', 'core', 0.9, 'ev', '[]', '[]')",
            (job_id,),
        )
        conn.execute("UPDATE job_sources SET raw_payload='{\"big\":true}', last_seen_at=datetime('now', '-45 days') WHERE job_id=%s", (job_id,))
        conn.commit()
        jobs_before = conn.execute("SELECT count(*) FROM jobs").fetchone()[0]

    res = compact_database(raw_payload_days=30)
    assert res["orphaned_classifications_deleted"] >= 1
    assert res["observations_pruned"] >= 1
    assert res["raw_payloads_cleared"] >= 1
    with connection() as conn:
        assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == jobs_before
        assert conn.execute("SELECT count(*) FROM job_market_classifications WHERE market_id='deleted_market'").fetchone()[0] == 0
        assert conn.execute("SELECT raw_payload FROM job_sources WHERE job_id=%s", (job_id,)).fetchone()[0] == "{}"
