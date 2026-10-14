"""Documento del CV por oferta: la selección determinista más tus operaciones, con historial, sugerencias y renderizado.

El documento no copia el CV: guarda **operaciones** (quitar, volver a incluir, mover, editar una línea) que se aplican sobre
la selección que ``cv_build`` calcula desde ``cv_master.json``. Así cada línea sigue rastreándose a un hecho real, deshacer
es sacar la última operación y nada se pierde. El agente no modifica el documento: **propone** operaciones que tú aceptas, y toda
reformulación pasa antes por la protección contra datos inventados (``cv_facts``). Ver ``docs/design-cv-studio.md``.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Any

from radar import cv_build, cv_facts, cv_render, cv_targets
from radar.db.database import connection

MAX_OPS = 400
MAX_TEXT = 700
MAX_PROPOSED_OPS = 25
OP_NAMES = {"omit", "include", "move", "edit", "option"}
OPTION_NAMES = {"template", "photo", "pages"}
_CACHE: OrderedDict[str, cv_render.Rendered] = OrderedDict()
CACHE_SIZE = 24


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# --- almacenamiento ------------------------------------------------------------------------------


def get_document(job_id: str) -> dict[str, Any]:
    """El documento de la oferta (se crea vacío la primera vez). Falla si la oferta no existe."""
    if cv_targets._job_context(job_id) is None:
        raise ValueError(f"Oferta no encontrada: {job_id}")
    with connection() as conn:
        row = conn.execute("SELECT id, template, photo, pages, ops, redo, updated_at FROM cv_documents WHERE job_id=%s", (job_id,)).fetchone()
        if row is None:
            conn.execute("INSERT INTO cv_documents(job_id, template, photo) VALUES (%s, 'ats', 0)", (job_id,))
            row = conn.execute("SELECT id, template, photo, pages, ops, redo, updated_at FROM cv_documents WHERE job_id=%s", (job_id,)).fetchone()
    return {"id": row[0], "job_id": job_id, "template": row[1], "photo": bool(row[2]), "pages": row[3],
            "ops": json.loads(row[4]), "redo": json.loads(row[5]), "updated_at": row[6]}


def _save(job_id: str, **fields: Any) -> None:
    columns = {"template": "template", "photo": "photo", "pages": "pages", "ops": "ops", "redo": "redo"}
    sets, values = [], []
    for key, value in fields.items():
        sets.append(f"{columns[key]}=%s")
        values.append(json.dumps(value) if key in {"ops", "redo"} else (int(value) if key == "photo" else value))
    with connection() as conn:
        conn.execute(f"UPDATE cv_documents SET {', '.join(sets)}, updated_at=now() WHERE job_id=%s", (*values, job_id))


# --- operaciones sobre la selección ---------------------------------------------------------------


def _locate(selection: dict[str, Any], item_id: str) -> tuple[list[dict[str, Any]], dict[str, Any], str] | None:
    """(lista contenedora, elemento, clase) de una línea incluida en el documento."""
    for role in selection["experience"]:
        if role["id"] == item_id:
            return selection["experience"], role, "role"
        for bullet in role["bullets"]:
            if bullet["id"] == item_id:
                return role["bullets"], bullet, "bullet"
    for project in selection["projects"]:
        if project["id"] == item_id:
            return selection["projects"], project, "project"
        for bullet in project["bullets"]:
            if bullet["id"] == item_id:
                return project["bullets"], bullet, "bullet"
    for key, kind in (("certifications", "cert"), ("education", "edu")):
        for item in selection[key]:
            if item["id"] == item_id:
                return selection[key], item, kind
    return None


def normalize_op(raw: dict[str, Any]) -> dict[str, Any]:
    """Valida la forma de una operación y devuelve solo los campos permitidos."""
    if not isinstance(raw, dict) or raw.get("op") not in OP_NAMES:
        raise ValueError(f"Operación inválida; permitidas: {', '.join(sorted(OP_NAMES))}")
    op = raw["op"]
    if op == "option":
        if raw.get("name") not in OPTION_NAMES:
            raise ValueError(f"option.name debe ser uno de: {', '.join(sorted(OPTION_NAMES))}")
        return {"op": op, "name": raw["name"], "value": raw.get("value")}
    item_id = raw.get("id")
    if not isinstance(item_id, str) or not item_id or len(item_id) > 80:
        raise ValueError("Falta el id de la línea")
    if op in {"omit", "include"}:
        return {"op": op, "id": item_id}
    if op == "move":
        to = raw.get("to")
        if not isinstance(to, int) or isinstance(to, bool) or not 0 <= to <= 50:
            raise ValueError("move.to debe ser un entero entre 0 y 50")
        return {"op": op, "id": item_id, "to": to}
    text = raw.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
        raise ValueError(f"edit.text debe tener entre 1 y {MAX_TEXT} caracteres")
    field = raw.get("field", "text")
    if field not in {"text", "title", "detail"}:
        raise ValueError("edit.field debe ser text, title o detail")
    return {"op": op, "id": item_id, "text": " ".join(text.split()), "field": field}


def apply_ops(selection: dict[str, Any], ops: list[dict[str, Any]], wanted: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Aplica las operaciones sobre una copia. Devuelve (selección final, operaciones que ya no aplican)."""
    result = copy.deepcopy(selection)
    stale: list[dict[str, Any]] = []
    result["edits"] = {}
    for op in ops:
        kind = op.get("op")
        if kind == "omit":
            found = _locate(result, op["id"])
            if found is None:
                stale.append(op)
                continue
            container, item, what = found
            owner = next((r["id"] for r in [*result["experience"], *result["projects"]] if what == "bullet" and item in r["bullets"]), None)
            container.remove(item)
            section = {"role": "experience", "bullet": "experience", "project": "projects", "cert": "certifications", "edu": "education"}[what]
            result["omitted"].append({"id": item["id"], "section": section, "text": item.get("text") or item.get("title") or "",
                                      "reason": "Quitada por ti" if op.get("by") != "agent" else "Quitada por una sugerencia que aceptaste",
                                      "owner": owner, "item": item})
        elif kind == "include":
            entry = next((o for o in result["omitted"] if o["id"] == op["id"]), None)
            if entry is None or not entry.get("item"):
                stale.append(op)
                continue
            item, section = entry["item"], entry["section"]
            if entry.get("owner") is not None and "bullets" not in item:  # una viñeta vuelve a su cargo o proyecto
                parent = next((r for r in [*result["experience"], *result["projects"]] if r["id"] == entry["owner"]), None)
                if parent is None:
                    stale.append(op)
                    continue
                parent["bullets"].append(item)
            else:
                result[section].append(item)
            result["omitted"].remove(entry)
        elif kind == "move":
            found = _locate(result, op["id"])
            if found is None:
                stale.append(op)
                continue
            container, item, _ = found
            container.remove(item)
            container.insert(min(op["to"], len(container)), item)
        elif kind == "edit":
            _apply_edit(result, op, stale)
    result["coverage"] = cv_build.coverage(result, wanted)
    result["warnings"] = cv_build._warnings(result, bool(result["header"]["contact"]))
    return result, stale


