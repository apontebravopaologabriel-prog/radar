import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from radar.db.database import connection
from radar.db.queries import list_jobs
from radar.db.repository import ingest_jobs
from radar.domain.models import RawJob
from radar.markets import backfill_market, save_search_profile, search_profile


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "radar.db"))
    monkeypatch.delenv("RADAR_ACCESS_TOKEN", raising=False)


def test_shared_offer_has_independent_classifications_and_identity():
    raw = RawJob("test", "Analista de Power BI", "Example", "https://example.com/bi",
                 description="Power BI y SQL, dashboards", published_at=datetime.now(UTC))
    ingest_jobs([raw])
    industrial = list_jobs(market_id="industrial_engineering")
    systems = list_jobs(market_id="sistemas_software")
    assert industrial[0]["id"] == systems[0]["id"]
    assert industrial[0]["primary_area"] != systems[0]["primary_area"]
    with connection() as conn:
        assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1
        from radar.careers import list_packs

        assert conn.execute("SELECT count(*) FROM job_market_classifications").fetchone()[0] == len(list_packs())


def test_reingestion_replaces_skills_in_both_projections():
    raw = RawJob("test", "Analista de Datos", "Example", "https://example.com/data", description="Excel")
    ingest_jobs([raw])
    ingest_jobs([replace(raw, description="Python y SQL")])
    with connection() as conn:
        rows = conn.execute("SELECT skills FROM job_market_classifications WHERE market_id IN ('industrial_engineering','sistemas_software')").fetchall()
    for row in rows:
        names = {item["name"] for item in json.loads(row[0])}
        assert "SQL" in names and "Excel" not in names


def test_backfill_is_idempotent_and_does_not_rewrite_canonical_classification():
    ingest_jobs([RawJob("test", "Desarrollador Java", "Example", "https://example.com/java", description="Java")])
    with connection() as conn:
        before = conn.execute("SELECT relevance_tier,relevance_evidence FROM jobs").fetchall()
        conn.execute("DELETE FROM job_market_classifications WHERE market_id='sistemas_software'")
    assert backfill_market("sistemas_software") == 1
    assert backfill_market("sistemas_software") == 0
    with connection() as conn:
        assert conn.execute("SELECT relevance_tier,relevance_evidence FROM jobs").fetchall() == before


def test_market_filters_use_projected_skills():
    ingest_jobs([RawJob("test", "Desarrollador Java", "Example", "https://example.com/java",
                       description="Java Spring Boot", published_at=datetime.now(UTC))])
    assert list_jobs(market_id="sistemas_software", skill="Java", relevance_tier="core")
    assert not list_jobs(market_id="sistemas_software", skill="Excel")


def test_search_profiles_are_independent_and_cannot_override_identity():
    save_search_profile("industrial_engineering", {"roles": ["Analista BI"]})
    save_search_profile("sistemas_software", {"roles": ["Backend"], "seniority": ["junior"]})
    save_search_profile("sistemas_software", {"roles": ["QA"]})
    assert search_profile("industrial_engineering")["preferences"] == {"roles": ["Analista BI"]}
    assert search_profile("sistemas_software")["version"] == 2
    with pytest.raises(ValueError):
        save_search_profile("sistemas_software", {"education": ["Invented degree"]})


def test_existing_database_gets_backup_before_market_migration(tmp_path):
    from radar.db.database import _SCHEMA_READY, database_path

    ingest_jobs([RawJob("test", "Analista BI", "Example", "https://example.com/bi")])
    with connection() as conn:
        conn.execute("DROP TABLE job_market_classifications")
        conn.execute("DROP TABLE market_search_profiles")
    _SCHEMA_READY.discard(str(database_path()))
    with connection() as conn:
        assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM job_market_classifications").fetchone()[0] == 0
    assert len(list((tmp_path / "backups").glob("pre-dual-market-*.db"))) == 1


