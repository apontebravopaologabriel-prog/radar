from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from radar import tools
from radar.agent import loop
from radar.db.database import connection
from radar.db.queries import get_job, list_jobs, set_job_favorite
from radar.db.repository import ingest_jobs
from radar.domain.models import RawJob
from radar.query_context import CURRENT_QUERY, ui_context, using_query


@pytest.fixture
def offers():
    raw = RawJob("test", "Desarrollador Java", "Example", "https://example.com/java",
                 location="Lima", description="Desarrollar software Java", published_at=datetime.now(UTC))
    ingest_jobs([raw, replace(raw, title="Analista de logistica", url="https://example.com/log",
                             description="Inventarios y compras"),
                 replace(raw, title="Analista de Power BI", url="https://example.com/bi", description="Power BI"),
                 replace(raw, title="Desarrollador Python", url="https://example.com/closed", description="Python",
                         application_status="closed"),
                 replace(raw, title="Desarrollador PHP", url="https://example.com/expired", description="PHP",
                         application_status="expired"),
                 replace(raw, title="Desarrollador antiguo", url="https://example.com/old",
                         published_at=datetime.now(UTC)-timedelta(days=25))])
    return {j["title"]: j["id"] for j in list_jobs(limit=None)}


def scope(market):
    return ui_context({"filters": {"market_id": market, "max_age_days": "7", "relevance_tier": "market"}})


def test_closed_offers_are_not_opportunities_but_remain_saved(offers):
    with connection() as c:
        id = c.execute("SELECT id FROM jobs WHERE title='Desarrollador Python'").fetchone()[0]
    set_job_favorite(id)
    assert get_job(id)["application_status"] == "closed"
    assert get_job(id)["is_favorite"]
    assert "Desarrollador Python" not in offers and "Desarrollador PHP" not in offers
    assert "Desarrollador Java" in offers  # unknown is still eligible


def test_worker_queries_inherit_market_and_period_without_leaking(offers):
    def run(market):
        return loop._call_tool_safely(tools.REGISTRY["search_saved_jobs"], {}, scope(market))
    with ThreadPoolExecutor(max_workers=2) as pool:
        industrial, systems = list(pool.map(run, ["industrial_engineering", "sistemas_software"]))
    assert "Analista de logistica" in {j["title"] for j in industrial["jobs"]}
    assert "Desarrollador Java" not in {j["title"] for j in industrial["jobs"]}
    assert "Desarrollador Java" in {j["title"] for j in systems["jobs"]}
    assert "Analista de logistica" not in {j["title"] for j in systems["jobs"]}
    assert "Desarrollador antiguo" not in {j["title"] for j in systems["jobs"]}
    assert systems["query_context"]["max_age_days"] == 7
    assert CURRENT_QUERY.get() is None


def test_explicit_market_override_and_counts_use_projected_data(offers):
    with using_query(scope("industrial_engineering")):
        jobs = tools.search_saved_jobs(market_id="sistemas_software")["jobs"]
        data = tools.get_market_breakdown("area", market_id="sistemas_software")
        skills = tools.get_skill_demand(market_id="sistemas_software")
        detail = tools.get_job_details(offers["Analista de Power BI"], market_id="sistemas_software")
    assert len(jobs) == data["total"] == skills["total_jobs"] == 2
    assert data["max_age_days"] == 7
    assert detail["area"] == "Data / BI"
    assert "Power BI" in {s["name"] for s in detail["skills"]}


def test_invalid_market_is_rejected_and_sql_is_not_claimed_as_scoped():
    with pytest.raises(ValueError):
        tools.search_saved_jobs(market_id="unknown")
    with using_query(scope("sistemas_software")):
        assert tools.run_readonly_sql("SELECT 1")["query_scope"] == "unscoped_sql"


def test_default_mcp_context_is_explicit_reference_career(offers):
    result = tools.REGISTRY["search_saved_jobs"].call({})
    assert result["query_context"]["market_id"] == "industrial_engineering"
    assert "market_id" in tools.REGISTRY["search_saved_jobs"].json_schema()["properties"]


def test_district_scope_is_frozen_and_filters_before_limit():
    raw = RawJob("test", "Desarrollador Java", "Example", "https://example.com/ate", location="Ate",
                 description="Java", published_at=datetime.now(UTC))
    ingest_jobs([raw, replace(raw, title="Desarrollador Python", location="Miraflores", url="https://example.com/m", description="Python")])
    state = {"district": "Ate", "filters": {"market_id": "sistemas_software", "max_age_days": 7}}
    frozen = ui_context(state)
    state["district"] = "Miraflores"
    with using_query(frozen):
        result = tools.search_saved_jobs(limit=1)
        assert [j["location"] for j in result["jobs"]] == ["Ate"]
        assert tools.get_market_breakdown("area")["total"] == 1
        assert tools.get_skill_demand()["total_jobs"] == 1


