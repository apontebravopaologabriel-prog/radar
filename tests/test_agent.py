import json

import httpx
import pytest
from fastapi.testclient import TestClient

from radar.agent import loop
from radar.agent.provider import LLMConfig, ProviderError, stream_chat
from radar.api import app
from radar.settings import read_secrets, secrets_path, set_setting


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "radar.db"))
    monkeypatch.delenv("RADAR_ACCESS_TOKEN", raising=False)
    set_setting("agent_enabled", "1")  # el agente nace apagado; las pruebas lo activan


CONFIG = LLMConfig("deepseek", "https://llm.test", "m", "sk-secret")


def _sse(*chunks):
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
    return body.encode()


def _client(*responses):
    """Cliente httpx que responde en orden con cuerpos SSE y registra las peticiones."""
    queue = list(responses)
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        status, body = queue.pop(0)
        return httpx.Response(status, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler)), sent


def _text(text):
    return (200, _sse({"choices": [{"delta": {"content": text}}]},
                      {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 5}}))


def _call(name, args, cid="c1"):
    return (200, _sse({"choices": [{"delta": {"tool_calls": [
        {"index": 0, "id": cid, "function": {"name": name, "arguments": json.dumps(args)}}]}}]}))


def test_provider_streams_text_and_tool_calls():
    client, _ = _client(_call("get_today_feed", {"limit": 2}))
    events = list(stream_chat(CONFIG, [], [], client))
    assert events == [{"tool_calls": [{"id": "c1", "name": "get_today_feed", "arguments": '{"limit": 2}'}]}]


def test_provider_maps_auth_errors_without_leaking_key():
    client, _ = _client((401, b"bad key sk-secret"))
    with pytest.raises(ProviderError) as exc:
        list(stream_chat(CONFIG, [], [], client))
    assert "sk-secret" not in str(exc.value)


def test_read_tool_runs_and_result_is_marked_untrusted():
    client, sent = _client(_call("get_market_breakdown", {"by": "area"}), _text("Listo"))
    events = list(loop.run_turn(CONFIG, [{"role": "user", "content": "resumen"}], client))
    kinds = [e["type"] for e in events if e["type"] != "usage"]
    assert kinds == ["assistant_message", "tool_result", "text", "done"]
    tool_msg = next(e for e in events if e["type"] == "tool_result")["message"]
    assert "datos_externos_no_confiables" in tool_msg["content"]
    assert sent[0]["messages"][0]["role"] == "system" and sent[0]["tools"]
    assert loop.month_usage() == 15


def test_ui_context_is_given_to_agent_as_navigation_data():
    client, sent = _client(_text("Estoy en Análisis."))
    list(loop.run_turn(CONFIG, [{"role": "user", "content": "en qué vista estoy"}], client,
                       context={"screen": "analysis", "analysis": {"ready": True, "windows": [{"title": "Ofertas por área"}], "recentQueries": []}}))
    system = sent[0]["messages"][0]["content"]
    assert "CONTEXTO ACTUAL DE LA INTERFAZ" in system
    assert '"screen":"analysis"' in system
    assert "Ofertas por área" in system


def test_write_tool_is_never_executed_by_the_loop():
    client, _ = _client(_call("favorite_job", {"job_id": "x"}))
    events = list(loop.run_turn(CONFIG, [{"role": "user", "content": "guarda"}], client))
    pending = next(e for e in events if e["type"] == "pending")["actions"]
    assert pending[0]["name"] == "favorite_job" and events[-1]["type"] == "done"
    assert not any(e["type"] == "tool_result" for e in events)


def test_unknown_or_hidden_tools_are_rejected():
    client, _ = _client(_call("ingest_jobs", {"source": "jobspy", "query": "x"}), _text("ok"))
    events = list(loop.run_turn(CONFIG, [{"role": "user", "content": "x"}], client))
    result = next(e for e in events if e["type"] == "tool_result")["message"]["content"]
    assert "inválidos" in result


def test_monthly_cap_stops_before_calling_the_provider():
    set_setting("agent_monthly_token_cap", "1000")
    loop._record_usage(CONFIG, {"prompt_tokens": 900, "completion_tokens": 200})
    client, sent = _client(_text("no debería llamarse"))
    events = list(loop.run_turn(CONFIG, [{"role": "user", "content": "hola"}], client))
    assert events[0]["type"] == "error" and sent == []


def test_missing_key_is_reported():
    events = list(loop.run_turn(LLMConfig("deepseek", "https://x", "m", None), []))
    assert events[0]["type"] == "error"


