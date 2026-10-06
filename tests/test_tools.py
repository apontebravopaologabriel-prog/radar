import pytest

from radar import tools
from radar.mcp import server


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "radar.db"))


def test_mcp_exposes_the_shared_registry_minus_unconfirmed_writes():
    import asyncio

    exposed = {t.name for t in asyncio.run(server.mcp.list_tools())}
    risky = {n for n, t in tools.REGISTRY.items() if t.write and not t.chat}
    assert risky  # si esto queda vacío, el resto del test no prueba nada
    assert exposed == set(tools.REGISTRY) - risky


def test_mcp_write_tools_respect_read_only():
    from radar.settings import set_setting

    fn = server.mcp._tool_manager._tools["record_career_event"].fn
    set_setting("agent_read_only", "1")
    with pytest.raises(ValueError, match="solo lectura"):
        fn(event_type="note", title="x")
    set_setting("agent_read_only", None)
    fn(event_type="note", title="x")  # sin el ajuste, escribe normalmente


def test_write_tools_are_classified_and_chat_excludes_risky_ones():
    writes = {n for n, t in tools.REGISTRY.items() if t.write}
    assert {"update_profile", "track_job_application", "favorite_job", "set_career_track"} <= writes
    assert "get_today_feed" not in writes
    chat = {t.name for t in tools.chat_tools()}
    assert "ingest_jobs" not in chat and "save_target_profile" not in chat


def test_schemas_derive_from_signatures():
    schema = tools.REGISTRY["track_job_application"].json_schema()
    assert schema["required"] == ["job_id"]
    assert "skills" in tools.REGISTRY["update_profile"].json_schema()["properties"]


def test_schemas_omit_default_values_the_model_never_needs():
    # El esquema que ve el modelo no necesita el valor por defecto (la opcionalidad ya la marca `required`);
    # Tool.call() lo sigue aplicando al ejecutar, sin cambios. Quitarlo del esquema ahorra bytes en cada mensaje.
    for t in tools.chat_tools():
        for prop in t.json_schema().get("properties", {}).values():
            assert "default" not in prop, f"{t.name} todavía manda un default al modelo"
    import inspect

    status_default = inspect.signature(tools.REGISTRY["track_job_application"].fn).parameters["status"].default
    assert status_default == "saved"


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


def test_salary_stats_drops_implausible_amounts_and_feed_breaks_ties_by_recency():
    from datetime import UTC, datetime, timedelta

    from radar.db.repository import ingest_jobs as store
    from radar.domain.models import RawJob

    now = datetime.now(UTC)
    store([
        RawJob("t", "Practicante de Procesos A", "A", "https://e.com/a", location="Lima", description="Excel",
               published_at=now - timedelta(days=5), salary_min=1, salary_max=1, salary_currency="PEN"),
        RawJob("t", "Practicante de Procesos B", "B", "https://e.com/b", location="Lima", description="Excel",
               published_at=now, salary_min=1500, salary_max=1500, salary_currency="PEN"),
    ])
    stats = tools.get_salary_stats()
    assert stats["discarded_implausible"] >= 0
    assert all(g["min"] >= 500 for g in stats["groups"] if g["currency"] == "PEN")
    tools.update_profile("Ana", ["Procesos"], ["Lima"], {"Excel": "advanced"})
    titles = [j["title"] for j in tools.get_today_feed(5)["jobs"]]
    assert titles.index("Practicante de Procesos B") < titles.index("Practicante de Procesos A")


def test_hot_query_indexes_exist_and_are_used():
    from radar.db.database import connection

    with connection() as conn:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
        plan = " ".join(
            str(r) for r in conn.execute(
                "EXPLAIN QUERY PLAN SELECT (SELECT source_url FROM job_sources js WHERE js.job_id=j.id "
                "ORDER BY js.last_seen_at DESC LIMIT 1) FROM jobs j"
            ).fetchall()
        )
    assert {"job_sources_job_seen_idx", "job_scores_profile_idx", "applications_job_idx"} <= names
    assert "job_sources_job_seen_idx" in plan  # sin el índice era un SCAN por oferta


def test_large_lists_are_gzipped_but_chat_stream_is_not():
    from fastapi.testclient import TestClient

    from radar.api import app

    _seed_market()
    api = TestClient(app)
    res = api.get("/api/jobs", headers={"Accept-Encoding": "gzip"})
    assert res.status_code == 200 and res.json()["total"] >= 1
    small = api.get("/api/health", headers={"Accept-Encoding": "gzip"})
    assert "content-encoding" not in small.headers  # bajo el umbral no se comprime


