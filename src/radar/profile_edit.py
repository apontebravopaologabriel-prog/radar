"""Perfil editable en un solo lugar: la interfaz de Ajustes y el agente usan estas mismas funciones.

Los datos viven en dos almacenes con responsabilidades distintas y aquí se reparten sin que quien edita lo note:

- ``cv_master.json`` (identidad y trayectoria): nombre, titular, resumen, distrito de casa y contacto.
- SQLite ``user_profile`` (lo que usa el puntaje): áreas objetivo, lugares, modalidades, formación y skills.

``patch`` recibe **solo lo que cambia** (nunca borra por omisión), valida todo antes de escribir, guarda copia
del CV, revierte el archivo si falla la base y devuelve el antes/después con un ``undo`` listo para reenviar.
"""

from __future__ import annotations

import json
from typing import Any

from radar import cv_edit, cv_targets
from radar.db.database import connection
from radar.db.queries import get_profile
from radar.db.repository import save_profile
from radar.geolocation import infer_location
from radar.normalize import normalize_text

SCALARS = {"name": 80, "headline": 200, "summary": 600, "home_district": 60, "education": 300}
LIST_FIELDS = ("areas", "locations")
ALLOWED = {*SCALARS, "contact", *LIST_FIELDS, *(f"{k}_{s}" for k in LIST_FIELDS for s in ("add", "remove")),
           "work_modes", "skills"}
LEVELS = {"none", "basic", "intermediate", "advanced"}
REMOVE = "remove"
MAX_ITEMS, MAX_ITEM_LEN = 30, 80
# Los valores canónicos son los que guardan las ofertas (y con los que compara el puntaje): onsite, hybrid, remote.
_MODES = {"presencial": "onsite", "onsite": "onsite", "hybrid": "hybrid", "hibrido": "hybrid",
          "remote": "remote", "remoto": "remote"}
_CV_KEYS = ("name", "headline", "summary", "home_district", "contact")
_DB_KEYS = ("name", "education", "areas", "locations", "work_modes", "skills")
_LABEL = {"name": "Nombre", "headline": "Titular", "summary": "Resumen", "home_district": "Distrito",
          "contact": "Contacto", "education": "Formación", "areas": "Áreas", "locations": "Lugares",
          "work_modes": "Modalidades", "skills": "Skills"}


def current() -> dict[str, Any]:
    """Vista unificada del perfil (lo que se muestra y sobre lo que se calcula el antes/después)."""
    account = get_profile() or {}
    cv = cv_targets.load_profile() or {}
    return {
        "name": cv.get("name") or account.get("name") or "",
        "headline": cv.get("headline") or "",
        "summary": cv.get("summary") or "",
        "home_district": cv.get("home_district") or "",
        "contact": dict(cv.get("contact") or {}),
        "education": account.get("education") or "",
        "areas": list(account.get("target_roles") or []),
        "locations": list(account.get("locations") or []),
        "work_modes": list(account.get("work_modes") or []),
        "skills": dict(account.get("skills") or {}),
        "has_photo": bool(cv.get("has_photo")),
    }


def completeness(profile: dict[str, Any]) -> dict[str, Any]:
    """Qué le falta al perfil y por qué importa (sobre todo para poder enviar un CV)."""
    checks = [
        ("name", "Nombre", bool(profile["name"]), "Sale en el CV y en tu perfil."),
        ("headline", "Titular", bool(profile["headline"]), "La línea bajo tu nombre en el CV."),
        ("summary", "Resumen", bool(profile["summary"]), "El párrafo «Perfil» de tu CV."),
        ("home_district", "Distrito", bool(profile["home_district"]), "Radar calcula la distancia a cada oferta desde aquí."),
        ("contact", "Contacto", bool(profile["contact"].get("email") or profile["contact"].get("phone")),
         "Sin correo o teléfono el CV no sirve para enviar."),
        ("areas", "Áreas objetivo", bool(profile["areas"]), "Definen qué ofertas encajan contigo."),
        ("locations", "Lugares", bool(profile["locations"]), "Dónde buscas trabajo."),
        ("skills", "Skills", bool(profile["skills"]), "Alimentan el encaje y el plan de cierre."),
    ]
    missing = [{"key": key, "label": label, "why": why} for key, label, ok, why in checks if not ok]
    return {"percent": round(100 * (len(checks) - len(missing)) / len(checks)), "missing": missing}


def get_full() -> dict[str, Any]:
    profile = current()
    return {**profile, "completeness": completeness(profile)}