def test_api_settings_never_return_the_key_and_file_is_private():
    api = TestClient(app)
    res = api.put("/api/agent/settings", json={"provider": "deepseek", "api_key": "sk-abc"})
    assert res.status_code == 200 and res.json()["has_key"] is True
    assert "sk-abc" not in res.text and "sk-abc" not in api.get("/api/agent/settings").text
    assert oct(secrets_path().stat().st_mode & 0o777) == "0o600"
    assert read_secrets()["llm_key_deepseek"] == "sk-abc"
    api.put("/api/agent/settings", json={"provider": "deepseek", "api_key": ""})
    assert api.get("/api/agent/settings").json()["has_key"] is False


def test_confirm_endpoint_only_runs_write_tools_and_can_reject():
    api = TestClient(app)
    assert api.post("/api/chat/confirm", json={"tool_call_id": "1", "name": "get_market_summary",
                                               "arguments": {}, "approve": True}).status_code == 422
    rejected = api.post("/api/chat/confirm", json={"tool_call_id": "1", "name": "set_career_track",
                                                   "arguments": {"career_id": "sistemas_software"},
                                                   "approve": False}).json()
    assert "cancelado" in rejected["message"]["content"]
    assert api.get("/api/career").json()["active"] == "industrial_engineering"
    api.post("/api/chat/confirm", json={"tool_call_id": "2", "name": "set_career_track",
                                        "arguments": {"career_id": "sistemas_software"}, "approve": True})
    assert api.get("/api/career").json()["active"] == "sistemas_software"


def test_access_token_protects_api(monkeypatch):
    monkeypatch.setenv("RADAR_ACCESS_TOKEN", "clave-larga")
    api = TestClient(app)
    assert api.get("/api/today").status_code == 401
    assert api.get("/api/health").status_code == 200
    assert api.post("/api/auth/login", json={"token": "mala"}).status_code == 401
    assert api.post("/api/auth/login", json={"token": "clave-larga"}).status_code == 200
    assert api.get("/api/today").status_code == 200
    assert TestClient(app).get("/api/today", headers={"Authorization": "Bearer clave-larga"}).status_code == 200


def test_today_applications_and_profile_endpoints():
    api = TestClient(app)
    assert api.get("/api/today").json()["profile_configured"] is False
    res = api.put("/api/profile", json={"name": "Ana", "areas": ["Procesos"], "locations": ["Lima"],
                                        "skills": {"Excel": "basic"}})
    assert res.status_code == 200 and res.json()["profile"]["skills"] == {"Excel": "basic"}
    assert api.put("/api/profile", json={"name": "Ana", "skills": {"Excel": "guru"}}).status_code == 422
    assert api.put("/api/applications/no-existe", json={"status": "saved"}).status_code == 404
    assert api.put("/api/career/weights", json={"weights": {"location": 0.9}}).status_code == 200
    assert api.put("/api/career/weights", json={"weights": {"foo": 1}}).status_code == 422


def test_agent_is_off_by_default_and_enforced_on_the_server():
    set_setting("agent_enabled", "0")
    api = TestClient(app)
    assert api.get("/api/agent/settings").json()["enabled"] is False
    res = api.post("/api/chat", json={"messages": [{"role": "user", "content": "hola"}]})
    assert res.status_code == 403 and res.json()["detail"] == "agent_disabled"
    assert api.post("/api/chat/confirm", json={"tool_call_id": "1", "name": "favorite_job",
                                               "arguments": {}, "approve": True}).status_code == 403
    events = list(loop.run_turn(CONFIG, [{"role": "user", "content": "hola"}]))
    assert events[0]["type"] == "error" and "desactivado" in events[0]["message"]
    api.put("/api/agent/settings", json={"provider": "deepseek", "enabled": True})
    assert api.get("/api/agent/settings").json()["enabled"] is True


def test_read_only_mode_hides_and_blocks_write_tools():
    set_setting("agent_read_only", "1")
    names = {s["function"]["name"] for s in loop._tool_specs()}
    assert "get_today_feed" in names and "favorite_job" not in names
    client, _ = _client(_call("favorite_job", {"job_id": "x"}), _text("ok"))
    events = list(loop.run_turn(CONFIG, [{"role": "user", "content": "guarda"}], client))
    assert not any(e["type"] == "pending" for e in events)
    api = TestClient(app)
    assert api.post("/api/chat/confirm", json={"tool_call_id": "1", "name": "set_career_track",
                                               "arguments": {"career_id": "sistemas_software"},
                                               "approve": True}).status_code == 422