def _apply_edit(result: dict[str, Any], op: dict[str, Any], stale: list[dict[str, Any]]) -> None:
    item_id, text, by = op["id"], op["text"], op.get("by", "user")
    if item_id == "summary":
        result["edits"][item_id] = {"from": result["summary"], "by": by}
        result["summary"] = text
        return
    if item_id == "headline":
        result["edits"][item_id] = {"from": result["header"]["headline"], "by": by}
        result["header"]["headline"] = text
        return
    found = _locate(result, item_id)
    if found is None:
        stale.append(op)
        return
    _, item, what = found
    field = op.get("field") or ("text" if what == "bullet" else "title")
    if field not in item and not (field == "text" and what == "bullet"):
        field = "title" if "title" in item else "text"
    result["edits"][item_id] = {"from": item.get(field), "by": by, "field": field}
    item[field] = text
    item["edited"] = by


# --- textos permitidos para la protección contra datos inventados -----------------------------------


def allowed_texts(profile: dict[str, Any]) -> dict[str, str]:
    """Para cada línea, el texto del que una reformulación puede tomar hechos: su cargo (o proyecto) y nada más;
    para el perfil y el titular, todo el CV maestro."""
    allowed: dict[str, str] = {}
    whole = cv_facts.whole_profile_text(profile)
    allowed["summary"] = allowed["headline"] = whole
    for role in profile.get("experience", []):
        owner = f"{role.get('role')}|{role.get('company')}"
        context = " ".join([role.get("role") or "", role.get("company") or "", role.get("location") or "",
                            *role.get("bullets", []), *role.get("skills", [])])
        allowed[cv_build._item_id("role", owner, "")] = context
        for bullet in role.get("bullets", []):
            allowed[cv_build._item_id("exp", owner, bullet)] = context
    for project in profile.get("projects", []):
        name = project.get("name") or ""
        context = " ".join([name, project.get("description") or "", *project.get("skills", [])])
        allowed[cv_build._item_id("proj", "proyecto", name)] = context
        allowed[cv_build._item_id("projd", name, project.get("description") or "")] = context
    for cert in profile.get("certifications", []):
        allowed[cv_build._item_id("cert", "certificado", cert.get("name") or "")] = f"{cert.get('name') or ''} {cert.get('issuer') or ''}"
    for study in profile.get("education", []):
        key = cv_build._item_id("edu", "formacion", f"{study.get('program')}|{study.get('institution')}")
        allowed[key] = " ".join(str(v) for v in study.values() if isinstance(v, str))
    return allowed