def _text(value: Any, key: str) -> str:
    text = " ".join(str(value).split())
    if len(text) > SCALARS[key]:
        raise ValueError(f"{_LABEL[key]} admite hasta {SCALARS[key]} caracteres")
    if key == "name" and not text:
        raise ValueError("El nombre no puede quedar vacío")
    return text


def _clean_list(items: Any, label: str) -> list[str]:
    if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
        raise ValueError(f"{label} debe ser una lista de textos")
    out: list[str] = []
    for item in items:
        text = " ".join(item.split())
        if not text:
            continue
        if len(text) > MAX_ITEM_LEN:
            raise ValueError(f"Cada elemento de {label} admite hasta {MAX_ITEM_LEN} caracteres")
        if normalize_text(text) not in {normalize_text(x) for x in out}:
            out.append(text)
    if len(out) > MAX_ITEMS:
        raise ValueError(f"{label} admite hasta {MAX_ITEMS} elementos")
    return out


def _merge_list(base: list[str], fields: dict[str, Any], key: str) -> list[str]:
    label = _LABEL[key]
    if fields.get(key) is not None:
        base = _clean_list(fields[key], label)
    drop = {normalize_text(x) for x in _clean_list(fields.get(f"{key}_remove") or [], label)}
    base = [x for x in base if normalize_text(x) not in drop]
    for item in _clean_list(fields.get(f"{key}_add") or [], label):
        if normalize_text(item) not in {normalize_text(x) for x in base}:
            base.append(item)
    if len(base) > MAX_ITEMS:
        raise ValueError(f"{label} admite hasta {MAX_ITEMS} elementos")
    return base