def test_conversations_are_stored_locally_and_deletable_even_when_agent_is_off():
    api = TestClient(app)
    payload = {"title": "Mi búsqueda", "data": {"history": [{"role": "user", "content": "hola"}], "lines": []}}
    created = api.post("/api/conversations", json=payload)
    assert created.status_code == 201
    cid = created.json()["id"]
    assert api.get(f"/api/conversations/{cid}").json()["data"]["history"][0]["content"] == "hola"
    payload["title"] = "Renombrada"
    assert api.put(f"/api/conversations/{cid}", json=payload).status_code == 200
    assert [c["title"] for c in api.get("/api/conversations").json()["conversations"]] == ["Renombrada"]
    assert api.put("/api/conversations/nope", json=payload).status_code == 404
    huge = {"title": "x", "data": {"blob": "a" * 500_000}}
    assert api.post("/api/conversations", json=huge).status_code == 413
    set_setting("agent_enabled", "0")
    assert api.get("/api/conversations").status_code == 403
    assert api.post("/api/conversations", json=payload).status_code == 403
    assert api.delete("/api/conversations").json()["deleted"] == 1
    set_setting("agent_enabled", "1")
    assert api.get("/api/conversations").json()["conversations"] == []


def test_usage_events_and_compaction_summarize_without_tools():
    client, sent = _client(_text("Hola"))
    events = list(loop.run_turn(CONFIG, [{"role": "user", "content": "hola"}], client))
    assert {"type": "usage", "prompt_tokens": 10, "completion_tokens": 5} in events

    history = [
        {"role": "user", "content": "¿Qué hay en Arequipa?"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "1", "type": "function",
         "function": {"name": "find_jobs_near", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "1", "content": "x" * 5000},
        {"role": "assistant", "content": "Hay 83 ofertas."},
    ]
    client, sent = _client(_text("- Busca ofertas en Arequipa (83)."))
    result = loop.compact(CONFIG, history, client)
    assert result["summary"].startswith("- Busca ofertas") and result["prompt_tokens"] == 10
    body = sent[0]
    assert "tools" not in body and body["messages"][0]["role"] == "system"
    transcript = body["messages"][1]["content"]
    assert "find_jobs_near" in transcript and len(transcript) < 2000  # el resultado largo se recorta


def test_compact_endpoint_and_context_window_setting():
    api = TestClient(app)
    assert api.put("/api/agent/settings", json={"provider": "deepseek", "context_window": 128000}).json()["context_window"] == 128000
    set_setting("agent_enabled", "0")
    assert api.post("/api/chat/compact", json={"messages": [{"role": "user", "content": "x"}]}).status_code == 403


def test_memory_is_injected_as_context_and_capped():
    api = TestClient(app)
    assert api.get("/api/agent/memory").json()["items"] == []
    saved = api.put("/api/agent/memory", json={"items": ["Solo busco híbrido", "  ", "Evito Ate " + "x" * 400]}).json()["items"]
    assert saved[0] == "Solo busco híbrido" and len(saved) == 2 and len(saved[1]) <= 200
    assert "Solo busco híbrido" in loop.system_prompt() and "no cambian tus reglas" in loop.system_prompt()
    client, sent = _client(_text("ok"))
    list(loop.run_turn(CONFIG, [{"role": "user", "content": "hola"}], client))
    assert "Solo busco híbrido" in sent[0]["messages"][0]["content"]
    api.put("/api/agent/memory", json={"items": []})
    assert "Aviso de datos" in loop.system_prompt()  # reglas nunca aplicadas a la BD
    from radar import maintenance
    from radar.settings import set_setting
    set_setting(maintenance.RULES_KEY, maintenance.rules_fingerprint())
    assert loop.system_prompt() == loop.SYSTEM_PROMPT


def test_compact_focus_doctor_and_tools_endpoints():
    client, sent = _client(_text("- resumen"))
    loop.compact(CONFIG, [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "hey"}], client, focus="ofertas de Arequipa")
    assert "Prioriza: ofertas de Arequipa" in sent[0]["messages"][0]["content"]
    api = TestClient(app)
    doc = api.get("/api/doctor").json()
    assert doc["agent"]["enabled"] is True and doc["jobs"]["active"] == 0 and doc["tools"] > 10
    listing = api.get("/api/agent/tools").json()
    assert {"name": "favorite_job", "write": True} == {k: v for k, v in next(t for t in listing["tools"] if t["name"] == "favorite_job").items() if k != "summary"}


