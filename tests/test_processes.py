from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from radar.api import app
from radar.db.database import _ensure_runtime_schema, connection
from radar.db.queries import get_job, list_jobs, set_job_favorite
from radar.db.repository import ingest_jobs, track_application
from radar.domain.models import RawJob
from radar.feed import _excluded_job_ids

client = TestClient(app)


def offer():
    ingest_jobs([RawJob("test", "Analista de logistica", "Example", "https://example.com/job",
                       location="Lima", description="Inventarios y compras", published_at=datetime.now(UTC))])
    return list_jobs(limit=None)[0]["id"]


def test_external_process_has_no_fake_job_and_survives_close_reopen():
    assert client.get("/api/processes").json() == {"processes": []}
    response = client.post("/api/processes", json={"company": " Acme ", "title": "Analista"})
    assert response.status_code == 201
    item = response.json()
    assert item["company"] == "Acme" and item["job_id"] is None and item["stage"] == "contact"
    with connection() as conn:
        assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM applications").fetchone()[0] == 0
    payload = {"company": "Acme", "title": "Analista", "stage": "closed", "next_step": "Conversar", "due_date": "2026-12-04", "notes": "Contexto"}
    closed = client.put(f"/api/processes/{item['id']}", json=payload).json()
    assert closed["due_date"] == "2026-12-04" and closed["stage"] == "closed"
    assert closed["archived_at"]
    edited = client.put(f"/api/processes/{item['id']}", json={**payload, "notes": "Actualizado"}).json()
    assert edited["archived_at"] == closed["archived_at"]
    payload["stage"] = "assessment"
    reopened = client.put(f"/api/processes/{item['id']}", json=payload).json()
    assert reopened["notes"] == "Contexto" and reopened["archived_at"] is None
    assert len(client.get("/api/processes").json()["processes"]) == 1


@pytest.mark.parametrize("bad", [{"company": " "}, {"title": ""}, {"stage": "applied"}, {"due_date": "2026-02-30"}, {"url": "javascript:alert(1)"}, {"notes": "x" * 5001}])
def test_process_validation(bad):
    assert client.post("/api/processes", json={"company": "Acme", "title": "Analista", **bad}).status_code == 422


def test_linked_process_excludes_inbox_even_when_closed_and_preserves_history():
    job_id = offer()
    set_job_favorite(job_id)
    payload = {"company": "Example", "title": "Analista", "job_id": job_id}
    item = client.post("/api/processes", json=payload).json()
    assert client.post("/api/processes", json=payload).status_code == 409
    assert list_jobs(limit=None, include_applied=False) == []
    assert job_id in _excluded_job_ids()
    assert get_job(job_id)["is_favorite"]
    assert client.put(f"/api/processes/{item['id']}", json={**payload, "stage": "closed"}).status_code == 200
    assert list_jobs(limit=None, include_applied=False) == []
    assert list_jobs(limit=None, include_applied=True)[0]["id"] == job_id
    with connection() as conn:
        assert conn.execute("SELECT count(*) FROM applications").fetchone()[0] == 0
    assert client.post("/api/processes", json={**payload, "job_id": "missing"}).status_code == 404
    assert client.put(f"/api/processes/{item['id']}", json={**payload, "job_id": None}).status_code == 422


def test_migrate_only_responses_once_without_overwriting_edits():
    job_id = offer()
    application_id = track_application(job_id, "interview", "Nota original")
    with connection() as conn:
        conn.execute("PRAGMA user_version=3")
        _ensure_runtime_schema(conn)
    item = client.get("/api/processes").json()["processes"][0]
    assert item["source_application_id"] == application_id
    assert item["stage"] == "interview"
    client.put(f"/api/processes/{item['id']}", json={"company": "Updated", "title": "Puesto", "job_id": job_id, "stage": "closed"})
    with connection() as conn:
        # Simulate a pre-sync client that updated only the application.
        conn.execute("UPDATE applications SET status='offer', notes='Old client edited history' WHERE job_id=%s", (job_id,))
        conn.execute("PRAGMA user_version=3")
        _ensure_runtime_schema(conn)
    result = client.get("/api/processes").json()["processes"]
    assert len(result) == 1 and result[0]["stage"] == "closed" and result[0]["company"] == "Updated"
    assert client.get("/api/applications").json()["applications"][0]["status"] == "offer"


