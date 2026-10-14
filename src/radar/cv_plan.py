"""Plan de cierre de brechas entre tus objetivos y cierre del ciclo con evidencia.

Todo es determinista y local. ``closure_plan`` agrega las brechas de tus objetivos (ofertas con ★), estima
cuánto sube la cercanía de cada uno si cierras una skill y la cruza con su demanda real en el mercado.
``close_gap`` registra la evidencia que la persona aporta (certificado o proyecto) en su CV, la anota en
la línea de tiempo y devuelve la cercanía antes y después. Ver ``docs/cv.md``.
"""

from __future__ import annotations

import re
from typing import Any

from radar import cv_baseline, cv_edit, cv_targets
from radar.db.queries import career_timeline, skill_overview
from radar.db.repository import add_career_event
from radar.normalize import normalize_text

MARKET_DAYS = 30
EVIDENCE_KINDS = ("certificado", "proyecto")
_EVENT_TYPE = {"certificado": "certification", "proyecto": "project"}
CLOSED_MARK = "Cierra brecha:"


def _snapshot(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Objetivos con su brecha base y cercanía calculadas contra ``profile``."""
    targets = []
    for job_id in cv_baseline.selected_job_ids():
        job = cv_targets._job_context(job_id)
        if job is None:
            continue
        items = cv_baseline.baseline(job_id, profile)
        targets.append({
            "id": job_id, "company": job["company"], "title": job["title"], "items": items,
            "description": job.get("description") or "",
            "readiness": cv_baseline.readiness(items, job.get("description") or ""),
        })
    return targets


def _gain(target: dict[str, Any], key: str) -> int | None:
    """Puntos de cercanía que ganaría este objetivo si ``key`` pasara a cubierto."""
    now = target["readiness"]
    if now["percent"] is None or now["low_data"]:
        return None
    changed = [{**i, "status": "cubierto"} if i["key"] == key else i for i in target["items"]]
    after = cv_baseline.readiness(changed, target["description"])["percent"]
    return None if after is None else after - now["percent"]


def _agent_gap_for(label: str) -> dict[str, Any] | None:
    """Acción propuesta por el agente para esta skill (kind, action, estimate_days), si existe."""
    needle = normalize_text(label)
    for target in cv_targets.load_targets():
        for gap in target.get("gaps", []):
            if needle and needle in normalize_text(str(gap.get("item", ""))):
                return {k: gap.get(k) for k in ("kind", "action", "estimate_days", "evidence_to_produce")}
    return None


def closure_plan(limit: int = 10) -> dict[str, Any]:
    """Qué skills cerrar primero: las que más suben tu cercanía entre todos tus objetivos, con su demanda."""
    profile = cv_targets.load_profile() or {}
    targets = _snapshot(profile)
    market = {s["name"]: s for s in skill_overview(max_age_days=MARKET_DAYS)["skills"]}
    skills: dict[str, dict[str, Any]] = {}
    structural: dict[str, dict[str, Any]] = {}
    for target in targets:
        for item in target["items"]:
            if item["status"] == "cubierto":
                continue
            if item["category"] != "skill":
                row = structural.setdefault(item["key"], {"label": item["label"], "status": item["status"],
                                                          "targets": [], "reason": item["reason"]})
                row["targets"].append(target["company"] or target["title"])
                continue
            row = skills.setdefault(item["key"], {
                "key": item["key"], "skill": item["label"], "targets": [], "gain_points": 0,
                "required_in": 0, "status": item["status"],
            })
            row["targets"].append(target["company"] or target["title"])
            row["gain_points"] += _gain(target, item["key"]) or 0
            row["required_in"] += item["requirement"] == "required"
            if item["status"] == "falta":
                row["status"] = "falta"
    plan = []
    for row in skills.values():
        stats = market.get(row["skill"])
        row["unlocks"] = len(row["targets"])
        row["market_share_pct"] = round(stats["share"] * 100, 1) if stats else None
        row["market_jobs"] = stats["job_count"] if stats else None
        row["proposal"] = _agent_gap_for(row["skill"])
        plan.append(row)
    plan.sort(key=lambda r: (-r["gain_points"], -r["unlocks"], -(r["market_share_pct"] or 0), r["skill"]))
    return {
        "targets": len(targets), "market_days": MARKET_DAYS, "plan": plan[: max(1, min(limit, 30))],
        "structural": [{"key": k, **v} for k, v in structural.items()],
        "closed": recently_closed(),
        "note": "gain_points suma, entre tus objetivos, los puntos de cercanía que ganarías al cubrir esa skill. "
                "Lo estructural (años de experiencia, grado) no se cierra con un curso.",
    }


def recently_closed(limit: int = 8) -> list[dict[str, Any]]:
    """Brechas cerradas con evidencia, tomadas de la línea de tiempo (más recientes primero)."""
    events = [e for e in career_timeline(60)
              if e["kind"] == "career_event" and (e.get("description") or "").startswith(CLOSED_MARK)]
    return [{"title": e["title"], "type": e["subtype"], "detail": e["description"], "date": e["date"]}
            for e in events[:limit]]


def _progress(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now = {t["id"]: t for t in after}
    rows = []
    for old in before:
        new = now.get(old["id"])
        if new is None:
            continue
        rows.append({"company": old["company"], "title": old["title"],
                     "before": old["readiness"]["percent"], "after": new["readiness"]["percent"]})
    return rows


def close_gap(skill: str, kind: str, name: str, issuer: str | None = None, date: str | None = None,
              description: str | None = None, link: str | None = None) -> dict[str, Any]:
    """Registra evidencia real que cierra una brecha: la guarda en el CV, anota el hito y mide el efecto."""
    skill, name = " ".join(skill.split()), " ".join(name.split())
    if kind not in EVIDENCE_KINDS:
        raise ValueError(f"kind debe ser uno de: {', '.join(EVIDENCE_KINDS)}")
    if not skill or not name:
        raise ValueError("skill y name son obligatorios")
    if date and not re.match(r"^\d{4}(-\d{2})?$", date):
        raise ValueError("date debe tener formato AAAA-MM (o AAAA)")
    if kind == "proyecto" and len((description or "").strip()) < 15:
        raise ValueError("Un proyecto necesita una descripción de lo que hiciste (mín. 15 caracteres). Pregúntasela a la persona.")
    before = _snapshot(cv_targets.load_profile() or {})
    if kind == "certificado":
        item: dict[str, Any] = {"name": name, "issuer": issuer, "date": date}
        written = cv_edit.update_cv("certifications", "add", {k: v for k, v in item.items() if v})
    else:
        project = {"name": name, "description": description, "skills": [skill], "date": date, "link": link}
        written = cv_edit.update_cv("projects", "add", {k: v for k, v in project.items() if v})
    try:  # la nota de brecha del CV ya no aplica; si no hay una coincidencia única se deja como está
        cv_edit.update_cv("gaps", "remove", match=skill)
        note_removed = True
    except ValueError:
        note_removed = False
    after = _snapshot(cv_targets.load_profile() or {})
    progress = _progress(before, after)
    summary = "; ".join(f"{p['company']}: {p['before']}% → {p['after']}%" for p in progress
                        if p["before"] is not None and p["after"] is not None) or "sin objetivos con datos suficientes"
    try:
        started = f"{date}-01" if date and len(date) == 7 else (f"{date}-01-01" if date else None)
        add_career_event(None, _EVENT_TYPE[kind], name, f"{CLOSED_MARK} {skill}. Cercanía — {summary}", started)
        recorded = True
    except Exception:  # noqa: BLE001 - el hito es un extra: sin perfil en la base no debe deshacer el CV
        recorded = False
    counted = any(p["after"] != p["before"] for p in progress)
    return {
        "closed": skill, "evidence": {"kind": kind, "name": name}, "progress": progress, "backup": written["backup"],
        "recorded_in_timeline": recorded, "gap_note_removed": note_removed, "counted": counted,
        "note": None if counted else "No cambió la cercanía de ningún objetivo. Si es un certificado, su nombre debe "
                                     "mencionar la skill (o registra un proyecto que la use).",
    }