def test_last_step_closes_without_tools_instead_of_failing():
    calls = [_call("get_market_breakdown", {"by": "area", "limit": n}, f"c{n}") for n in range(1, loop.MAX_STEPS)]
    client, sent = _client(*calls, _text("Con lo obtenido, esto es lo que hay."))
    events = list(loop.run_turn(CONFIG, [{"role": "user", "content": "analiza"}], client))
    assert not any(e["type"] == "error" for e in events)
    assert events[-1]["type"] == "done" and "tools" not in sent[-1] or not sent[-1].get("tools")


def test_repeated_identical_tool_call_is_short_circuited():
    client, _ = _client(_call("get_market_breakdown", {"by": "area"}, "a"), _call("get_market_breakdown", {"by": "area"}, "b"), _text("ok"))
    events = list(loop.run_turn(CONFIG, [{"role": "user", "content": "x"}], client))
    results = [e["message"]["content"] for e in events if e["type"] == "tool_result"]
    assert "misma consulta" in results[1]


def test_large_results_are_shrunk_by_items_and_old_tool_results_are_trimmed():
    big = {"jobs": [{"id": str(i), "title": "x" * 400} for i in range(40)]}
    wrapped = json.loads(loop.wrap_untrusted(big))
    kept = wrapped["datos_externos_no_confiables"]
    assert 1 <= len(kept["jobs"]) < 40 and "recortado" in kept  # JSON válido, lista abreviada
    history = [{"role": "user", "content": "a"}, {"role": "tool", "tool_call_id": "1", "content": "y" * 5000},
               {"role": "assistant", "content": "ok"}, {"role": "user", "content": "b"}, {"role": "tool", "tool_call_id": "2", "content": "z" * 5000}]
    trimmed = loop._trim_old_tool_results(history)
    assert len(trimmed[1]["content"]) < 900 and len(trimmed[4]["content"]) == 5000


def test_past_conversations_are_searchable_accent_insensitive_and_listed_with_counts():
    api = TestClient(app)
    data = {"history": [], "lines": [{"kind": "user", "text": "¿Cuántas ofertas hay en Miraflores para logística?"},
                                     {"kind": "assistant", "text": "Hay 42 ofertas de logística en Miraflores."},
                                     {"kind": "tool", "text": "Consultó get_place_profile"}]}
    api.post("/api/conversations", json={"title": "Miraflores logística", "data": data})
    api.post("/api/conversations", json={"title": "Otra", "data": {"history": [], "lines": [{"kind": "user", "text": "hola"}]}})
    hit = api.get("/api/conversations/search", params={"q": "logistica miraflores"}).json()["conversations"]
    assert len(hit) == 1 and hit[0]["title"] == "Miraflores logística" and "42 ofertas" in " ".join(hit[0]["snippets"])
    listed = api.get("/api/conversations").json()["conversations"]
    assert {c["title"]: c["lines"] for c in listed} == {"Miraflores logística": 3, "Otra": 1}
    assert loop.tools.REGISTRY["search_past_conversations"].write is False
    assert loop.tools.REGISTRY["search_past_conversations"].call({"query": "logistica"})["conversations"]


def test_mentions_endpoint_returns_places_and_is_accent_insensitive():
    api = TestClient(app)
    data = api.get("/api/mentions", params={"q": "mira"}).json()
    assert any(p["name"] == "Miraflores" for p in data["places"]) and data["jobs"] == []
    assert api.get("/api/mentions").json()["places"]


def test_plan_mode_hides_write_tools_and_adds_the_plan_instruction():
    client, sent = _client(_text("1. Reclasificar..."))
    list(loop.run_turn(CONFIG, [{"role": "user", "content": "ordena la BD"}], client, plan=True))
    names = {t["function"]["name"] for t in sent[0]["tools"]}
    assert "reclassify_jobs" not in names and "update_cv" not in names and "get_market_breakdown" in names
    assert "MODO PLAN" in sent[0]["messages"][0]["content"]
    client, sent = _client(_text("ok"))
    list(loop.run_turn(CONFIG, [{"role": "user", "content": "x"}], client))
    assert "MODO PLAN" not in sent[0]["messages"][0]["content"]
    assert "load_tools" in {t["function"]["name"] for t in sent[0]["tools"]}


