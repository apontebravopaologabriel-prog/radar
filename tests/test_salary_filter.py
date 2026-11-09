from datetime import UTC, datetime

from fastapi.testclient import TestClient

from radar.api import app
from radar.db.queries import list_jobs
from radar.db.repository import ingest_jobs
from radar.domain.models import RawJob
from radar.query_context import ui_context, using_query


def test_salary_range_matches_overlapping_bands_and_excludes_unknown():
    ingest_jobs([RawJob("test", f"Analista logistica {i}", "Example", f"https://example.com/{i}",
                       description="Inventarios y compras", published_at=datetime.now(UTC)) for i in range(5)])
    from radar.db.database import connection
    with connection() as c:
        for i, low, high in [(0, 1000, 1800), (1, 2500, 3500), (2, 4000, 5000), (3, None, None), (4, 2000, None)]:
            c.execute("UPDATE jobs SET salary_min=%s,salary_max=%s WHERE title=%s", (low, high, f"Analista logistica {i}"))
    expected = {"Analista logistica 0", "Analista logistica 1", "Analista logistica 4"}
    assert {j["title"] for j in list_jobs(limit=None, min_salary=1500, max_salary=2500)} == expected
    assert len(list_jobs(limit=None)) == 5
    assert len(list_jobs(limit=None, max_salary=1500)) == 1
    assert len(list_jobs(limit=None, min_salary=4000)) == 1
    with using_query(ui_context({"filters": {"market_id": "industrial_engineering", "min_salary": "1500", "max_salary": "2500"}})):
        assert {j["title"] for j in list_jobs(limit=None)} == expected
    client = TestClient(app)
    assert {j["title"] for j in client.get('/api/jobs?min_salary=1500&max_salary=2500').json()["jobs"]} == expected
    assert client.get('/api/jobs?min_salary=3000&max_salary=1000').status_code == 422
    assert client.get('/api/jobs?max_salary=-1').status_code == 422
    assert len(client.get('/api/map/jobs?max_salary=1500').json()["features"]) <= 1
