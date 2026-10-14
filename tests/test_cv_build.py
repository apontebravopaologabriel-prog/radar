import json
import shutil
import zipfile
from datetime import UTC, datetime
from xml.etree import ElementTree

import pytest
from cv_fixtures import DESCRIPTION, PROFILE

from radar import cv_build, cv_edit, cv_pdf, tools
from radar.db.database import connection
from radar.db.repository import ingest_jobs
from radar.domain.models import RawJob


@pytest.fixture
def job(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "radar.db"))
    (tmp_path / "cv_master.json").write_text(json.dumps(PROFILE), encoding="utf-8")
    ingest_jobs([RawJob(source="test", title="Practicante de Analítica", company="ACME S.A.", url="https://e.com/1",
                        location="Miraflores, Lima", description=DESCRIPTION, published_at=datetime.now(UTC))])
    with connection() as conn:
        return conn.execute("SELECT id FROM jobs").fetchone()[0]


def test_selection_ranks_relevant_lines_within_page_budget(job):
    selection = cv_build.select(job)
    assert selection["pages_budget"] == 1 and selection["language"] == "es"
    [role] = selection["experience"]
    texts = [b["text"] for b in role["bullets"]]
    assert len(texts) == 3
    assert texts[:2] == ["Dashboard en Power BI de ventas", "Controles de inventario en Excel"]
    assert {o["section"] for o in selection["omitted"]} >= {"experience", "certifications"}
    assert all(o["reason"] for o in selection["omitted"])
    assert [p["title"] for p in selection["projects"]] == ["Reporte automático"]  # el irrelevante queda fuera


def test_skills_without_evidence_never_enter_the_cv(job):
    selection = cv_build.select(job)
    assert "Excel" in selection["skills"] and "Power BI" in selection["skills"]
    assert "Python" in selection["coverage"]["demonstrated"]  # respaldado por el proyecto
    profile = {**PROFILE, "projects": []}
    without = cv_build.select(job, profile)
    assert "Python" not in without["skills"] and "Python" in without["coverage"]["missing"]


def test_coverage_separates_demonstrated_from_listed_only(job):
    profile = {**PROFILE, "experience": [{**PROFILE["experience"][0], "bullets": ["Controles en Excel"]}],
               "projects": [], "tools_declared_in_db": {"Power BI": "basic"}}
    coverage = cv_build.select(job, profile)["coverage"]
    assert "Excel" in coverage["demonstrated"]
    assert "Power BI" in coverage["listed_only"]


def test_missing_contact_warns_and_language_is_detected(job):
    assert cv_build.select(job, {**PROFILE, "contact": {}})["warnings"]
    assert cv_build.select(job)["warnings"] == []
    assert cv_build.detect_language("We are looking for an analyst with experience in the supply chain and our team to grow") == "en"
    assert cv_build.detect_language("Buscamos un analista con experiencia en la cadena de suministro") == "es"


