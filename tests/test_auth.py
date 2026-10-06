import pytest
from fastapi.testclient import TestClient

from radar import auth
from radar.api import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "radar.db"))
    monkeypatch.setenv("RADAR_ACCESS_TOKEN", "secreto")
    auth._attempts.clear()
    return TestClient(app)


def test_protected_routes_require_authentication(client):
    assert client.get("/api/profile").status_code == 401
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/auth/status").json() == {"required": True, "authenticated": False}


def test_bearer_token_grants_access(client):
    ok = client.get("/api/profile", headers={"Authorization": "Bearer secreto"})
    assert ok.status_code != 401
    bad = client.get("/api/profile", headers={"Authorization": "Bearer otro"})
    assert bad.status_code == 401


def test_login_sets_session_cookie(client):
    assert client.post("/api/auth/login", json={"token": "mala"}).status_code == 401
    assert client.post("/api/auth/login", json={"token": "secreto"}).json() == {"authenticated": True}
    assert client.get("/api/auth/status").json()["authenticated"] is True
    assert client.get("/api/profile").status_code != 401
    client.post("/api/auth/logout")
    assert client.get("/api/profile").status_code == 401


def test_login_is_rate_limited(client):
    for _ in range(auth.MAX_ATTEMPTS):
        assert client.post("/api/auth/login", json={"token": "mala"}).status_code == 401
    assert client.post("/api/auth/login", json={"token": "secreto"}).status_code == 429


def test_no_token_configured_leaves_api_open(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "radar.db"))
    monkeypatch.delenv("RADAR_ACCESS_TOKEN", raising=False)
    assert TestClient(app).get("/api/profile").status_code != 401