def test_saved_search_filters_and_skill_counts_share_the_same_market_scope():
    from radar.markets import market_skills

    raw = RawJob("test", "Desarrollador Java Junior", "Example", "https://example.com/java",
                 location="Lima", description="Java y SQL", published_at=datetime.now(UTC))
    ingest_jobs([raw, replace(raw, title="Desarrollador Python Junior", url="https://example.com/python",
                             description="Python", location="Arequipa")])
    save_search_profile("sistemas_software", {"roles": ["desarrollador"], "locations": ["Lima"],
                                             "seniority": ["junior"], "excluded_titles": ["Python"]})
    filters = {"market_id": "sistemas_software", "profile_mode": "saved", "relevance_tier": "core"}
    assert [job["title"] for job in list_jobs(**filters)] == [raw.title]
    overview = market_skills(**filters)
    assert overview["total_jobs"] == 1
    assert {skill["name"] for skill in overview["skills"]} == {"Java", "SQL"}
    assert all(skill["share"] == 1 for skill in overview["skills"])
    assert not list_jobs(market_id="industrial_engineering", profile_mode="saved")


def test_market_http_endpoints_validate_context_and_apply_saved_preferences():
    from fastapi.testclient import TestClient

    from radar.api import app

    with TestClient(app) as client:
        assert client.get("/api/markets").status_code == 200
        preferences = {"roles": ["Java"], "work_modes": ["remote"]}
        assert client.put("/api/markets/sistemas_software/profile", json=preferences).status_code == 200
        assert client.get("/api/markets/sistemas_software/profile").json()["preferences"] == preferences
        assert client.get("/api/markets/industrial_engineering/profile").json()["preferences"] == {}
        assert client.put("/api/markets/sistemas_software/profile", json={"work_modes": ["invalid"]}).status_code == 422
        assert client.get("/api/jobs?profile_mode=saved").status_code == 422
        assert client.get("/api/skills/overview?profile_mode=saved").status_code == 422
        assert client.get("/api/jobs?market_id=unknown").status_code == 422
        assert client.get("/api/jobs?market_id=sistemas_software&profile_mode=saved").json()["jobs"] == []


def test_backfill_does_not_hold_a_transaction_during_classification_or_overwrite_a_capture(monkeypatch):
    import threading

    from radar import markets

    raw = RawJob("test", "Analista de Datos", "Example", "https://example.com/data", description="Java")
    ingest_jobs([raw])
    with connection() as conn:
        conn.execute("DELETE FROM job_market_classifications WHERE market_id='sistemas_software'")
    computing = threading.Event()
    release = threading.Event()
    original = markets._projection_values
    result = []
    errors = []

    def prepare(*args, **kwargs):
        if threading.current_thread().name == "test-backfill":
            computing.set()
            assert release.wait(10)
        return original(*args, **kwargs)

    def rebuild():
        try:
            result.append(backfill_market("sistemas_software"))
        except Exception as exc:  # noqa: BLE001 - forward worker failures to the test thread
            errors.append(exc)

    monkeypatch.setattr(markets, "_projection_values", prepare)
    worker = threading.Thread(target=rebuild, name="test-backfill")
    worker.start()
    try:
        assert computing.wait(10)
        ingest_jobs([replace(raw, description="Python")])
    finally:
        release.set()
        worker.join(10)
    assert not worker.is_alive() and not errors
    assert result == [0]
    with connection() as conn:
        skills = conn.execute("SELECT skills FROM job_market_classifications WHERE market_id='sistemas_software'").fetchone()[0]
    assert {item["name"] for item in json.loads(skills)} == {"Python"}


def test_parallel_first_connections_initialize_one_committed_catalog():
    import threading
    from concurrent.futures import ThreadPoolExecutor

    ready = threading.Barrier(8)

    def first_read(_):
        ready.wait(10)
        with connection() as conn:
            return conn.execute("SELECT count(*) FROM industrial_areas").fetchone()[0]

    with ThreadPoolExecutor(max_workers=8) as workers:
        counts = list(workers.map(first_read, range(8)))
    assert counts[0] > 0 and len(set(counts)) == 1


def test_current_market_does_not_wait_for_an_unrelated_rebuild():
    from concurrent.futures import ThreadPoolExecutor

    from radar.db.database import database_path
    from radar.markets import _backfill_lock

    ingest_jobs([RawJob("test", "Analista BI", "Example", "https://example.com/bi")])
    with ThreadPoolExecutor(max_workers=1) as workers, _backfill_lock(str(database_path().resolve())):
        assert workers.submit(backfill_market, "industrial_engineering").result(timeout=3) == 0
