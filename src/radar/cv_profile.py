"""Confirmed, revision-checked edits to the factual CV shared by every view."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from functools import cache
from typing import Any

from radar import cv_edit


class ProfileConflict(ValueError):
    """The user reviewed an older copy of the factual CV."""


@cache
def lock(path: str) -> threading.RLock:
    return threading.RLock()


def revision() -> str:
    path = cv_edit._path()
    return hashlib.sha256(path.read_bytes() if path.exists() else b"").hexdigest()


def read() -> dict[str, Any]:
    path = cv_edit._path()
    with lock(str(path.resolve())):
        profile = cv_edit._load() if path.exists() else {}
        return {"sections": {key: profile.get(key, []) for key in cv_edit.LIST_SECTIONS},
                "revision": revision()}


def refresh_scores() -> list[str]:
    from radar.db.queries import get_profile
    from radar.db.repository import recompute_scores

    try:
        account = get_profile()
        if account:
            recompute_scores(account["id"])
    except Exception:
        logging.getLogger(__name__).exception("CV saved; score refresh is pending")
        return ["Tu CV está guardado; el recálculo de las ofertas quedó pendiente."]
    return []


def save(sections: dict, expected_revision: str) -> dict[str, Any]:
    """Replace only explicitly edited sections, keeping unrelated fields and an undo snapshot."""
    if not isinstance(sections, dict) or not sections or set(sections) - set(cv_edit.LIST_SECTIONS):
        raise ValueError("Elige una sección de experiencia, estudios, certificados, proyectos o idiomas.")
    if len(json.dumps(sections)) > 160_000:
        raise ValueError("El CV contiene demasiado texto.")
    with lock(str(cv_edit._path().resolve())):
        if expected_revision != revision():
            raise ProfileConflict("Tu CV cambió en otra vista. Recarga los datos antes de guardar.")
        cv = cv_edit._load() if cv_edit._path().exists() else {}
        undo = {key: cv.get(key, []) for key in sections}
        clean = {}
        for section, entries in sections.items():
            if not isinstance(entries, list) or len(entries) > 50 or any(not isinstance(x, dict) for x in entries):
                raise ValueError("Cada sección admite hasta 50 registros.")
            allowed, required, _ = cv_edit.LIST_SECTIONS[section]
            values = []
            for entry in entries:
                # Older CVs can have extra fields; retain those only when the existing record matches.
                known = {key: value for key, value in entry.items() if key in allowed}
                item = cv_edit._clean(section, known)
                if any(not item.get(key) for key in required):
                    raise ValueError("Completa los datos obligatorios o quita el registro vacío.")
                extra = {key: value for key, value in entry.items() if key not in allowed}
                if extra and not any(all(old.get(key) == value for key, value in extra.items()) for old in cv.get(section, [])):
                    raise ValueError("El registro contiene campos no reconocidos.")
                values.append({**extra, **item})
            clean[section] = values
        backup = cv_edit.set_fields(clean)
        result = {**read(), "undo": undo, "backup": backup}
    return {**result, "warnings": refresh_scores()}
