import json

import pytest
from fastapi.testclient import TestClient

from radar import mcp_config
from radar.api import app


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
    monkeypatch.setattr(mcp_config.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("RADAR_DB_PATH", raising=False)
    monkeypatch.setattr(mcp_config, "server_command", lambda: "/opt/radar/radar-mcp")


def test_describe_lists_every_client_with_a_ready_snippet_or_command():
    info = mcp_config.describe()
    by_id = {c["id"]: c for c in info["clients"]}
    assert set(by_id) == {"claude_desktop", "claude_code", "cursor", "gemini_cli"}
    assert json.loads(by_id["cursor"]["snippet"])["mcpServers"]["radar"]["command"] == "/opt/radar/radar-mcp"
    assert by_id["claude_code"]["command"] == "claude mcp add radar -- /opt/radar/radar-mcp"
    assert by_id["claude_code"]["can_install"] is False


def test_install_creates_the_file_when_missing(tmp_path):
    out = mcp_config.install("cursor")
    path = tmp_path / ".cursor/mcp.json"
    assert out["backup"] is None and json.loads(path.read_text())["mcpServers"]["radar"]["command"] == "/opt/radar/radar-mcp"


def test_install_keeps_other_servers_and_backs_up_the_old_file(tmp_path):
    path = mcp_config.config_path("gemini_cli")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"theme": "dark", "mcpServers": {"otro": {"command": "x"}}}))
    out = mcp_config.install("gemini_cli")
    data = json.loads(path.read_text())
    assert data["theme"] == "dark" and set(data["mcpServers"]) == {"otro", "radar"}
    assert json.loads((tmp_path / ".gemini/settings.json.radar-bak").read_text())["mcpServers"] == {"otro": {"command": "x"}}
    assert out["backup"].endswith(".radar-bak")
    again = mcp_config.install("gemini_cli")
    assert again["replaced_existing_radar_entry"] is False  # misma entrada: nada que reemplazar


def test_install_refuses_broken_json_and_unknown_clients(tmp_path):
    path = mcp_config.config_path("cursor")
    path.parent.mkdir(parents=True)
    path.write_text("{ no json")
    with pytest.raises(ValueError):
        mcp_config.install("cursor")
    assert path.read_text() == "{ no json"  # no toca lo que no entiende
    with pytest.raises(ValueError):
        mcp_config.install("claude_code")
    with pytest.raises(ValueError):
        mcp_config.config_path("../../etc/passwd")


def test_db_path_is_passed_to_the_server(monkeypatch):
    monkeypatch.setenv("RADAR_DB_PATH", "/data/radar.db")
    assert mcp_config.server_entry()["env"] == {"RADAR_DB_PATH": "/data/radar.db"}


def test_endpoints_accept_only_closed_client_list():
    api = TestClient(app)
    assert api.get("/api/mcp/config").status_code == 200
    assert api.post("/api/mcp/install", json={"client": "../../x"}).status_code == 422
    assert api.post("/api/mcp/install", json={"client": "cursor"}).status_code == 200
