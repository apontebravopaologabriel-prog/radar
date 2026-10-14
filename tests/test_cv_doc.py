import json
from datetime import UTC, datetime

import pytest
from cv_fixtures import DESCRIPTION, PROFILE

from radar import cv_build, cv_doc, cv_facts, cv_render
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


def _ids(state_):
    role = state_["selection"]["experience"][0]
    return role["id"], [b["id"] for b in role["bullets"]]


def test_omit_include_move_and_undo_redo(job):
    first = cv_doc.state(job)
    _, bullets = _ids(first)
    assert first["document"]["ops"] == 0 and not first["document"]["can_undo"]
    after_omit = cv_doc.add_ops(job, [{"op": "omit", "id": bullets[0]}])
    assert _ids(after_omit)[1] == bullets[1:] and after_omit["document"]["can_undo"]
    omitted_ids = {o["id"] for o in after_omit["selection"]["omitted"]}
    assert bullets[0] in omitted_ids
    back = cv_doc.add_ops(job, [{"op": "include", "id": bullets[0]}])
    assert sorted(_ids(back)[1]) == sorted(bullets) and _ids(back)[1][-1] == bullets[0]  # vuelve al final de su cargo
    moved = cv_doc.add_ops(job, [{"op": "move", "id": bullets[0], "to": 0}])
    assert _ids(moved)[1][0] == bullets[0]
    undone = cv_doc.undo(job)
    assert _ids(undone)[1][-1] == bullets[0] and undone["document"]["can_redo"]
    assert _ids(cv_doc.redo(job))[1][0] == bullets[0]
    assert cv_doc.reset(job)["document"]["ops"] == 0


def test_invalid_operations_are_rejected_and_nothing_is_saved(job):
    state_ = cv_doc.state(job)
    _, bullets = _ids(state_)
    with pytest.raises(ValueError):
        cv_doc.add_ops(job, [{"op": "omit", "id": bullets[0]}, {"op": "omit", "id": "exp:inexistente"}])
    assert cv_doc.state(job)["document"]["ops"] == 0  # atómico
    for bad in ({"op": "delete", "id": "x"}, {"op": "move", "id": "x", "to": -1}, {"op": "edit", "id": "x", "text": ""},
                {"op": "option", "name": "evil", "value": 1}, "texto"):
        with pytest.raises(ValueError):
            cv_doc.normalize_op(bad)
    with pytest.raises(ValueError):
        cv_doc.add_ops(job, [])


def test_user_edit_is_marked_and_keeps_the_original(job):
    _, bullets = _ids(cv_doc.state(job))
    edited = cv_doc.add_ops(job, [{"op": "edit", "id": bullets[0], "text": "Dashboard de ventas en Power BI"}])
    bullet = edited["selection"]["experience"][0]["bullets"][0]
    assert bullet["text"] == "Dashboard de ventas en Power BI" and bullet["edited"] == "user"
    assert edited["selection"]["edits"][bullets[0]]["from"] == "Dashboard en Power BI de ventas"
    assert "trace" in bullet and "Experiencia" in bullet["trace"]


def test_options_template_photo_and_pages(job, tmp_path):
    with pytest.raises(ValueError):
        cv_doc.set_options(job, photo=True)  # sin foto no se activa
    (tmp_path / "photo.jpg").write_bytes(_tiny_jpeg())
    out = cv_doc.set_options(job, template="sidebar", photo=True, pages=2)
    assert out["document"]["template"] == "sidebar" and out["document"]["photo"] and out["document"]["pages_budget"] == 2
    with pytest.raises(ValueError):
        cv_doc.set_options(job, template="inexistente")


def _tiny_jpeg() -> bytes:
    import io

    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (300, 400), (120, 130, 140)).save(out, "JPEG")
    return out.getvalue()


def test_render_returns_pdf_pages_and_boxes_for_every_line(job):
    state_ = cv_doc.state(job)
    pdf, pages = cv_doc.pdf_bytes(job)
    assert pdf.startswith(b"%PDF") and pages == state_["render"]["pages"] >= 1
    boxes = {b["id"] for b in state_["render"]["boxes"]}
    role_id, bullets = _ids(state_)
    assert {role_id, *bullets} <= boxes and "name" in boxes
    for box in state_["render"]["boxes"]:
        assert 0 <= box["x"] <= 210 and 0 <= box["y"] <= 297 and box["h"] > 0
    png = cv_doc.page_image(job, 1)
    assert png.startswith(b"\x89PNG")
    with pytest.raises(ValueError):
        cv_doc.page_image(job, 9)