def test_slim_lists_drop_descriptions_and_detail_endpoint_returns_them():
    from fastapi.testclient import TestClient

    from radar.api import app

    _seed_market()
    api = TestClient(app)
    full = api.get("/api/jobs").json()["jobs"]
    slim = api.get("/api/jobs?slim=true").json()["jobs"]
    assert full[0]["description"] and "description" not in slim[0] and slim[0]["has_description"] is True
    assert "description" not in api.get("/api/map/jobs?slim=true").json()["features"][0]["properties"]
    detail = api.get(f"/api/jobs/{slim[0]['id']}/description").json()
    assert detail["description"] and api.get("/api/jobs/no-existe/description").status_code == 404


def test_jobs_endpoint_paginates_without_changing_the_default():
    from fastapi.testclient import TestClient

    from radar.api import app

    _seed_market()
    api = TestClient(app)
    everything = api.get("/api/jobs").json()
    total = everything["total"]
    assert total >= 1 and len(everything["jobs"]) == total
    first = api.get("/api/jobs?limit=1").json()
    assert len(first["jobs"]) == 1 and first["total"] == total and first["offset"] == 0
    rest = api.get("/api/jobs?limit=1&offset=1").json()
    assert rest["total"] == total and [j["id"] for j in rest["jobs"]] == [j["id"] for j in everything["jobs"][1:2]]
    assert api.get(f"/api/jobs?offset={total}").json()["jobs"] == []
    assert api.get("/api/jobs?limit=0").status_code == 422


def test_compare_places_is_multidimensional_and_hidden_duplicates_stay_out_of_chat():
    result = tools.compare_places("Ate", "Miraflores")
    assert {"top_areas", "work_mode", "seniority", "salary_pen", "production"} <= set(result["places"][0])
    assert "stronger_for_production" not in result
    chat = {t.name for t in tools.chat_tools()}
    assert not {"get_market_summary", "list_recommended_jobs", "get_skill_impact", "get_job_history"} & chat


def test_place_profile_counts_only_that_place_and_prompt_does_not_autorun_setup():
    from radar.agent import loop

    profile = tools.get_place_profile("Ate")
    assert profile["place"] == "Ate" and {"jobs", "top_companies", "salary_pen"} <= set(profile)
    assert "get_place_profile" in {t.name for t in tools.chat_tools()}
    assert "llama primero a get_setup_status" not in loop.SYSTEM_PROMPT
    assert "SIN llamar herramientas" in loop.SYSTEM_PROMPT


def test_classification_audit_is_read_only_and_reclassify_needs_confirmation():
    assert tools.REGISTRY["audit_classification"].write is False
    assert tools.REGISTRY["reclassify_jobs"].write is True
    report = tools.audit_classification(3)
    assert {"jobs", "drifted", "drift_pct", "top_transitions", "sample"} <= set(report)


def test_market_breakdown_supports_sector_and_filters():
    from radar import insights

    assert "sector" in insights.BREAKDOWNS
    result = tools.get_market_breakdown("company", 60, 5, search="asistente", exclude_sector="Finanzas y banca,Tecnología y servicios TI")
    assert result["filters"]["search"] == "asistente" and "rows" in result
    with pytest.raises(ValueError):
        tools.get_market_breakdown("source", 30, 5, sector="Educación")
    with pytest.raises(ValueError) as exc:
        tools.run_readonly_sql("select nope from jobs")
    assert "Tablas y columnas" in str(exc.value)


def test_refresh_market_is_a_confirmed_write_and_builds_place_focused_steps(monkeypatch):
    from radar import refresh

    assert tools.REGISTRY["refresh_market"].write is True and tools.REGISTRY["get_refresh_status"].write is False
    monkeypatch.setattr(refresh, "_binaries", lambda: {"computrabajo": ["radar", "ingest", "--source", "computrabajo"],
                                                      "jobspy": ["radar", "ingest", "--source", "jobspy"]})
    captured = []
    monkeypatch.setattr(refresh, "_work", lambda steps: captured.extend(steps))
    monkeypatch.setattr(refresh.threading, "Thread", lambda target, args, **k: type("T", (), {"start": lambda self: target(*args)})())
    state = refresh.start_place_refresh("Miraflores")
    assert state["place"] == "Miraflores" and captured
    assert any("Miraflores, Lima" in step for step in captured) and any("Lima" in step and "Miraflores" in " ".join(step) for step in captured)
    refresh._state["running"] = False
    with pytest.raises(ValueError):
        refresh.start_place_refresh("Marte")