def test_plan_mode_rejects_a_write_call_even_if_the_model_insists():
    client, _ = _client(_call("reclassify_jobs", {}), _text("no puedo"))
    events = list(loop.run_turn(CONFIG, [{"role": "user", "content": "x"}], client, plan=True))
    assert not any(e["type"] == "pending" for e in events)


def test_profile_edit_confirmation_shows_before_and_after_and_writes_nothing(tmp_path):
    cv = tmp_path / "cv_master.json"
    cv.write_text(json.dumps({"name": "Ana", "home_district": "La Victoria"}), encoding="utf-8")
    client, _ = _client(_call("load_tools", {"groups": ["perfil"]}),
                        _call("update_profile_fields", {"home_district": "Surco", "skills": {"Klingon": "basic"}}))
    events = list(loop.run_turn(CONFIG, [{"role": "user", "content": "me mudé a Surco"}], client))
    [action] = next(e for e in events if e["type"] == "pending")["actions"]
    assert action["name"] == "update_profile_fields"
    assert action["preview"][0].startswith("No se puede aplicar")  # la skill desconocida se detecta antes de aprobar
    client, _ = _client(_call("load_tools", {"groups": ["perfil"]}),
                        _call("update_profile_fields", {"home_district": "Surco"}))
    events = list(loop.run_turn(CONFIG, [{"role": "user", "content": "me mudé a Surco"}], client))
    [action] = next(e for e in events if e["type"] == "pending")["actions"]
    assert action["preview"] == ["Distrito: La Victoria → Surco"]
    assert json.loads(cv.read_text(encoding="utf-8"))["home_district"] == "La Victoria"  # nada se escribe sin aprobar


def _names(request):
    return {t["function"]["name"] for t in request["tools"]}


def test_grouped_tools_are_loaded_on_demand_and_cut_the_schema_size():
    client, sent = _client(_call("load_tools", {"groups": ["sistema"]}), _text("listo"))
    list(loop.run_turn(CONFIG, [{"role": "user", "content": "¿cómo está el sistema?"}], client))
    assert "get_system_status" not in _names(sent[0]) and "load_tools" in _names(sent[0])
    assert "get_system_status" in _names(sent[1]) and "update_cv" not in _names(sent[1])
    assert len(json.dumps(sent[0]["tools"])) < 12_000  # antes ~19.500 caracteres siempre


def test_calling_an_unloaded_group_tool_is_refused_with_a_hint():
    client, _ = _client(_call("get_system_status", {}), _text("ok"))
    events = list(loop.run_turn(CONFIG, [{"role": "user", "content": "estado"}], client))
    result = next(e for e in events if e["type"] == "tool_result")
    assert "load_tools" in result["message"]["content"]


