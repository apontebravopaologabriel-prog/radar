import os
import stat

import pytest
from fastapi.testclient import TestClient

from radar.api import app
from radar.db.database import connection, database_path
from radar.security import allowed_hosts, harden_data_dir


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "data" / "radar.db"))
    monkeypatch.delenv("RADAR_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("RADAR_API_HOST", raising=False)
    monkeypatch.delenv("RADAR_ALLOWED_HOSTS", raising=False)


def test_foreign_host_is_rejected_dns_rebinding():
    client = TestClient(app)
    assert client.get("/api/health", headers={"host": "evil.example.com:8100"}).status_code == 403
    assert client.get("/api/health", headers={"host": "127.0.0.1:8100"}).status_code == 200
    assert client.get("/api/health", headers={"host": "localhost"}).status_code == 200


def test_configured_bind_address_and_extra_hosts_are_allowed(monkeypatch):
    monkeypatch.setenv("RADAR_API_HOST", "100.64.0.7")
    monkeypatch.setenv("RADAR_ALLOWED_HOSTS", "radar.tailnet.ts.net")
    assert {"100.64.0.7", "radar.tailnet.ts.net"} <= allowed_hosts()
    client = TestClient(app)
    assert client.get("/api/health", headers={"host": "100.64.0.7:8100"}).status_code == 200
    monkeypatch.setenv("RADAR_API_HOST", "0.0.0.0")
    assert "0.0.0.0" not in allowed_hosts()


def test_cross_origin_writes_are_rejected_but_reads_and_same_origin_work():
    with connection():  # el editor SQL abre la base en solo lectura: debe existir
        pass
    client = TestClient(app)
    body = {"sql": "select 1"}
    evil = client.post("/api/analytics/query", json=body, headers={"origin": "https://evil.example.com"})
    assert evil.status_code == 403 and evil.json()["detail"] == "Origen no permitido"
    assert client.post("/api/analytics/query", json=body, headers={"origin": "null"}).status_code == 403
    ok = client.post("/api/analytics/query", json=body, headers={"origin": "http://127.0.0.1:8100"})
    assert ok.status_code != 403
    assert client.post("/api/analytics/query", json=body).status_code != 403  # curl y scripts no envían Origin
    assert client.get("/api/health", headers={"origin": "https://evil.example.com"}).status_code == 200


def test_security_headers_present():
    response = TestClient(app).get("/api/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


@pytest.mark.skipif(os.name == "nt", reason="permisos POSIX")
def test_data_files_become_private():
    with connection():
        pass
    db_file = database_path()
    folder = db_file.parent
    (folder / "cv_master.json").write_text("{}")
    (folder / "radar.db.bak.old").write_text("x")
    (folder / "backups").mkdir()
    (folder / "backups" / "radar-1.db").write_text("x")
    for path in (folder / "cv_master.json", folder / "radar.db.bak.old", folder / "backups" / "radar-1.db"):
        path.chmod(0o644)
    harden_data_dir(db_file, owned_dir=True)
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    for path in (db_file, folder / "cv_master.json", folder / "radar.db.bak.old", folder / "backups" / "radar-1.db"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600, path
