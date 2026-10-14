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


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8100/api/health", "http://localhost/", "http://[::1]/", "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.5/", "http://192.168.1.1/admin", "file:///etc/passwd", "ftp://example.com/x", "javascript:alert(1)", "http:///nohost",
])
def test_private_or_non_http_urls_are_refused(url, monkeypatch):
    from radar.security import UnsafeUrlError, ensure_public_http_url

    monkeypatch.setattr("radar.security.socket.getaddrinfo", lambda host, *a, **k: [(2, 1, 6, "", ("127.0.0.1", 0))])
    with pytest.raises(UnsafeUrlError):
        ensure_public_http_url(url)


def test_public_urls_and_hostnames_resolving_to_public_addresses_are_allowed(monkeypatch):
    from radar.security import UnsafeUrlError, ensure_public_http_url

    ensure_public_http_url("https://8.8.8.8/")
    monkeypatch.setattr("radar.security.socket.getaddrinfo", lambda host, *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))])
    ensure_public_http_url("https://portal.example/oferta/1")
    monkeypatch.setattr("radar.security.socket.getaddrinfo", lambda host, *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0)), (2, 1, 6, "", ("10.0.0.9", 0))])
    with pytest.raises(UnsafeUrlError):  # basta una dirección privada entre las resueltas
        ensure_public_http_url("https://mixed.example/")


def test_liveness_never_contacts_private_addresses(monkeypatch):
    from radar.db.database import connection
    from radar.db.repository import ingest_jobs
    from radar.domain.models import RawJob
    from radar.liveness import check_application_status

    ingest_jobs([RawJob("t", "Practicante", "ACME", "http://127.0.0.1:8100/api/health", location="Lima", description="x")])
    contacted = []
    monkeypatch.setattr("radar.security.socket.getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 0))])
    import httpx

    class Spy(httpx.HTTPTransport):
        def handle_request(self, request):
            contacted.append(str(request.url))
            raise AssertionError("no debía abrir conexión")

    real_client = httpx.Client
    monkeypatch.setattr("radar.liveness.httpx.Client", lambda **kw: real_client(transport=Spy(), **kw))
    with connection() as conn:
        conn.execute("UPDATE jobs SET is_active=1, published_at=now()")
    stats = check_application_status(limit=5)
    assert contacted == [] and stats["errors"] >= 1
