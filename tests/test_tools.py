import pytest

from radar import tools
from radar.mcp import server


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "radar.db"))


def test_mcp_exposes_the_shared_registry():
    import asyncio

    exposed = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert exposed == set(tools.REGISTRY)


def test_write_tools_are_classified_and_chat_excludes_risky_ones():
    writes = {n for n, t in tools.REGISTRY.items() if t.write}
    assert {"update_profile", "track_job_application", "favorite_job", "set_career_track"} <= writes
    assert "get_today_feed" not in writes
    chat = {t.name for t in tools.chat_tools()}
    assert "ingest_jobs" not in chat and "save_target_profile" not in chat


def test_schemas_derive_from_signatures():
    schema = tools.REGISTRY["track_job_application"].json_schema()
    assert schema["required"] == ["job_id"]
    assert schema["properties"]["status"]["default"] == "saved"
    assert "skills" in tools.REGISTRY["update_profile"].json_schema()["properties"]


def test_profile_feed_and_skill_impact_roundtrip():
    from datetime import UTC, datetime

    from radar.db.repository import ingest_jobs as store
    from radar.domain.models import RawJob

    store([RawJob("t", "Practicante de Procesos", "ACME", "https://e.com/1", location="Lima",
                  description="Excel, Power BI y SQL", published_at=datetime.now(UTC))])
    fallback = tools.get_today_feed()
    assert fallback["profile_configured"] is False and fallback["jobs"][0]["url"] == "https://e.com/1"
    tools.update_profile("Ana", ["Procesos"], ["Lima"], {"Excel": "advanced"})
    feed = tools.get_today_feed()
    assert feed["profile_configured"] and feed["jobs"][0]["why"].startswith("Coincide en Excel")
    impact = tools.get_skill_impact()
    assert {e["skill"] for e in impact["skills"]} == {"Power BI", "SQL"}
    job_id = feed["jobs"][0]["id"]
    tools.favorite_job(job_id)
    tools.track_job_application(job_id, "applied")
    assert tools.get_today_feed()["jobs"] == []  # ya gestionada
    with pytest.raises(ValueError):
        tools.update_profile("Ana", [], [], {"Excel": "guru"})


def test_setup_status_guides_and_help_is_grounded():
    status = tools.get_setup_status()
    assert status["complete"] is False and status["next"]["id"] == "profile"
    tools.update_profile("Ana", ["Procesos"], ["Lima"], {"Excel": "basic"})
    ids_done = {s["id"] for s in tools.get_setup_status()["steps"] if s["done"]}
    assert {"career", "profile", "skills"} <= ids_done
    topics = tools.get_help()["available_topics"]
    assert {"inicio", "hoy", "agente", "privacidad"} <= set(topics)
    assert "Radar nunca postula" in tools.get_help("inicio")["text"]
    with pytest.raises(ValueError):
        tools.get_help("no-existe")
    assert "get_help" in {t.name for t in tools.chat_tools()}