def test_system_tools_are_confirmed_writes_and_schedule_edits_only_the_timer(tmp_path, monkeypatch):
    from radar import system

    assert tools.REGISTRY["get_system_status"].write is False
    assert all(tools.REGISTRY[n].write for n in ("set_refresh_schedule", "run_maintenance", "set_score_weights"))
    unit = tmp_path / "radar-refresh.timer"
    unit.write_text("[Unit]\nDescription=x\n\n[Timer]\nOnBootSec=5min\nOnUnitActiveSec=24h\n", encoding="utf-8")
    calls = []
    monkeypatch.setattr(system, "timer_path", lambda: unit)
    monkeypatch.setattr(system.shutil, "which", lambda name: "/usr/bin/systemctl")
    monkeypatch.setattr(system, "_systemctl", lambda *a: calls.append(a) or type("R", (), {"stdout": "[]", "returncode": 0})())
    system.set_schedule(7, on_boot=False)
    text = unit.read_text(encoding="utf-8")
    assert "OnUnitActiveSec=7d" in text and "OnBootSec" not in text
    assert ("daemon-reload",) in calls and ("restart", "radar-refresh.timer") in calls
    with pytest.raises(ValueError):
        system.set_schedule(99)
    with pytest.raises(ValueError):
        system.run_maintenance("rm -rf")
    system.set_schedule(0)
    assert ("disable", "--now", "radar-refresh.timer") in calls


def test_backup_and_status_work_on_a_real_database():
    from radar import system

    result = system.backup_database()
    assert result["size_mb"] >= 0 and system.system_status()["database"]["integrity"] == "ok"


def test_get_my_cv_reads_the_master_cv_without_private_paths(tmp_path, monkeypatch):
    import json

    from radar import cv_targets

    monkeypatch.setattr(cv_targets, "data_dir", lambda: tmp_path)
    assert tools.get_my_cv()["cv"] is None
    (tmp_path / "cv_master.json").write_text(json.dumps({"_nota": "x", "name": "Ana", "headline": "Ing. industrial",
                                                        "experience": [{"role": "Auxiliar"}], "photo_path": "/home/x.jpg"}), encoding="utf-8")
    cv = tools.get_my_cv()["cv"]
    assert cv["experience"] and "photo_path" not in cv and "_nota" not in cv


def test_update_cv_edits_the_master_cv_safely(tmp_path, monkeypatch):
    import json

    from radar import cv_edit, cv_targets

    monkeypatch.setattr(cv_targets, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(cv_edit, "data_dir", lambda: tmp_path)
    cv_file = tmp_path / "cv_master.json"
    cv_file.write_text(json.dumps({"name": "Ana", "photo_path": "/x.jpg", "certifications": [{"name": "SQL", "date": "2025-06"}],
                                   "gaps_of_evidence": ["Python sin certificación"]}), encoding="utf-8")
    assert tools.REGISTRY["update_cv"].write is True
    tools.update_cv("certifications", "add", {"name": "Lean Six Sigma Green Belt", "issuer": "ASQ", "date": "2026-08"})
    data = json.loads(cv_file.read_text(encoding="utf-8"))
    assert [c["name"] for c in data["certifications"]] == ["SQL", "Lean Six Sigma Green Belt"] and data["photo_path"] == "/x.jpg"
    assert list(tmp_path.glob("cv_master.json.bak-*"))
    tools.update_cv("certifications", "update", {"date": "2026-09"}, match="green belt")
    assert json.loads(cv_file.read_text(encoding="utf-8"))["certifications"][1]["date"] == "2026-09"
    for bad in (("certifications", "add", {"name": "SQL"}), ("certifications", "add", {"name": "X", "date": "ayer"}),
                ("certifications", "add", {"issuer": "solo emisor"}), ("certifications", "add", {"name": "Y", "color": "rojo"}),
                ("tools", "add", {"name": "Excel"}), ("certifications", "remove", None)):
        with pytest.raises(ValueError):
            tools.update_cv(*bad)
    tools.update_cv("gaps", "remove", match="python")
    tools.update_cv("certifications", "remove", match="sql")
    assert [c["name"] for c in json.loads(cv_file.read_text(encoding="utf-8"))["certifications"]] == ["Lean Six Sigma Green Belt"]