def test_applied_is_history_and_sort_dates_before_undated():
    job_id = offer()
    track_application(job_id, "applied")
    with connection() as conn:
        conn.execute("PRAGMA user_version=3")
        _ensure_runtime_schema(conn)
    assert client.get("/api/processes").json()["processes"] == []
    for title, due in [("Undated", None), ("Later", "2026-12-20"), ("Earlier", "2026-12-02")]:
        assert client.post("/api/processes", json={"company": "Acme", "title": title, "due_date": due}).status_code == 201
    assert [p["title"] for p in client.get("/api/processes").json()["processes"]] == ["Earlier", "Later", "Undated"]
    assert client.delete("/api/processes/not-deletable").status_code == 405


def test_archive_history_search_and_pages_do_not_expand_the_live_window():
    job_id = offer()
    track_application(job_id, "applied")
    track_application(job_id, "rejected")
    with connection() as conn:
        conn.execute("UPDATE applications SET applied_at='2025-01-01T03:00:00Z', updated_at='2025-01-02T12:00:00Z'")
        conn.execute("UPDATE application_events SET occurred_at=CASE WHEN to_status='applied' THEN '2025-01-01T03:00:00Z' ELSE '2025-01-02T12:00:00Z' END")
        conn.executemany(
            "INSERT INTO processes (company, title, stage, archived_at) VALUES ('Compañía', %s, 'closed', '2025-01-01T12:00:00Z')",
            [(f"Proceso {i}",) for i in range(21)],
        )

    tracking = client.get("/api/applications/tracking").json()
    assert tracking == {"applications": [], "activity": {"2024-12-31": 1}}
    first = client.get("/api/processes/archive", params={"q": "compania"}).json()
    second = client.get("/api/processes/archive", params={"q": "compania", "page": 2}).json()
    assert len(first["entries"]) == 20 and first["has_more"]
    assert len(second["entries"]) == 1 and not second["has_more"]
    assert second["entries"][0]["id"] not in {item["id"] for item in first["entries"]}
    [application] = client.get("/api/processes/archive", params={"q": "logística"}).json()["entries"]
    assert application["job_id"] == job_id


def test_migrate_missing_follow_up_from_legacy_mcp_status():
    job_id = offer()
    track_application(job_id, "responded")
    with connection() as conn:
        conn.execute("DELETE FROM processes WHERE job_id=%s", (job_id,))
        conn.execute("PRAGMA user_version=5")
        _ensure_runtime_schema(conn)
    [process] = client.get("/api/processes").json()["processes"]
    assert process["stage"] == "contact"
    assert process["job_id"] == job_id


def test_return_to_submissions_preserves_follow_up_and_archive_origin():
    job_id = offer()
    track_application(job_id, "applied")
    process = client.post("/api/processes", json={
        "company": "Example", "title": "Analista", "job_id": job_id,
        "stage": "interview", "notes": "Preparar entrevista",
    }).json()
    track_application(job_id, "interview")

    assert client.put(f"/api/applications/{job_id}", json={"status": "applied"}).status_code == 200
    [submitted] = client.get("/api/applications/tracking").json()["applications"]
    assert submitted["status"] == "applied"
    assert client.get("/api/processes").json()["processes"] == [process]

    track_application(job_id, "rejected")
    [archived] = client.get("/api/applications/tracking").json()["applications"]
    assert archived["archived_from_applied"]

    track_application(job_id, "interview")
    assert client.get("/api/processes").json()["processes"] == [process]
