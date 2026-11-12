import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from radar.api import app
from radar.db.database import connection
from radar.db.queries import list_jobs, set_job_user_status
from radar.db.repository import ingest_jobs, track_application
from radar.domain.models import RawJob
from radar.freshness import visible_date_bounds

client = TestClient(app)
BASE = {"market_id": "sistemas_software", "geo_scope": "lima_callao", "max_age_days": 7, "relevance_tier": "market"}


@pytest.fixture
def offers(monkeypatch):
    monkeypatch.delenv("RADAR_ACCESS_TOKEN", raising=False)
    ingest_jobs([RawJob("indeed", f"Analista de datos Python {i}", f"Empresa {i}", f"https://indeed.com/{i}",
                       location=location, description="Desarrollo de software. Python SQL. Híbrido.",
                       published_at=datetime.now(UTC))
                 for i, location in enumerate(["San Isidro, Lima", "Miraflores, Lima", "Ate, Lima", "Arequipa", "San Isidro, Lima", "San Isidro, Lima", "San Isidro, Lima"])])
    rows = list_jobs(limit=None, market_id="sistemas_software", max_age_days=7)
    indexed = {int(row["title"].rsplit(" ", 1)[-1]): row["id"] for row in rows}
    set_job_user_status(indexed[4], "hidden", "not_interested")
    track_application(indexed[5], "applied")
    response = client.post("/api/processes", json={"company": "Empresa 6", "title": "Analista", "job_id": indexed[6], "stage": "closed"})
    assert response.status_code == 201
    return indexed


def overview(params=None):
    response = client.get("/api/analytics/overview", params={**BASE, **(params or {})})
    assert response.status_code == 200, response.text
    return response.json()


def test_overview_matches_map_and_every_breakdown_drills_into_exact_offers(offers):
    result = overview()
    mapped = client.get("/api/jobs", params={**BASE, "include_applied": "false", "slim": 1}).json()
    assert result["total"] == mapped["total"] == 3
    assert result["employers"] == 3
    dimensions = {"areas": "area", "skills": "skill", "companies": "company", "districts": "district", "sources": "source", "seniorities": "seniority", "work_modes": "work_mode", "publications": "publication"}
    for field, dimension in dimensions.items():
        for bucket in result[field]:
            detail = client.get("/api/analytics/offers", params={**BASE, "dimension": dimension, "value": bucket["value"], "limit": 1}).json()
            assert detail["total"] == bucket["count"], (field, bucket, detail)
            assert len(detail["jobs"]) == min(1, bucket["count"])
            if detail["jobs"]:
                assert "has_description" in detail["jobs"][0]
                assert "description" not in detail["jobs"][0]
    all_ids = {job["id"] for offset in range(3) for job in client.get("/api/analytics/offers", params={**BASE, "limit": 1, "offset": offset}).json()["jobs"]}
    assert all_ids == {offers[0], offers[1], offers[2]}


def test_scope_filters_and_projected_skills_match_selected_market(offers):
    with connection() as conn:
        conn.execute("UPDATE job_market_classifications SET skills=%s WHERE job_id=%s AND market_id=%s", (json.dumps([{"name": "Selected market only"}]), offers[0], "sistemas_software"))
    for filters in ({"search": "Empresa 1"}, {"area": overview()["areas"][0]["value"]}, {"source": "indeed"}, {"skill": "Selected market only"}, {"seniority": "junior"}, {"work_mode": "hybrid"}, {"min_salary": 1500, "max_salary": 2500}):
        expected = client.get("/api/jobs", params={**BASE, **filters, "include_applied": "false"}).json()["total"]
        assert overview(filters)["total"] == expected
    assert overview({"skill": "Selected market only"})["total"] == 1
    assert "Selected market only" in {s["value"] for s in overview()["skills"]}
    assert "Selected market only" not in {s["value"] for s in overview({"market_id": "industrial_engineering"})["skills"]}


def test_district_radius_and_unselected_radar(offers):
    assert overview({"district": "san isidro"})["total"] == 1
    assert overview({"district": "not-a-district"})["total"] == 0
    assert overview({"empty": "true"})["total"] == 0
    map_rows = client.get("/api/jobs", params={**BASE, "include_applied": "false"}).json()["jobs"]
    center = next(j for j in map_rows if j["id"] == offers[0])
    params = {"latitude": center["latitude"], "longitude": center["longitude"], "radius_km": 2}
    assert overview(params)["total"] == 1
    assert client.get("/api/analytics/offers", params={**BASE, **params}).json()["jobs"][0]["id"] == offers[0]