def test_loaded_groups_persist_through_the_conversation_history():
    history = [
        {"role": "user", "content": "estado"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c0", "type": "function", "function": {"name": "load_tools", "arguments": '{"groups": ["cv"]}'}}]},
        {"role": "tool", "tool_call_id": "c0", "content": "{}"},
        {"role": "user", "content": "ahora el CV"},
    ]
    client, sent = _client(_text("ok"))
    list(loop.run_turn(CONFIG, history, client))
    assert "get_my_cv" in _names(sent[0]) and "get_system_status" not in _names(sent[0])


def _long_history(turns: int) -> list[dict]:
    history: list[dict] = []
    for i in range(turns):
        history.append({"role": "user", "content": f"pregunta {i}"})
        history.append({"role": "assistant", "content": f"respuesta {i}"})
    return history


def test_split_keeps_tail_starting_at_user_and_requires_enough_history():
    history = _long_history(8)
    head, tail = loop.split_for_compaction(history)
    assert tail[0] == {"role": "user", "content": "pregunta 4"} and len(tail) == 8
    assert head == history[:8]
    assert loop.split_for_compaction(_long_history(3)) == ([], _long_history(3))  # poco historial: nada que resumir


def test_split_never_cuts_a_tool_call_pair():
    history = _long_history(4)
    history += [
        {"role": "user", "content": "busca"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "1", "type": "function", "function": {"name": "x", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "1", "content": "datos"},
        {"role": "assistant", "content": "hecho"},
    ]
    _, tail = loop.split_for_compaction(history, keep_turns=1)
    assert tail[0]["role"] == "user" and tail[1]["tool_calls"] and tail[2]["role"] == "tool"


def test_should_autocompact_threshold_setting_and_off_switch():
    history = _long_history(8)
    set_setting("agent_context_window", "10000")
    assert not loop.should_autocompact(history, 6000)      # 60 % < 65 %
    assert loop.should_autocompact(history, 6600)          # 66 %
    assert not loop.should_autocompact(history, 0)         # sin dato real no se adivina
    assert not loop.should_autocompact(_long_history(3), 9000)
    set_setting("agent_autocompact_pct", "0")
    assert not loop.should_autocompact(history, 9999)
    set_setting("agent_autocompact_pct", "40")
    assert loop.should_autocompact(history, 4100)


def test_run_turn_autocompacts_then_answers_from_summary_plus_tail():
    set_setting("agent_context_window", "10000")
    history = _long_history(8) + [{"role": "user", "content": "¿y ahora?"}]
    client, sent = _client(_text("OBJETIVO: híbrido\nPREFERENCIAS:\n- Solo híbrido"), _text("Listo."))
    events = list(loop.run_turn(CONFIG, history, client, last_prompt_tokens=8000))
    compacted = next(e for e in events if e["type"] == "compacted")
    assert compacted["history"][0]["content"].startswith(loop.SUMMARY_PREFIX)
    assert compacted["history"][-1] == {"role": "user", "content": "¿y ahora?"}
    assert compacted["memory_candidates"] == ["Solo híbrido"]
    assert len(compacted["history"]) < len(history)
    answer_messages = sent[1]["messages"]
    dumped = json.dumps(answer_messages, ensure_ascii=False)
    assert "pregunta 0" not in dumped and "Solo híbrido" in dumped
    assert events[-1]["type"] == "done"


def test_run_turn_survives_a_failed_compaction():
    set_setting("agent_context_window", "10000")
    history = _long_history(8) + [{"role": "user", "content": "hola"}]
    client, _ = _client((500, b"boom"), (500, b"boom"), _text("Sigo aquí."))
    events = list(loop.run_turn(CONFIG, history, client, last_prompt_tokens=9000))
    assert any(e["type"] == "notice" for e in events) and not any(e["type"] == "compacted" for e in events)
    assert events[-1]["type"] == "done"


def test_second_compaction_nests_the_previous_summary():
    history = [*loop.summary_messages("OBJETIVO: viejo"), *_long_history(7)]
    head, tail = loop.split_for_compaction(history)
    assert head[0]["content"].startswith(loop.SUMMARY_PREFIX) and tail[0]["content"] == "pregunta 3"
    client, sent = _client(_text("OBJETIVO: viejo y nuevo"))
    loop.compact(CONFIG, head, client)
    assert "OBJETIVO: viejo" in sent[0]["messages"][1]["content"]
    assert "Si empieza con un resumen anterior" in sent[0]["messages"][0]["content"]


def test_autocompact_setting_roundtrip_and_chat_accepts_last_prompt_tokens():
    api = TestClient(app)
    out = api.put("/api/agent/settings", json={"provider": "deepseek", "autocompact_pct": 50}).json()
    assert out["autocompact_pct"] == 50
    assert api.put("/api/agent/settings", json={"provider": "deepseek", "autocompact_pct": 95}).status_code == 422


def test_secrets_use_the_system_keyring_when_selected_and_migrate_old_files(monkeypatch):
    from radar import settings

    store: dict[tuple[str, str], str] = {}

    class FakeKeyring:
        @staticmethod
        def set_password(service, name, value):
            store[(service, name)] = value

        @staticmethod
        def get_password(service, name):
            return store.get((service, name))

        @staticmethod
        def delete_password(service, name):
            store.pop((service, name), None)

    settings._write_file_secret("llm_key_openai", "sk-old")  # clave guardada antes en el archivo
    monkeypatch.setattr(settings, "_keyring", lambda: FakeKeyring)
    assert settings.read_secret("llm_key_openai") == "sk-old"
    assert store[("radar", "llm_key_openai")] == "sk-old" and "llm_key_openai" not in settings.read_secrets()
    settings.write_secret("llm_key_deepseek", "sk-new")
    assert store[("radar", "llm_key_deepseek")] == "sk-new" and settings.read_secrets() == {}
    settings.write_secret("llm_key_deepseek", None)
    assert settings.read_secret("llm_key_deepseek") is None


def test_secrets_default_to_the_protected_file_on_posix(monkeypatch):
    from radar import settings

    monkeypatch.delenv("RADAR_SECRETS_BACKEND", raising=False)
    if __import__("os").name != "nt":
        assert settings._keyring() is None
    monkeypatch.setenv("RADAR_SECRETS_BACKEND", "file")
    assert settings._keyring() is None
