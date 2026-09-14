from radar.db.database import connection
from radar.db.queries import (
    get_profile,
    list_jobs,
    market_summary,
    recommendations,
    skill_overview,
)
from radar.db.repository import capture_market_snapshot


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


def test_sqlite_skill_overview():
    overview = skill_overview(max_age_days=60)
    assert overview["total_jobs"] > 0
    assert len(overview["skills"]) > 0