def _merge_contact(base: dict[str, str], value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("contact debe ser un objeto {email, phone, linkedin, location}")  # noqa: TRY004 - se captura ValueError
    extra = set(value) - set(cv_edit.CONTACT_FIELDS)
    if extra:
        raise ValueError(f"contact admite: {', '.join(cv_edit.CONTACT_FIELDS)}")
    merged = dict(base)
    for key, raw in value.items():
        text = " ".join(str(raw or "").split())
        if len(text) > 120:
            raise ValueError(f"{key} admite hasta 120 caracteres")
        if key == "email" and text and "@" not in text.strip("@"):
            raise ValueError("El correo no parece válido")
        if text:
            merged[key] = text
        else:
            merged.pop(key, None)
    return merged


def _canonical_skill(name: str) -> str | None:
    """Nombre del catálogo para una skill escrita a mano, o ``None`` si Radar no la conoce."""
    with connection() as conn:
        row = conn.execute(
            "SELECT name FROM skills WHERE normalized_name=%s OR lower(name)=lower(%s)",
            (normalize_text(name).replace(" ", "-"), name),
        ).fetchone()
    return row[0] if row else None


def _merge_skills(base: dict[str, str], value: Any) -> tuple[dict[str, str], list[str]]:
    if not isinstance(value, dict):
        raise ValueError("skills debe ser un objeto {skill: nivel}")  # noqa: TRY004 - se captura ValueError
    merged, warnings, unknown = dict(base), [], []
    for raw, level in value.items():
        canonical = _canonical_skill(str(raw))
        if canonical is None:
            unknown.append(str(raw))
            continue
        if level == REMOVE:
            if merged.pop(canonical, None) is None:
                warnings.append(f"{canonical} no estaba en tu perfil")
        elif level in LEVELS:
            merged[canonical] = level
        else:
            raise ValueError(f"Nivel inválido para {canonical}: usa {', '.join(sorted(LEVELS))} o «{REMOVE}»")
    if unknown:
        raise ValueError("Skills que Radar no reconoce (solo hay las del catálogo de la carrera activa): "
                         + ", ".join(unknown))
    return merged, warnings


def _modes(value: Any) -> list[str]:
    items = _clean_list(value, "Modalidades")
    bad = [i for i in items if normalize_text(i) not in _MODES]
    if bad:
        raise ValueError(f"Modalidad no reconocida: {', '.join(bad)}. Usa presencial (onsite), híbrido (hybrid) o remoto (remote)")
    return list(dict.fromkeys(_MODES[normalize_text(i)] for i in items))


def _plan(fields: dict[str, Any], cur: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Valida ``fields`` y devuelve el estado nuevo completo; no escribe nada."""
    unknown = set(fields) - ALLOWED
    if unknown:
        raise ValueError(f"Campos no permitidos: {', '.join(sorted(unknown))}. Permitidos: {', '.join(sorted(ALLOWED))}")
    new = json.loads(json.dumps(cur))
    warnings: list[str] = []
    for key in SCALARS:
        if fields.get(key) is not None:
            new[key] = _text(fields[key], key)
    if fields.get("contact") is not None:
        new["contact"] = _merge_contact(cur["contact"], fields["contact"])
    for key in LIST_FIELDS:
        new[key] = _merge_list(list(cur[key]), fields, key)
    if fields.get("work_modes") is not None:
        new["work_modes"] = _modes(fields["work_modes"])
    if fields.get("skills") is not None:
        new["skills"], warnings = _merge_skills(cur["skills"], fields["skills"])
    district = new["home_district"]
    if district and district != cur["home_district"]:
        place = infer_location(district)
        if place is None or place.precision != "district":
            warnings.append(f"«{district}» no es un distrito que Radar reconozca: no podrá calcular distancias desde ahí.")
    return new, warnings


def _diff(cur: dict[str, Any], new: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Cambios como {campo: {before, after}} y el ``undo`` que los revierte."""
    diff: dict[str, Any] = {}
    undo: dict[str, Any] = {}
    for key in (*SCALARS, "contact", *LIST_FIELDS, "work_modes"):
        if cur[key] == new[key]:
            continue
        diff[key] = {"before": cur[key], "after": new[key]}
        if key == "contact":
            undo[key] = {k: cur[key].get(k, "") for k in {*cur[key], *new[key]}}
        else:
            undo[key] = cur[key]
    changed = {s for s in {*cur["skills"], *new["skills"]} if cur["skills"].get(s) != new["skills"].get(s)}
    if changed:
        diff["skills"] = {"before": {s: cur["skills"].get(s) for s in changed}, "after": {s: new["skills"].get(s) for s in changed}}
        undo["skills"] = {s: cur["skills"].get(s, REMOVE) for s in changed}
    return diff, undo


def preview(fields: dict[str, Any]) -> list[str]:
    """Líneas «Campo: antes → después» para mostrar en la tarjeta de confirmación (no escribe)."""
    try:
        cur = current()
        new, _ = _plan(fields, cur)
        diff, _ = _diff(cur, new)
    except ValueError as exc:
        return [f"No se puede aplicar: {exc}"]

    def show(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else (str(value) or "—")

    lines = [f"{_LABEL[key]}: {show(change['before'])} → {show(change['after'])}" for key, change in diff.items()]
    return lines or ["Sin cambios respecto a tu perfil actual."]


def patch(fields: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    """Aplica un cambio parcial al perfil. Solo se tocan los campos indicados."""
    cur = current()
    new, warnings = _plan(fields, cur)
    diff, undo = _diff(cur, new)
    result: dict[str, Any] = {"changed": list(diff), "diff": diff, "undo": undo, "warnings": warnings}
    if not diff or dry_run:
        return {**result, "dry_run": dry_run, "profile": get_full()}

    account = get_profile()
    touches_db = any(k in diff for k in ("education", "areas", "locations", "work_modes", "skills"))
    if not account and touches_db and not new["name"]:
        raise ValueError("Define primero tu nombre para crear tu perfil en Radar.")
    sync_db = bool(account) and ("name" in diff or touches_db) or (not account and touches_db)

    cv_file = cv_edit._path()
    previous = cv_file.read_bytes() if cv_file.exists() else None
    cv_changes: dict[str, Any] = {}
    for key in _CV_KEYS:
        if key in diff:
            value = new[key]
            cv_changes[key] = value or None
    if "locations" in diff and (cv_targets.load_profile() or {}).get("preferred_locations") is not None:
        cv_changes["preferred_locations"] = new["locations"]  # la copia del archivo no se queda vieja
    backup = cv_edit.set_fields(cv_changes) if cv_changes else None
    try:
        if sync_db:
            skills = new["skills"]
            upserts = {k: v for k, v in skills.items() if cur["skills"].get(k) != v}
            removed = [k for k in cur["skills"] if k not in skills]
            save_profile(new["name"], new["education"] or None, new["areas"], new["locations"], new["work_modes"],
                         upserts, remove_skills=removed, reason=f"edición parcial: {', '.join(diff)}")
    except Exception:
        if cv_changes:  # el archivo vuelve a como estaba: nunca queda el perfil a medias
            if previous is None:
                cv_file.unlink(missing_ok=True)
            else:
                cv_file.write_bytes(previous)
        raise
    return {**result, "backup": backup, "profile": get_full()}
