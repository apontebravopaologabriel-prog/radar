import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from radar import pipeline
from radar.db.database import connection
from radar.db.queries import set_job_favorite
from radar.db.repository import ingest_jobs, track_application
from radar.domain.models import RawJob


def job(**values):
    return replace(RawJob("portal", "Analista de datos", "Example", "https://example.com/1",
                          external_id="one", location="Lima", description="Python y SQL",
                          published_at=datetime.now(UTC)), **values)


def test_same_portal_offer_keeps_id_sources_and_personal_state_when_title_changes():
    ingest_jobs([job()])
    with connection() as c:
        id = c.execute("SELECT id FROM jobs").fetchone()[0]
    set_job_favorite(id)
    track_application(id, "applied", "keep note")
    ingest_jobs([job(title="Analista de Data Senior", location="Miraflores")])
    with connection() as c:
        assert c.execute("SELECT id,title,location FROM jobs").fetchall() == [(id, "Analista de Data Senior", "Miraflores")]
        assert c.execute("SELECT job_id FROM job_sources").fetchall() == [(id,)]
        assert c.execute("SELECT job_id,note FROM job_user_favorites").fetchall() == [(id, None)]
        assert c.execute("SELECT job_id,status,notes FROM applications").fetchall() == [(id, "applied", "keep note")]


def test_source_external_id_survives_url_changes_but_new_id_is_a_new_publication():
    ingest_jobs([job(), job(url="https://example.com/new-url")])
    with connection() as c:
        assert c.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1
        assert c.execute("SELECT count(*) FROM job_sources").fetchone()[0] == 2
    ingest_jobs([job(external_id="two", url="https://example.com/repost")])
    with connection() as c:
        assert c.execute("SELECT count(*) FROM jobs").fetchone()[0] == 2
        assert c.execute("SELECT count(*) FROM jobs j WHERE NOT EXISTS (SELECT 1 FROM job_sources s WHERE s.job_id=j.id)").fetchone()[0] == 0


def test_conflicting_identity_rolls_back_batch_instead_of_committing_orphans():
    ingest_jobs([job(), job(external_id="two", url="https://example.com/2", title="Desarrollador Java")])
    with pytest.raises(ValueError, match="ofertas distintas"):
        ingest_jobs([job(external_id="three", url="https://example.com/3", title="Analista nuevo"),
                     job(external_id="two")])
    with connection() as c:
        assert c.execute("SELECT count(*) FROM jobs").fetchone()[0] == 2
        assert c.execute("SELECT status FROM ingestion_runs ORDER BY rowid DESC LIMIT 1").fetchone()[0] == "failed"


def test_missing_detail_does_not_erase_previous_description():
    ingest_jobs([job(), job(description=None)])
    with connection() as c:
        assert c.execute("SELECT description_raw FROM jobs").fetchone()[0] == "Python y SQL"
        observation = json.loads(c.execute("SELECT snapshot FROM job_observations ORDER BY rowid DESC LIMIT 1").fetchone()[0])
        assert observation["description_retained_from_previous_observation"] is True


def test_partial_card_keeps_known_title_company_and_location():
    ingest_jobs([job(), job(title="Sin título", company=None, location=None, description=None)])
    with connection() as c:
        assert c.execute("SELECT j.title,j.location,c.name FROM jobs j JOIN companies c ON c.id=j.company_id").fetchall() == [("Analista de datos", "Lima", "Example")]


def test_timeout_records_search_and_cannot_ingest(monkeypatch):
    def timeout(*args):
        raise TimeoutError("Source download exceeded deadline")
    monkeypatch.setattr("radar.source_fetch.fetch_jobs", timeout)
    with pytest.raises(TimeoutError):
        pipeline.run_ingestion("portal", "analista datos", "Lima", search_timeout=0.01,
                               market_ids=["sistemas_software"])
    with connection() as c:
        assert c.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
        query, context, status = c.execute("SELECT query,context,status FROM ingestion_runs").fetchone()
    assert query == "analista datos" and status == "timeout"
    assert json.loads(context)["requested_market_ids"] == ["sistemas_software"]


def test_successful_search_keeps_query_and_counts_before_freshness_filter(monkeypatch):
    class Source:
        def search(self, *args):
            return [job(), job(url="https://example.com/undated", published_at=None)]
    monkeypatch.setattr(pipeline, "resolve_source", lambda _: Source())
    result = pipeline.run_ingestion("portal", "analista datos", "Lima")
    assert result["created"] == 1 and result["discarded_stale_or_undated"] == 1
    with connection() as c:
        assert c.execute("SELECT query,jobs_found,jobs_created,status FROM ingestion_runs").fetchall() == [("analista datos", 2, 1, "success")]


def test_identity_audit_reports_orphans_without_modifying_them():
    from radar.db.repository import audit_data_quality

    ingest_jobs([job()])
    with connection() as c:
        c.execute("DELETE FROM job_sources")
    report = audit_data_quality()
    assert report["jobs_without_source"] == report["active_jobs_without_source"] == 1
    with connection() as c:
        assert c.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1
