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


def test_find_jobs_near_works_across_peru():
    from datetime import UTC, datetime

    from radar.db.repository import ingest_jobs as store
    from radar.domain.models import RawJob
    from radar.feed import map_places

    now = datetime.now(UTC)
    store([
        RawJob("t", "Practicante de Procesos", "A", "https://e.com/a", location="Miraflores, Lima",
               description="Excel", published_at=now),
        RawJob("t", "Practicante de Logística", "B", "https://e.com/b", location="San Isidro, Peru",
               description="Excel", published_at=now),
        RawJob("t", "Practicante de Calidad", "C", "https://e.com/c", location="Ate, Lima",
               description="Excel", published_at=now),
        RawJob("t", "Analista de Compras", "D", "https://e.com/d", location="Yanahuara, Arequipa",
               description="Excel, SAP", published_at=now),
        RawJob("t", "Practicante de Producción", "E", "https://e.com/e", location="Áncash",
               description="Excel", published_at=now),
    ])
    lima = tools.find_jobs_near("Miraflores", 5)
    assert [j["place"] for j in lima["jobs"]] == ["Miraflores", "San Isidro"]
    assert lima["jobs"][0]["km"] == 0
    assert tools.find_jobs_near("Miraflores", 30)["total"] == 3  # Arequipa queda a ~1000 km
    south = tools.find_jobs_near("Arequipa", 10)
    assert [j["place"] for j in south["jobs"]] == ["Arequipa"]
    nationwide = tools.find_jobs_near("Lima", 2000)
    assert nationwide["total"] == 5
    assert {j["precision"] for j in nationwide["jobs"]} == {"district", "city", "department"}
    places = {p["name"]: p for p in map_places()["places"]}
    assert places["Arequipa"]["precision"] == "city" and places["Áncash"]["precision"] == "department"
    with pytest.raises(ValueError):
        tools.find_jobs_near("Narnia")


def _seed_market():
    from datetime import UTC, datetime

    from radar.db.repository import ingest_jobs as store
    from radar.domain.models import RawJob

    now = datetime.now(UTC)
    store([
        RawJob("t", "Practicante de Procesos", "ACME", "https://e.com/1", location="Miraflores, Lima",
               description="Requisito: Excel y Power BI. Salario S/ 1500 mensual.", published_at=now),
        RawJob("t", "Analista de Logística", "Beta", "https://e.com/2", location="Arequipa",
               description="Excel, SAP y SQL.", published_at=now),
        RawJob("t", "Practicante de Calidad", "ACME", "https://e.com/3", location="Ate, Lima",
               description="Excel y Lean.", published_at=now),
    ])
    return tools.search_saved_jobs(limit=10)["jobs"]


def test_agent_can_answer_open_questions_about_the_market():
    jobs = _seed_market()
    ids = {j["title"]: j["id"] for j in jobs}
    tools.update_profile("Ana", ["Procesos"], ["Lima"], {"Excel": "advanced"})

    detail = tools.get_job_details(ids["Practicante de Procesos"])
    assert detail["company"] == "ACME" and {s["name"] for s in detail["skills"]} >= {"Excel", "Power BI"}
    assert detail["fit"]["strong_matches"] == ["Excel"] and "Power BI" in detail["fit"]["missing_skills"]
    assert "Requisito" in detail["description"]

    fit = tools.explain_job_fit(ids["Practicante de Procesos"])
    assert abs(sum(d["contribution"] for d in fit["dimensions"]) - fit["total"]) < 1

    demand = tools.get_skill_demand()
    assert demand["skills"][0]["skill"] == "Excel" and demand["skills"][0]["jobs"] == 3

    by_place = {r["value"]: r["jobs"] for r in tools.get_market_breakdown("place")["rows"]}
    assert by_place["Arequipa"] == 1 and by_place["Miraflores"] == 1
    assert tools.get_market_breakdown("company")["rows"][0] == {"value": "ACME", "jobs": 2}
    with pytest.raises(ValueError):
        tools.get_market_breakdown("color")

    cmp = tools.compare_jobs([ids["Practicante de Procesos"], ids["Analista de Logística"]])
    assert cmp["common_skills"] == ["Excel"]
    assert "Power BI" in cmp["jobs"][0]["only_here"]
    with pytest.raises(ValueError):
        tools.compare_jobs([ids["Practicante de Procesos"]])

    assert tools.plan_learning()["skills"][0]["skill"] in {"Power BI", "SQL", "SAP", "Lean"}
    stats = tools.get_salary_stats()
    assert stats["groups"] == [] or stats["groups"][0]["count"] >= 1


def test_readonly_sql_is_bounded_and_rejects_writes():
    _seed_market()
    schema = tools.get_data_schema()
    assert "jobs" in {t["table"] for t in schema["tables"]}
    rows = tools.run_readonly_sql("SELECT count(*) AS n FROM jobs")
    assert rows["rows"][0][0] == 3
    with pytest.raises(ValueError):
        tools.run_readonly_sql("DELETE FROM jobs")
    with pytest.raises(ValueError):
        tools.run_readonly_sql("SELECT 1; DROP TABLE jobs")
    assert tools.REGISTRY["run_readonly_sql"].chat and not tools.REGISTRY["run_readonly_sql"].write


def test_mcp_exposes_resources_prompts_and_skill_export(tmp_path):
    import asyncio

    from radar.mcp import server
    from radar.skill_export import export, render

    prompts = {p.name for p in asyncio.run(server.mcp.list_prompts())}
    assert {"configurar_radar", "analizar_mercado", "plan_de_aprendizaje"} <= prompts
    resources = {str(r.uri) for r in asyncio.run(server.mcp.list_resources())}
    templates = {t.uriTemplate for t in asyncio.run(server.mcp.list_resource_templates())}
    assert "radar://topics" in resources and "radar://help/{topic}" in templates
    text = render()
    assert text.startswith("---\nname: radar") and "`run_readonly_sql`" in text and "`favorite_job` | escribe" in text
    assert "Radar nunca postula" in text
    assert export(tmp_path).read_text(encoding="utf-8") == text