def test_cross_market_fit_and_learning_do_not_claim_a_new_score(offers):
    from radar.db.repository import save_profile

    save_profile("Test", None, ["Operaciones"], ["Lima"], [], {"Java": "advanced"})
    with using_query(scope("sistemas_software")):
        jobs = tools.list_recommended_jobs()
        assert jobs["score_scope"] == "not_computed_for_selected_market"
        assert all(j["score"] is None for j in jobs["jobs"])
        assert tools.plan_learning()["available"] is False


def test_seven_calendar_days_and_lima_midnight():
    from radar.freshness import visible_date_bounds

    assert visible_date_bounds(7, datetime(2026, 11, 2, 2, tzinfo=UTC)) == ("2026-10-26", "2026-11-02")
    assert visible_date_bounds(1, datetime(2026, 11, 2, 6, tzinfo=UTC)) == ("2026-11-02", "2026-11-03")


def test_publication_days_match_across_market_views(monkeypatch):
    from radar.api import map_jobs
    from radar.db.queries import recommendations, skill_overview
    from radar.db.repository import save_profile
    from radar.freshness import visible_date_bounds

    now = datetime(2026, 11, 7, 2, tzinfo=UTC)  # November 6, 21:00 in Lima.
    monkeypatch.setattr("radar.db.queries.visible_date_bounds", lambda days: visible_date_bounds(days, now))
    publications = {
        "Evening": "2026-11-07 00:38:00+00:00",
        "End of day": "2026-11-07T04:59:59.999999Z",
        "Next day": "2026-11-07 05:00:00+00:00",
        "First day": "2026-10-31 00:00:00-05:00",
        "Too old": "2026-10-31 04:59:59+00:00",
        "Date only": "2026-10-31",
        "No zone": "2026-10-31 00:00:00",
        "Undated": None,
    }
    urls = {company: f"https://example.com/bi/{i}" for i, company in enumerate(publications)}
    ingest_jobs([
        RawJob("test", "Analista BI", company, url, location="Miraflores, Lima",
               description="Power BI", published_at=now)
        for company, url in urls.items()
    ])
    with connection() as conn:
        conn.executemany(
            "UPDATE jobs SET published_at=? WHERE id=(SELECT job_id FROM job_sources WHERE source_url=?)",
            [(published_at, urls[company]) for company, published_at in publications.items()],
        )
        conn.commit()
    save_profile("Ana", None, [], ["Lima"], [], {})

    expected = {"Evening", "End of day", "First day", "Date only", "No zone"}
    assert {job["company"] for job in list_jobs(limit=None, max_age_days=7)} == expected
    assert {feature["properties"]["company"] for feature in map_jobs(max_age_days=7)["features"]} == expected
    assert skill_overview(max_age_days=7)["total_jobs"] == len(expected)
    assert {job["company"] for job in recommendations(max_age_days=7)["jobs"]} == expected


def test_radar_scope_counts_match_list_and_skills_across_districts():
    raw = RawJob("test", "Desarrollador Java", "Example", "https://example.com/mira", location="Miraflores",
                 description="Java", published_at=datetime.now(UTC))
    ingest_jobs([raw, replace(raw, title="Desarrollador Python", location="Ate", url="https://example.com/a", description="Python")])
    context = ui_context({"mode": "radar", "district": "Miraflores",
                          "radar": {"center": "Miraflores", "radiusKm": 2},
                          "filters": {"market_id": "sistemas_software", "max_age_days": 7}})
    with using_query(context):
        assert len(tools.search_saved_jobs()["jobs"]) == 1
        assert tools.get_market_breakdown("area")["total"] == 1
        assert tools.get_skill_demand()["total_jobs"] == 1


def test_audit_targets_selected_projection_and_keeps_all_saved_scope(offers):
    with using_query(scope("sistemas_software")):
        data = tools.audit_classification()
    assert data["market_id"] == "sistemas_software"
    assert data["scope"] == "all_saved_offers" and data["drifted"] == 0


def test_applied_exclusion_matches_agent_list_counts_and_skills(offers):
    from radar.db.repository import track_application

    track_application(offers["Desarrollador Java"], "applied")
    with using_query(scope("sistemas_software")):
        assert len(tools.search_saved_jobs()["jobs"]) == 1
        assert tools.get_market_breakdown("area")["total"] == 1
        assert tools.get_skill_demand()["total_jobs"] == 1
        assert len(tools.search_saved_jobs(include_applied=True)["jobs"]) == 2
