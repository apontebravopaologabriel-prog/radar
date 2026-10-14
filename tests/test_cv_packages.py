import json
from datetime import UTC, datetime

import pytest
from cv_fixtures import DESCRIPTION, PROFILE

from radar import cv_doc, cv_packages
from radar.db.database import connection
from radar.db.repository import ingest_jobs
from radar.domain.models import RawJob


@pytest.fixture
def job(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "data" / "radar.db"))
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "cv_master.json").write_text(json.dumps(PROFILE), encoding="utf-8")
    monkeypatch.setattr(cv_packages, "default_root", lambda: tmp_path / "Postulaciones")
    ingest_jobs([RawJob(source="test", title="Practicante de Analítica (Lima) ", company="ACME: S.A.", url="https://e.com/oferta/1",
                        location="Miraflores, Lima", description=DESCRIPTION, published_at=datetime.now(UTC))])
    with connection() as conn:
        return conn.execute("SELECT id FROM jobs").fetchone()[0]


@pytest.mark.parametrize(("raw", "expected"), [
    ("Analista: BI / Datos", "Analista BI Datos"),
    ("CON", "CON_"), ("nul.txt", "nul.txt_"), ('a<b>c"d|e?f*', "a b c d e f"), ("  .punto.  ", "punto"),
    ("", "sin nombre"), ("x" * 200, "x" * 80),
])
def test_safe_name_is_valid_on_windows_macos_and_linux(raw, expected):
    assert cv_packages.safe_name(raw) == expected


def test_ascii_folding_and_short_role():
    assert cv_packages.safe_name("José Pérez Ñandú", ascii_only=True) == "Jose Perez Nandu"
    assert cv_packages.short_role("Practicante de Analítica (Lima) ") == "Practicante de Analítica"
    assert cv_packages.short_role("Analista BI - Lima Remoto") == "Analista BI"
    assert cv_packages.short_role("") == "Puesto"


def test_export_creates_a_folder_per_application_with_clean_names(job, tmp_path):
    result = cv_packages.export(job, ["pdf", "docx"])
    folder = tmp_path / "Postulaciones"
    [created] = list(folder.iterdir())
    assert created.name.endswith("ACME S.A. - Practicante de Analitica") and created.name[:4] == str(datetime.now(UTC).year)
    names = sorted(p.name for p in created.iterdir())
    assert names == ["CV Ana Perez & Co - Practicante de Analitica.docx", "CV Ana Perez & Co - Practicante de Analitica.pdf",
                     "oferta.md", "postulacion.json"]
    assert (created / names[1]).read_bytes().startswith(b"%PDF") and result["pages"] == 1
    offer = (created / "oferta.md").read_text(encoding="utf-8")
    assert "https://e.com/oferta/1" in offer and "Excel, Power BI y Python" in offer
    manifest = json.loads((created / "postulacion.json").read_text(encoding="utf-8"))
    assert manifest["template"] == "ats" and manifest["files"][0]["sha256"] and manifest["profile_sha256"]


def test_reexport_reuses_the_folder_and_archives_the_previous_version(job, tmp_path):
    first = cv_packages.export(job)
    _, bullets = cv_doc.state(job)["selection"]["experience"][0]["id"], [b["id"] for b in cv_doc.state(job)["selection"]["experience"][0]["bullets"]]
    cv_doc.add_ops(job, [{"op": "omit", "id": bullets[0]}])
    second = cv_packages.export(job)
    assert second["folder"] == first["folder"] and len(list((tmp_path / "Postulaciones").iterdir())) == 1
    from pathlib import Path

    old = list((Path(first["folder"]) / "anteriores").iterdir())
    assert len(old) == 1 and old[0].suffix == ".pdf"
    assert first["files"][0]["sha256"] != second["files"][0]["sha256"]


def test_two_offers_with_the_same_title_never_share_a_folder(job, tmp_path):
    cv_packages.export(job)
    ingest_jobs([RawJob(source="test", title="Practicante de Analítica (Lima) ", company="ACME: S.A.", url="https://e.com/oferta/2",
                        location="Surco, Lima", description=DESCRIPTION + " otra", published_at=datetime.now(UTC))])
    with connection() as conn:
        other = conn.execute("SELECT id FROM jobs WHERE id <> %s", (job,)).fetchone()[0]
    cv_packages.export(other)
    assert len(list((tmp_path / "Postulaciones").iterdir())) == 2