def test_both_templates_render_and_sidebar_uses_the_photo(job, tmp_path):
    (tmp_path / "photo.jpg").write_bytes(_tiny_jpeg())
    sel, _ = cv_build.select_full(job)
    plain = cv_render.render(sel, "sidebar", None)
    with_photo = cv_render.render(sel, "sidebar", tmp_path / "photo.jpg")
    assert plain.pdf.startswith(b"%PDF") and len(with_photo.pdf) > len(plain.pdf)
    assert cv_render.render(sel, "ats").pages >= 1


def test_long_content_flows_to_a_second_page_without_losing_boxes(job):
    sel, _ = cv_build.select_full(job)
    sel["experience"][0]["bullets"] = [{"id": f"exp:{i}", "text": "Línea larga de experiencia " * 6} for i in range(40)]
    for template in ("ats", "sidebar"):
        rendered = cv_render.render(sel, template)
        assert rendered.pages >= 2
        assert {f"exp:{i}" for i in range(40)} <= {b["id"] for b in rendered.boxes}
        assert {b["page"] for b in rendered.boxes} <= set(range(1, rendered.pages + 1)) and max(b["page"] for b in rendered.boxes) >= 2


def test_agent_suggestions_are_not_applied_until_accepted(job):
    _, bullets = _ids(cv_doc.state(job))
    suggestion = cv_doc.propose(job, [{"op": "omit", "id": bullets[2]}], "Menos relevante")
    assert suggestion["safe"] and cv_doc.state(job)["document"]["ops"] == 0
    assert len(cv_doc.state(job)["suggestions"]) == 1
    accepted = cv_doc.accept(job, suggestion["id"])
    assert bullets[2] not in _ids(accepted)[1] and accepted["suggestions"] == []
    other = cv_doc.propose(job, [{"op": "option", "name": "template", "value": "sidebar"}])
    cv_doc.reject(job, other["id"])
    assert cv_doc.state(job)["document"]["template"] == "ats"
    with pytest.raises(ValueError):
        cv_doc.accept(job, other["id"])  # ya resuelta


def test_fact_guard_blocks_invented_numbers_names_and_tools(job):
    _, bullets = _ids(cv_doc.state(job))
    target = bullets[0]  # «Dashboard en Power BI de ventas»
    ok = cv_doc.propose(job, [{"op": "edit", "id": target, "text": "Dashboard de ventas en Power BI"}])
    assert ok["safe"] and ok["flags"] == []
    bad = cv_doc.propose(job, [{"op": "edit", "id": target, "text": "Dashboard en Power BI y Tableau que redujo 40 % los costos en Google"}])
    assert not bad["safe"]
    kinds = {f["kind"] for flag in bad["flags"] for f in flag["facts"]}
    assert {"number", "name", "skill"} <= kinds
    with pytest.raises(ValueError, match="no verificados"):
        cv_doc.accept(job, bad["id"])
    assert cv_doc.state(job)["document"]["ops"] == 0
    result = cv_doc.accept_safe(job)
    assert result["accepted"] == [ok["id"]] and len(result["suggestions"]) == 1  # solo la segura pasa


def test_fact_guard_context_is_the_same_role_not_the_whole_cv(job):
    profile = {**PROFILE, "experience": [
        PROFILE["experience"][0],
        {"role": "Practicante", "company": "Globex", "from": "2022-01", "to": "2022-12", "bullets": ["Premio al mejor practicante 2022"], "skills": []},
    ]}
    allowed = cv_doc.allowed_texts(profile)
    first_bullet = cv_build._item_id("exp", "Auxiliar|JAS", "Dashboard en Power BI de ventas")
    flags = cv_facts.new_facts("Dashboard en Power BI; premio al mejor practicante de Globex", allowed[first_bullet])
    assert flags, "un logro de otro cargo no puede colarse en esta viñeta"
    assert cv_facts.new_facts("Resumen con Power BI y Excel", allowed["summary"]) == []  # el perfil sí puede usar todo el CV


def test_stale_operations_are_reported_when_the_master_changes(job, tmp_path):
    _, bullets = _ids(cv_doc.state(job))
    cv_doc.add_ops(job, [{"op": "omit", "id": bullets[0]}])
    changed = {**PROFILE, "experience": [{**PROFILE["experience"][0], "bullets": ["Otra línea"]}]}
    (tmp_path / "cv_master.json").write_text(json.dumps(changed), encoding="utf-8")
    assert cv_doc.state(job)["stale_ops"], "la operación sobre una línea que ya no existe se informa, no rompe"