def test_docx_is_valid_single_column_and_never_overwritten(job):
    first = cv_build.build(job, ["docx"])
    second = cv_build.build(job, ["docx"])
    assert first["files"][0]["name"] != second["files"][0]["name"]
    path = cv_build.resolve_file(first["files"][0]["path"])
    with zipfile.ZipFile(path) as archive:
        document = archive.read("word/document.xml")
        assert b"<w:tbl>" not in document and b"<w:drawing" not in document  # sin tablas ni imágenes
    tree = ElementTree.fromstring(document)  # XML bien formado, incluso con «&» en el nombre
    text = "".join(node.text or "" for node in tree.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"))
    assert "Ana Pérez & Co" in text and "Dashboard en Power BI de ventas" in text and "Habilidades" in text
    manifest = json.loads(next(path.parent.glob("*.manifest.json")).read_text(encoding="utf-8"))
    assert manifest["template"] == cv_build.TEMPLATE and manifest["included_ids"] and manifest["profile_sha256"]


def test_native_pdf_respects_page_budget_and_has_extractable_text(job):
    result = cv_build.build(job, ["docx", "pdf"])
    assert [f["format"] for f in result["files"]] == ["docx", "pdf"]
    check = result["check"]
    assert check["pages"] is not None and check["pages"] <= result["selection"]["pages_budget"] and check["within_budget"] is True
    assert check["text_extractable"] is True
    pdf = cv_build.resolve_file(result["files"][1]["path"])
    assert pdf.read_bytes().startswith(b"%PDF")
    if shutil.which("pdftotext"):  # verificación independiente cuando hay poppler
        import subprocess

        text = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
        assert "Ana" in text and "Power BI" in text


def test_pdf_falls_back_to_helvetica_when_no_truetype_font_is_found(job, monkeypatch):
    monkeypatch.setattr(cv_pdf, "find_fonts", lambda: None)
    result = cv_build.build(job, ["pdf"])
    assert result["files"][-1]["format"] == "pdf" and result["check"]["pages"] >= 1
    assert cv_pdf._latin1("a • b – “c” ñ → ✓") == 'a - b - "c" ñ -> ?'


def test_generated_files_can_only_be_served_from_the_cvs_folder(job, tmp_path):
    built = cv_build.build(job, ["docx"])
    assert cv_build.resolve_file(built["files"][0]["path"]) is not None
    (tmp_path / "secrets.docx").write_bytes(b"x")
    assert cv_build.resolve_file("../secrets.docx") is None
    assert cv_build.resolve_file("../cv_master.json") is None
    assert cv_build.resolve_file("nope/none.docx") is None


def test_contact_can_be_edited_and_tools_are_registered(job, tmp_path):
    cv_edit.update_cv("contact", "update", {"email": "nueva@example.com"})
    assert json.loads((tmp_path / "cv_master.json").read_text(encoding="utf-8"))["contact"]["email"] == "nueva@example.com"
    with pytest.raises(ValueError, match="email"):
        cv_edit.update_cv("contact", "update", {"email": "no-es-correo"})
    with pytest.raises(ValueError, match="contact admite"):
        cv_edit.update_cv("contact", "update", {"fax": "1"})
    assert not tools.REGISTRY["preview_cv"].write
    assert tools.REGISTRY["build_cv"].write and tools.REGISTRY["build_cv"].chat


def test_placeholders_in_the_real_cv_are_reported_before_sending(job):
    profile = {**PROFILE, "experience": [{**PROFILE["experience"][0], "company": "Perfumería (nombre no indicado)"}],
               "languages": [{"name": "Inglés", "level": "(no declarado)"}]}
    warnings = cv_build.select(job, profile)["warnings"]
    assert len(warnings) == 1 and "nombre no indicado" in warnings[0] and "no declarado" in warnings[0]


def test_api_preview_build_and_download(job):
    from fastapi.testclient import TestClient

    from radar.api import app

    client = TestClient(app)
    preview = client.get("/api/cv/build/preview", params={"job_id": job})
    assert preview.status_code == 200 and preview.json()["coverage"]["demonstrated"]
    assert client.get("/api/cv/build/preview", params={"job_id": "no-existe"}).status_code == 404
    built = client.post("/api/cv/build", json={"job_id": job, "formats": ["docx"]})
    assert built.status_code == 200
    path = built.json()["files"][0]["path"]
    download = client.get(f"/api/cv/files/{path}")
    assert download.status_code == 200 and download.content[:2] == b"PK"  # un DOCX es un zip
    assert "attachment" in download.headers["content-disposition"]
    assert client.get("/api/cv/files/x/..%2F..%2Fcv_master.json").status_code == 404
    assert client.get("/api/cv/files/2026-01-01/secreto.txt").status_code == 404
    assert client.post("/api/cv/build", json={"job_id": job, "formats": ["odt"]}).status_code == 400
