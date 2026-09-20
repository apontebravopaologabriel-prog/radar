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
    client, sent = _client(_call("get_market_summary", {}), _text("Listo"))
    events = list(loop.run_turn(CONFIG, [{"role": "user", "content": "resumen"}], client))
    kinds = [e["type"] for e in events]
    assert kinds == ["assistant_message", "tool_result", "text", "done"]
    tool_msg = next(e for e in events if e["type"] == "tool_result")["message"]
    assert "datos_externos_no_confiables" in tool_msg["content"]
    assert sent[0]["messages"][0]["role"] == "system" and sent[0]["tools"]
    assert loop.month_usage() == 15


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
                                                   "arguments": {"career_id": "contabilidad"},
                                                   "approve": False}).json()
    assert "cancelado" in rejected["message"]["content"]
    assert api.get("/api/career").json()["active"] == "industrial_engineering"
    api.post("/api/chat/confirm", json={"tool_call_id": "2", "name": "set_career_track",
                                        "arguments": {"career_id": "contabilidad"}, "approve": True})
    assert api.get("/api/career").json()["active"] == "contabilidad"


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
                                               "arguments": {"career_id": "contabilidad"},
                                               "approve": True}).status_code == 422
