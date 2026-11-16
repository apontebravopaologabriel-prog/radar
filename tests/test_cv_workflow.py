"""Regression coverage for the simplified, local CV workflow and data preservation."""

import io
import json
import zipfile
from xml.sax.saxutils import escape

import pytest
from cv_fixtures import PROFILE
from fastapi.testclient import TestClient

from radar.api import app
from radar.cv import edit as cv_edit
from radar.cv import import_cv as cv_import
from radar.cv import profile as cv_profile

TEXT = """Ana Pérez
Ingeniería Industrial
ana@example.com
+51 999111222
Perfil profesional
Analizo datos y mejoro procesos con evidencia.
Experiencia laboral
Analista | ACME
2023-01 - 2024-12
• Reportes de Excel
Formación académica
Universidad UPC
Estudiante de Ingeniería Industrial
Certificaciones
Curso de SQL | Instituto de Datos 2026-04
Proyectos
Inventarios: Analicé existencias con SQL
• Publiqué un reporte verificable
Idiomas
Inglés: B2
Español nativo
Habilidades
Excel y SQL
"""


def word(text=TEXT):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(zipfile.ZipInfo("word/document.xml"), '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                         + "".join(f"<w:p><w:r><w:t>{escape(line)}</w:t></w:r></w:p>" for line in text.splitlines())
                         + "</w:body></w:document>")
    return output.getvalue()


@pytest.fixture
def existing(tmp_path):
    path = tmp_path / "cv_master.json"
    path.write_text(json.dumps(PROFILE, ensure_ascii=False), encoding="utf-8")
    return path


def test_import_extracts_factual_sections_without_inventing_levels():
    draft = cv_import.preview(word(), "CV.docx", "industrial_engineering")
    assert draft["headline"] == "Ingeniería Industrial"
    assert draft["summary"] == "Analizo datos y mejoro procesos con evidencia."
    assert draft["projects"][0]["name"] == "Inventarios"
    assert "reporte verificable" in draft["projects"][0]["description"]
    assert draft["certifications"][0]["name"] == "Curso de SQL"
    assert draft["languages"] == [{"name": "Inglés", "level": "B2"}, {"name": "Español", "level": "nativo"}]
    assert "SQL" in draft["detected_skills"] and "skills" not in draft
    assert cv_import.original() is None


def test_reimport_reviews_changes_preserves_other_facts_and_original_bytes(existing):
    before = json.loads(existing.read_text(encoding="utf-8"))
    draft = cv_import.preview(word(), "CV.docx", "industrial_engineering")
    changes = cv_import.changes(draft)
    assert existing.read_text(encoding="utf-8") == json.dumps(PROFILE, ensure_ascii=False)
    assert "summary" in changes["diff"]
    done = cv_import.apply({**draft, "base_revision": changes["revision"]})
    assert done["undo"]
    profile = json.loads(existing.read_text(encoding="utf-8"))
    assert before["projects"][0] in profile["projects"]
    assert before["experience"][0] in profile["experience"]
    assert cv_import.original()[0].read_bytes() == word()
    cv_import.apply({**draft, "base_revision": cv_profile.revision()})
    assert json.loads(existing.read_text(encoding="utf-8")) == profile


def test_stale_import_cannot_overwrite_a_new_profile_edit(existing):
    draft = cv_import.preview(word(), "CV.docx", "industrial_engineering")
    cv_edit.update_cv("summary", "update", {"text": "Una actualización más reciente."})
    before = existing.read_bytes()
    with pytest.raises(cv_profile.ProfileConflict):
        cv_import.apply(draft)
    assert existing.read_bytes() == before


def test_undo_import_restores_facts_and_refuses_stale_or_arbitrary_files(existing):
    before = json.loads(existing.read_text(encoding="utf-8"))
    done = cv_import.apply(cv_import.preview(word(), "CV.docx", "industrial_engineering"))
    cv_import.undo_import(done["undo"]["backup"], done["undo"]["revision"])
    assert json.loads(existing.read_text(encoding="utf-8")) == before
    assert cv_import.original() is None
    with pytest.raises(cv_profile.ProfileConflict):
        cv_import.undo_import(done["undo"]["backup"], done["undo"]["revision"])
    with pytest.raises(ValueError):
        cv_import.undo_import("../secrets.json", cv_profile.revision())


def test_history_editor_preserves_other_sections_and_supports_revision_checked_undo(existing):
    initial = cv_profile.read()
    changed = cv_profile.save({"projects": [{"name": "Proyecto real", "description": "Construí un reporte con SQL"}]}, initial["revision"])
    assert json.loads(existing.read_text(encoding="utf-8"))["experience"] == PROFILE["experience"]
    with pytest.raises(cv_profile.ProfileConflict):
        cv_profile.save({"projects": []}, initial["revision"])
    restored = cv_profile.save(changed["undo"], changed["revision"])
    assert restored["sections"] == initial["sections"]
    assert json.loads(existing.read_text(encoding="utf-8"))["contact"] == PROFILE["contact"]


def test_invalid_history_edit_is_atomic(existing):
    before = existing.read_bytes()
    for sections in ({"projects": [{"name": "Nuevo"}], "experience": [{"role": "Sin empresa"}]}, {"secrets": []}, {"projects": "bad"}):
        with pytest.raises(ValueError):
            cv_profile.save(sections, cv_profile.revision())
        assert existing.read_bytes() == before


def test_factual_editor_http_and_original_are_available_without_agent(existing):
    api = TestClient(app)
    assert api.get("/api/me/cv/original").status_code == 404
    draft = api.post("/api/me/cv/preview", data={"career_id": "industrial_engineering"}, files={"file": ("CV.docx", word())}).json()
    assert api.get("/api/me/cv/original").status_code == 404
    assert api.post("/api/me/setup/confirm", json=draft).status_code == 200
    original = api.get("/api/me/cv/original")
    assert original.content == word() and original.headers["cache-control"] == "no-store"
    current = api.get("/api/me/cv").json()
    result = api.patch("/api/me/cv", json={"revision": current["revision"], "sections": {"projects": [{"name": "Nuevo", "skills": ["SQL"]}]}})
    assert result.status_code == 200
    assert api.patch("/api/me/cv", json={"revision": current["revision"], "sections": {"projects": []}}).status_code == 409
    assert api.get("/api/me/cv/original").content == word()