# --- estado, renderizado y edición ----------------------------------------------------------------


def _photo_for(doc: dict[str, Any]):
    return cv_targets.photo_path() if doc["photo"] and cv_render.TEMPLATES[doc["template"]]["photo"] else None


def _final(doc: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    selection, wanted = cv_build.select_full(doc["job_id"])
    final, stale = apply_ops(selection, doc["ops"], wanted)
    if doc["pages"]:
        final["pages_budget"] = doc["pages"]
    for role in final["experience"]:
        for bullet in role["bullets"]:
            bullet["trace"] = f"Experiencia › {role['title']}"
    for project in final["projects"]:
        for bullet in project["bullets"]:
            bullet["trace"] = f"Proyectos › {project['title']}"
    final["template"] = doc["template"]
    return final, stale


def _render(final: dict[str, Any], doc: dict[str, Any]) -> cv_render.Rendered:
    photo = _photo_for(doc)
    mtime = photo.stat().st_mtime_ns if photo else 0
    key = hashlib.sha1(json.dumps([final, doc["template"], bool(photo), mtime], sort_keys=True, default=str).encode()).hexdigest()
    cached = _CACHE.get(key)
    if cached is not None:
        _CACHE.move_to_end(key)
        return cached
    rendered = cv_render.render(final, doc["template"], photo)
    _CACHE[key] = rendered
    while len(_CACHE) > CACHE_SIZE:
        _CACHE.popitem(last=False)
    return rendered


def state(job_id: str) -> dict[str, Any]:
    """Todo lo que necesita el estudio para una oferta: líneas, omitidas, vista previa (cajas), sugerencias y opciones."""
    doc = get_document(job_id)
    final, stale = _final(doc)
    rendered = _render(final, doc)
    warnings = [*final["warnings"], *rendered.warnings]
    over = rendered.pages > final["pages_budget"]
    if over:
        warnings.append(f"El CV ocupa {rendered.pages} páginas y el presupuesto para esta oferta es {final['pages_budget']}: quita líneas o cambia de plantilla.")
    return {
        "job_id": job_id, "selection": final, "stale_ops": stale,
        "document": {"template": doc["template"], "photo": doc["photo"], "pages_budget": final["pages_budget"], "ops": len(doc["ops"]),
                     "can_undo": bool(doc["ops"]), "can_redo": bool(doc["redo"]), "updated_at": doc["updated_at"]},
        "render": {"pages": rendered.pages, "boxes": rendered.boxes, "over_budget": over, "page_mm": [cv_render.PAGE_W, cv_render.PAGE_H]},
        "warnings": warnings, "suggestions": list_suggestions(job_id),
        "photo_available": cv_targets.photo_path() is not None,
        "templates": {k: v["label"] for k, v in cv_render.TEMPLATES.items()},
    }


def pdf_bytes(job_id: str) -> tuple[bytes, int]:
    doc = get_document(job_id)
    final, _ = _final(doc)
    rendered = _render(final, doc)
    return rendered.pdf, rendered.pages


def page_image(job_id: str, page: int, scale: float = 1.4) -> bytes:
    pdf, _ = pdf_bytes(job_id)
    return cv_render.page_png(pdf, page, min(max(scale, 0.5), 3.0))


def add_ops(job_id: str, ops: list[dict[str, Any]], by: str = "user") -> dict[str, Any]:
    """Registra operaciones en el documento. Todas se validan y deben aplicar; si alguna falla no se guarda ninguna."""
    if not ops or len(ops) > MAX_PROPOSED_OPS:
        raise ValueError(f"Envía entre 1 y {MAX_PROPOSED_OPS} operaciones")
    doc = get_document(job_id)
    normalized = [normalize_op(op) for op in ops]
    content = [op for op in normalized if op["op"] != "option"]
    if len(doc["ops"]) + len(content) > MAX_OPS:
        raise ValueError("El documento llegó al máximo de operaciones; reinícialo o acepta menos cambios")
    stamped = [{**op, "by": by, "at": _now()} for op in content]
    selection, wanted = cv_build.select_full(job_id)
    _, stale = apply_ops(selection, [*doc["ops"], *stamped], wanted)
    previous_stale = apply_ops(selection, doc["ops"], wanted)[1]
    if len(stale) > len(previous_stale):
        failing = [op for op in stale if op not in previous_stale]
        raise ValueError(f"Alguna operación no aplica (línea inexistente o ya incluida/omitida): {failing[0]}")
    for op in normalized:
        if op["op"] == "option":
            set_options(job_id, **{op["name"]: op["value"]})
    if stamped:
        _save(job_id, ops=[*doc["ops"], *stamped], redo=[])
    return state(job_id)


def set_options(job_id: str, template: str | None = None, photo: bool | None = None, pages: int | None = None) -> dict[str, Any]:
    get_document(job_id)
    changes: dict[str, Any] = {}
    if template is not None:
        if template not in cv_render.TEMPLATES:
            raise ValueError(f"Plantilla desconocida: {template}")
        changes["template"] = template
    if photo is not None:
        if photo and cv_targets.photo_path() is None:
            raise ValueError("No hay foto de perfil: súbela en Ajustes → Perfil")
        changes["photo"] = bool(photo)
    if pages is not None:
        if pages not in (1, 2, 3):
            raise ValueError("pages debe ser 1, 2 o 3")
        changes["pages"] = pages
    if changes:
        _save(job_id, **changes)
    return state(job_id)


def undo(job_id: str) -> dict[str, Any]:
    doc = get_document(job_id)
    if not doc["ops"]:
        raise ValueError("No hay nada que deshacer")
    last = doc["ops"][-1]
    _save(job_id, ops=doc["ops"][:-1], redo=[*doc["redo"], last])
    return state(job_id)


def redo(job_id: str) -> dict[str, Any]:
    doc = get_document(job_id)
    if not doc["redo"]:
        raise ValueError("No hay nada que rehacer")
    _save(job_id, ops=[*doc["ops"], doc["redo"][-1]], redo=doc["redo"][:-1])
    return state(job_id)


def reset(job_id: str) -> dict[str, Any]:
    get_document(job_id)
    _save(job_id, ops=[], redo=[], template="ats", photo=False, pages=None)
    return state(job_id)


# --- sugerencias del agente ----------------------------------------------------------------------


def propose(job_id: str, ops: list[dict[str, Any]], note: str = "") -> dict[str, Any]:
    """Guarda una sugerencia pendiente. No cambia el documento: la persona la acepta o la rechaza en el estudio."""
    if not ops or len(ops) > MAX_PROPOSED_OPS:
        raise ValueError(f"Propón entre 1 y {MAX_PROPOSED_OPS} operaciones")
    doc = get_document(job_id)
    normalized = [normalize_op(op) for op in ops]
    selection, wanted = cv_build.select_full(job_id)
    current, _ = apply_ops(selection, doc["ops"], wanted)
    probe = [{**op, "by": "agent"} for op in normalized if op["op"] != "option"]
    _, stale_after = apply_ops(selection, [*doc["ops"], *probe], wanted)
    if len(stale_after) > len(apply_ops(selection, doc["ops"], wanted)[1]):
        raise ValueError("Alguna operación no aplica al documento actual; consulta cv_doc_get para ver los ids vigentes")
    allowed = allowed_texts(cv_targets.load_profile() or {})
    flags: list[dict[str, Any]] = []
    for index, op in enumerate(normalized):
        if op["op"] == "edit":
            original = allowed.get(op["id"])
            if original is None:
                raise ValueError(f"No se puede verificar la línea {op['id']}: no existe en tu CV")
            facts = cv_facts.new_facts(op["text"], original)
            if facts:
                flags.append({"op": index, "id": op["id"], "facts": facts})
    sid = None
    with connection() as conn:
        conn.execute("INSERT INTO cv_suggestions(job_id, note, ops, flags) VALUES (%s,%s,%s,%s)",
                     (job_id, (note or "")[:300], json.dumps(normalized), json.dumps(flags)))
        sid = conn.execute("SELECT id FROM cv_suggestions WHERE job_id=%s ORDER BY created_at DESC, rowid DESC LIMIT 1", (job_id,)).fetchone()[0]
    return {"id": sid, "ops": normalized, "flags": flags, "safe": not flags, "visible_in": "Estudio de CV: acéptala o recházala",
            "current_lines": len(current["experience"])}


def list_suggestions(job_id: str, status: str = "pending") -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute("SELECT id, note, ops, flags, status, created_at FROM cv_suggestions WHERE job_id=%s AND status=%s ORDER BY created_at, rowid",
                            (job_id, status)).fetchall()
    return [{"id": r[0], "note": r[1], "ops": json.loads(r[2]), "flags": json.loads(r[3]), "safe": not json.loads(r[3]),
             "status": r[4], "created_at": r[5]} for r in rows]


def _suggestion(job_id: str, suggestion_id: str) -> dict[str, Any]:
    found = next((s for s in list_suggestions(job_id) if s["id"] == suggestion_id), None)
    if found is None:
        raise ValueError("Sugerencia no encontrada o ya resuelta")
    return found


def accept(job_id: str, suggestion_id: str) -> dict[str, Any]:
    suggestion = _suggestion(job_id, suggestion_id)
    if suggestion["flags"]:
        facts = ", ".join(f"{f['kind']} «{f['value']}»" for flag in suggestion["flags"] for f in flag["facts"])
        raise ValueError(f"Contiene datos nuevos no verificados ({facts}). Añádelos a tu CV maestro si son ciertos y pide la sugerencia de nuevo.")
    result = add_ops(job_id, suggestion["ops"], by="agent")
    with connection() as conn:
        conn.execute("UPDATE cv_suggestions SET status='accepted', decided_at=now() WHERE id=%s", (suggestion_id,))
    result["suggestions"] = list_suggestions(job_id)
    return result


def reject(job_id: str, suggestion_id: str) -> dict[str, Any]:
    _suggestion(job_id, suggestion_id)
    with connection() as conn:
        conn.execute("UPDATE cv_suggestions SET status='rejected', decided_at=now() WHERE id=%s", (suggestion_id,))
    return state(job_id)


def accept_safe(job_id: str) -> dict[str, Any]:
    accepted = []
    for suggestion in list_suggestions(job_id):
        if suggestion["safe"]:
            try:
                accept(job_id, suggestion["id"])
                accepted.append(suggestion["id"])
            except ValueError:
                continue
    result = state(job_id)
    result["accepted"] = accepted
    return result