def test_salary_groups_separate_currency_and_period_and_drill_down(offers):
    with connection() as conn:
        for i, low, high, currency, period in [(0, 1500, 2500, "PEN", "month"), (1, 2000, None, "USD", "month"), (2, None, 24000, "PEN", "year")]:
            conn.execute("UPDATE jobs SET salary_min=%s,salary_max=%s,salary_currency=%s,salary_period=%s WHERE id=%s", (low, high, currency, period, offers[i]))
    result = overview()
    assert result["salary_count"] == 3 and result["salary_share"] == 1
    assert {(g["currency"], g["period"], g["median"]) for g in result["salaries"]} == {("PEN", "month", 2000), ("USD", "month", 2000), ("PEN", "year", 24000)}
    for group in result["salaries"]:
        assert sum(b["count"] for b in group["bins"]) == group["count"]
        for bucket in group["bins"]:
            value = json.dumps([group["currency"], group["period"], bucket["value"]], ensure_ascii=False, separators=(",", ":"))
            detail = client.get("/api/analytics/offers", params={**BASE, "dimension": "salary", "value": value}).json()
            assert detail["total"] == bucket["count"]
    with connection() as conn:
        conn.execute("UPDATE jobs SET salary_period=NULL WHERE id=%s", (offers[0],))
    assert any(g["period"] == "unknown" for g in overview()["salaries"])


def test_local_calendar_and_zero_days_are_not_capture_growth(offers):
    start, end = visible_date_bounds(7)
    last = (datetime.fromisoformat(end) - timedelta(days=1)).date().isoformat()
    with connection() as conn:
        conn.execute("UPDATE jobs SET published_at=%s WHERE id=%s", (f"{start}T04:30:00+00:00", offers[0]))  # Previous day in Lima: excluded.
        conn.execute("UPDATE jobs SET published_at=%s WHERE id=%s", (f"{start}T05:30:00+00:00", offers[1]))
        conn.execute("UPDATE jobs SET published_at=%s WHERE id=%s", (f"{last}T23:59:59.999999-05:00", offers[2]))
    result = overview()
    assert result["total"] == 2
    assert len(result["publications"]) == 7
    assert result["publications"][0] == {"value": start, "count": 1}
    assert result["publications"][-1] == {"value": last, "count": 1}
    assert sum(b["count"] for b in result["publications"]) == 2
    assert any(b["count"] == 0 for b in result["publications"])


@pytest.mark.parametrize("bad", [{"radius_km": 5}, {"latitude": 91}, {"min_salary": 3000, "max_salary": 1000}, {"max_age_days": 0}, {"market_id": "missing"}, {"geo_scope": "other"}])
def test_invalid_scopes_are_rejected(bad):
    assert client.get("/api/analytics/overview", params={**BASE, **bad}).status_code == 422


def test_salary_period_aliases_share_one_group_without_assuming_missing_units(offers):
    with connection() as conn:
        for i, period in [(0, "mensual"), (1, "month"), (2, "mensuales")]:
            conn.execute("UPDATE jobs SET salary_min=2000,salary_max=NULL,salary_currency='PEN',salary_period=%s WHERE id=%s", (period, offers[i]))
    result = overview()
    assert len(result["salaries"]) == 1
    assert result["salaries"][0]["period"] == "month"
    assert result["salaries"][0]["count"] == 3


def test_company_metrics_skip_generic_labels_without_losing_offers(offers):
    with connection() as conn:
        conn.execute("UPDATE companies SET name='Importante empresa del sector industrial' WHERE name='Empresa 0'")
        conn.execute("UPDATE companies SET name='CONFIDENCIAL.' WHERE name='Empresa 1'")
    result = overview()
    assert result["total"] == 3
    assert result["employers"] == 1
    assert result["companies"] == [{"value": "Empresa 2", "count": 1}]
    response = client.get("/api/analytics/offers", params=BASE)
    assert response.json()["total"] == 3


def test_skill_groups_preserve_names_for_drilldown(offers):
    skills = [
        {"name": "Excel", "skill_type": "technical"},
        {"name": "Lean", "skill_type": "methodology"},
        {"name": "Comunicación"},
        {"name": "English"},
        {"name": "Python"},
        {"name": "ETL", "skill_type": "technical"},
        {"name": "Histórica"},
    ]
    with connection() as conn:
        conn.execute("UPDATE job_market_classifications SET skills=%s WHERE job_id=%s AND market_id=%s",
                     (json.dumps(skills), offers[0], BASE["market_id"]))
    result = overview({"search": "Empresa 0"})
    assert {group: [item["value"] for item in rows] for group, rows in result["skill_groups"].items()} == {
        "technical": ["Excel", "Python"], "knowledge": ["ETL", "Lean"], "soft": ["Comunicación"], "language": ["English"], "other": ["Histórica"],
    }
    response = client.get("/api/analytics/offers", params={**BASE, "dimension": "skill", "value": "English"})
    assert response.json()["total"] == 1
