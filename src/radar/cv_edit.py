"""Edición del CV real (`cv_master.json`) por texto: la misma fuente que lee la vista de CVs.

Cada cambio valida el formato de su sección, conserva las claves que no toca, guarda una copia
previa (últimas 5) y escribe de forma atómica. Solo se edita lo que la persona dicta; nunca se inventa.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from radar.cv_targets import data_dir
from radar.normalize import normalize_text

BACKUPS_KEPT = 5
DATE = re.compile(r"^\d{4}(-\d{2})?$")
OPEN_END = {"actual", "presente", "present", "en curso"}

# sección -> (campos permitidos, obligatorios al añadir, campos que identifican un ítem)
LIST_SECTIONS: dict[str, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = {
    "certifications": (("name", "issuer", "date"), ("name",), ("name",)),
    "experience": (("role", "company", "location", "from", "to", "bullets"), ("role", "company"), ("role", "company")),
    "education": (("institution", "program", "from", "to", "status", "skills"), ("institution", "program"), ("program", "institution")),
    "languages": (("name", "level", "evidence"), ("name",), ("name",)),
}
TEXT_SECTIONS = {"summary", "headline"}
SECTIONS = (*LIST_SECTIONS, "gaps", *TEXT_SECTIONS)
ACTIONS = ("add", "update", "remove")


def _path():
    return data_dir() / "cv_master.json"


def _load() -> dict[str, Any]:
    try:
        cv = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("No hay CV cargado (cv_master.json) o está dañado; créalo antes de editarlo por texto.") from exc
    if not isinstance(cv, dict):
        raise ValueError("cv_master.json no tiene el formato esperado")
    return cv


def _clean(section: str, item: dict[str, Any]) -> dict[str, Any]:
    allowed = LIST_SECTIONS[section][0]
    extra = set(item) - set(allowed)
    if extra:
        raise ValueError(f"Campos no permitidos en {section}: {', '.join(sorted(extra))}. Permitidos: {', '.join(allowed)}")
    clean: dict[str, Any] = {}
    for key, value in item.items():
        if key in ("bullets", "skills"):
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value) or len(value) > 12:
                raise ValueError(f"{key} debe ser una lista de hasta 12 textos")
            clean[key] = [" ".join(v.split())[:300] for v in value if v.strip()]
            continue
        if not isinstance(value, str) or len(value) > 300:
            raise ValueError(f"{key} debe ser un texto de hasta 300 caracteres")
        value = " ".join(value.split())
        if key in ("date", "from") and value and not DATE.match(value):
            raise ValueError(f"{key} debe tener formato AAAA-MM (o AAAA)")
        if key == "to" and value and not DATE.match(value) and normalize_text(value) not in OPEN_END:
            raise ValueError("to debe ser AAAA-MM, AAAA o «actual»")
        clean[key] = value
    return clean


def _find(section: str, items: list[dict[str, Any]], match: str) -> int:
    needle = normalize_text(match)
    keys = LIST_SECTIONS[section][2]
    hits = [i for i, it in enumerate(items) if any(needle in normalize_text(str(it.get(k, ""))) for k in keys)]
    if len(hits) != 1:
        options = [" · ".join(str(it.get(k, "")) for k in keys) for it in items]
        raise ValueError(f"«{match}» coincide con {len(hits)} ítems de {section}; sé más específico. Hay: {options}")
    return hits[0]


def _backup_and_write(cv: dict[str, Any]) -> str:
    path = _path()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    backup = path.with_name(f"{path.name}.bak-{stamp}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    for old in sorted(path.parent.glob(f"{path.name}.bak-*"))[:-BACKUPS_KEPT]:
        old.unlink()
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(cv, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return backup.name


def update_cv(section: str, action: str, item: dict[str, Any] | None = None, match: str | None = None) -> dict[str, Any]:
    if section not in SECTIONS:
        raise ValueError(f"section debe ser una de: {', '.join(SECTIONS)}. Las skills y herramientas se cambian con update_profile.")
    if action not in ACTIONS and section not in TEXT_SECTIONS:
        raise ValueError(f"action debe ser una de: {', '.join(ACTIONS)}")
    item = item or {}
    cv = _load()
    if section in TEXT_SECTIONS:  # summary / headline: action «update» con item={"text": ...}
        text = " ".join(str(item.get("text", "")).split())
        if not text or len(text) > 600:
            raise ValueError("item.text debe tener entre 1 y 600 caracteres")
        cv[section] = text
        result: Any = text
    elif section == "gaps":
        gaps = list(cv.get("gaps_of_evidence") or [])
        if action == "add":
            text = " ".join(str(item.get("text", "")).split())[:300]
            if not text:
                raise ValueError("item.text es obligatorio")
            gaps.append(text)
        else:
            needle = normalize_text(match or str(item.get("text", "")))
            hits = [i for i, g in enumerate(gaps) if needle and needle in normalize_text(g)]
            if len(hits) != 1:
                raise ValueError(f"«{needle}» coincide con {len(hits)} brechas; sé más específico. Hay: {gaps}")
            if action == "remove":
                gaps.pop(hits[0])
            else:
                gaps[hits[0]] = " ".join(str(item.get("text", "")).split())[:300]
        cv["gaps_of_evidence"] = gaps
        result = gaps
    else:
        items = [dict(x) for x in cv.get(section) or []]
        required = LIST_SECTIONS[section][1]
        if action == "add":
            new = _clean(section, item)
            missing = [k for k in required if not new.get(k)]
            if missing:
                raise ValueError(f"Faltan datos para añadir a {section}: {', '.join(missing)}. Pregúntaselos a la persona.")
            probe = " ".join(str(new.get(k, "")) for k in LIST_SECTIONS[section][2])
            if any(normalize_text(probe) == normalize_text(" ".join(str(it.get(k, "")) for k in LIST_SECTIONS[section][2])) for it in items):
                raise ValueError("Ese ítem ya existe; usa action=update para modificarlo.")
            items.append(new)
        else:
            if not match:
                raise ValueError("match es obligatorio para update y remove")
            index = _find(section, items, match)
            if action == "remove":
                items.pop(index)
            else:
                items[index] = {**items[index], **_clean(section, item)}
        cv[section] = items
        result = items
    backup = _backup_and_write(cv)
    hint = ("Si esto aporta evidencia a una brecha, ofrece actualizarla con section=gaps."
            if section in ("certifications", "experience", "education") else None)
    return {"section": section, "action": action if section not in TEXT_SECTIONS else "set", "now": result,
            "backup": backup, "next": hint}