def test_modified_files_are_detected_and_files_are_served_by_simple_name_only(job):
    result = cv_packages.export(job)
    from pathlib import Path

    pdf = Path(result["folder"]) / result["files"][0]["name"]
    assert cv_packages.package(job)["files"][0]["modified_after_export"] is False
    pdf.write_bytes(pdf.read_bytes() + b"\n%edit")
    assert cv_packages.package(job)["files"][0]["modified_after_export"] is True
    assert cv_packages.file_path(job, pdf.name) == pdf
    for bad in ("../cv_master.json", "..\\x.pdf", "sub/oferta.md", "postulacion.exe", "nope.pdf"):
        assert cv_packages.file_path(job, bad) is None


def test_mark_applied_logs_the_pipeline_and_never_without_a_package(job):
    with pytest.raises(ValueError):
        cv_packages.mark_applied(job)
    cv_packages.export(job)
    done = cv_packages.mark_applied(job, "Subido en Computrabajo")
    assert done["status"] == "applied" and done["applied_at"]
    with connection() as conn:
        assert conn.execute("SELECT status FROM applications WHERE job_id=%s", (job,)).fetchone()[0] == "applied"


def test_open_folder_uses_the_stored_path_only(job, monkeypatch):
    seen = []
    monkeypatch.setattr(cv_packages, "_launch", lambda path: seen.append(path))
    with pytest.raises(ValueError):
        cv_packages.open_folder(job)
    result = cv_packages.export(job)
    assert cv_packages.open_folder(job)["opened"] == result["folder"] and str(seen[0]) == result["folder"]


def test_settings_validate_folder_and_pattern(job, tmp_path, monkeypatch):
    monkeypatch.setattr(cv_packages.Path, "home", classmethod(lambda cls: tmp_path))
    ok = cv_packages.update_settings(str(tmp_path / "MisCVs"), "CV {nombre} - {puesto} ({fecha})", False)
    assert ok["export_dir"].endswith("MisCVs") and ok["ascii_filenames"] is False and "Ana" in ok["example"]
    for bad_dir in ("relativa/ruta", "/etc", str(tmp_path), str(tmp_path / "data")):
        with pytest.raises(ValueError):
            cv_packages.update_settings(export_dir=bad_dir)
    for bad_pattern in ("sin variables", "{otra}", "CV/{nombre}", "x" * 100 + "{nombre}"):
        with pytest.raises(ValueError):
            cv_packages.update_settings(filename_pattern_=bad_pattern)


def test_studio_http_flow_end_to_end(job, tmp_path):
    from fastapi.testclient import TestClient

    from radar.api import app

    api = TestClient(app)
    state_ = api.get(f"/api/cv/studio/{job}").json()
    bullets = [b["id"] for b in state_["selection"]["experience"][0]["bullets"]]
    page = api.get(f"/api/cv/studio/{job}/page/1.png")
    assert page.status_code == 200 and page.content.startswith(b"\x89PNG") and page.headers["cache-control"] == "no-store"
    assert api.get(f"/api/cv/studio/{job}/page/9.png").status_code == 422
    assert api.post(f"/api/cv/studio/{job}/ops", json={"ops": [{"op": "omit", "id": bullets[0]}]}).json()["document"]["ops"] == 1
    assert api.post(f"/api/cv/studio/{job}/ops", json={"ops": [{"op": "omit", "id": "exp:no"}]}).status_code == 422
    assert api.post(f"/api/cv/studio/{job}/undo").json()["document"]["ops"] == 0
    assert api.post(f"/api/cv/studio/{job}/options", json={"template": "sidebar"}).json()["document"]["template"] == "sidebar"
    assert api.post(f"/api/cv/studio/{job}/options", json={"template": "x" * 5}).status_code == 422
    exported = api.post(f"/api/cv/studio/{job}/export", json={"formats": ["pdf"]}).json()
    name = exported["files"][0]["name"]
    download = api.get(f"/api/cv/packages/{job}/files/{name}")
    assert download.status_code == 200 and download.content.startswith(b"%PDF")
    assert api.get(f"/api/cv/packages/{job}/files/..%2Fcv_master.json").status_code == 404
    assert api.get(f"/api/cv/packages/{job}/files/secrets.json").status_code == 404
    assert api.get("/api/cv/packages").json()["packages"][0]["job_id"] == job
    assert api.post(f"/api/cv/packages/{job}/applied", json={"notes": "ok"}).json()["status"] == "applied"
    assert api.get("/api/cv/settings").json()["filename_pattern"]
    assert api.put("/api/cv/settings", json={"export_dir": "/etc"}).status_code == 422
