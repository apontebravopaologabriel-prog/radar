"""Lectura de los CVs objetivo hipotéticos y su matriz de brechas (solo lectura).

Los datos viven junto a la base SQLite, fuera del repositorio:
``cv_master.json`` (perfil real), ``targets/*.json`` (un candidato ideal por oferta)
y ``photo.jpg``. Ver ``docs/target-profiles.md``.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from radar.db.database import connection, database_path
from radar.geolocation import LIMA_DISTRICTS, LocationPoint, infer_location

_STATUS_RANK = {"cubierto": 0, "parcial": 1, "falta": 2}
_PHOTO_NAMES = ("photo.jpg", "photo.png")
_ORIGINS = {"explicito", "inferido", "tipico"}
_GAP_KINDS = {"dias", "semanas", "no_cerrable_rapido"}
_SECTIONS = {"summary", "experience", "tools", "education", "certifications"}


def data_dir() -> Path:
    return database_path().parent


def photo_path() -> Path | None:
    for name in _PHOTO_NAMES:
        candidate = data_dir() / name
        if candidate.is_file():
            return candidate
    return None


def _read_json(path: Path) -> dict[str, Any] | None:
    """JSON de un archivo local editable a mano; uno dañado se ignora en lugar de romper la API."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def load_profile() -> dict[str, Any] | None:
    profile = _read_json(data_dir() / "cv_master.json")
    if profile is None:
        return None
    # La ruta original de la foto es un dato de configuración local; no se expone.
    profile.pop("photo_path", None)
    profile["has_photo"] = photo_path() is not None
    return profile


def load_targets() -> list[dict[str, Any]]:
    directory = data_dir() / "targets"
    if not directory.is_dir():
        return []
    targets = []
    for path in sorted(directory.glob("*.json")):
        target = _read_json(path)
        if target is None or not isinstance(target.get("sections"), dict):
            continue
        target.setdefault("gaps", [])
        # Un CV objetivo es siempre hipotético, sin importar lo que diga el archivo.
        target["hypothetical"] = True
        target.pop("photo_path", None)
        target["id"] = path.stem
        targets.append(target)
    return targets


def build_matrix(targets: list[dict[str, Any]]) -> dict[str, Any]:
    """Requisitos con ``key`` cruzados por puesto; con varios ítems por clave gana el peor estado."""
    columns = [
        {"id": t["id"], "title": t.get("title"), "company": t.get("company")} for t in targets
    ]
    rows: dict[str, dict[str, Any]] = {}
    for target in targets:
        for section in ("experience", "tools"):
            for item in target.get("sections", {}).get(section, []):
                if not isinstance(item, dict):
                    continue
                key, status = item.get("key"), item.get("status")
                if not key or status not in _STATUS_RANK:
                    continue
                label = item.get("label") or item.get("text") or key
                row = rows.setdefault(key, {"key": key, "label": label, "cells": {}})
                current = row["cells"].get(target["id"])
                if current is None or _STATUS_RANK[status] > _STATUS_RANK[current]:
                    row["cells"][target["id"]] = status
    ordered = []
    for row in rows.values():
        open_count = sum(1 for status in row["cells"].values() if status != "cubierto")
        ordered.append({**row, "open_count": open_count})
    ordered.sort(key=lambda row: (-row["open_count"], row["label"]))
    return {"columns": columns, "rows": ordered}


def distance_km(a: LocationPoint, b: LocationPoint) -> float:
    """Distancia Haversine entre dos puntos, en km con un decimal."""
    lat1, lat2 = math.radians(a.latitude), math.radians(b.latitude)
    delta_lat, delta_lon = lat2 - lat1, math.radians(b.longitude - a.longitude)
    h = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return round(2 * 6371 * math.asin(math.sqrt(h)), 1)


def districts_near(reference: str, limit: int = 3) -> list[dict[str, Any]]:
    """Distritos más cercanos a una zona mencionada en una oferta (centroides aproximados)."""
    origin = infer_location(reference)
    if origin is None or origin.precision != "district":
        return []
    seen: dict[str, dict[str, Any]] = {}
    for label, latitude, longitude in LIMA_DISTRICTS.values():
        point = LocationPoint(latitude, longitude, label, "district", 0.72, "district-centroid")
        seen[label] = {"district": label, "km": distance_km(origin, point)}
    return sorted(seen.values(), key=lambda row: row["km"])[: max(1, min(limit, 10))]


def _job_context(job_id: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(
            """SELECT j.id, j.title, c.name, j.location, j.work_mode, j.seniority, j.salary_min,
                      j.salary_max, j.description_clean
               FROM jobs j LEFT JOIN companies c ON c.id = j.company_id WHERE j.id = %s""",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        skills = [
            r[0]
            for r in conn.execute(
                "SELECT s.name FROM job_skills k JOIN skills s ON s.id = k.skill_id WHERE k.job_id = %s",
                (job_id,),
            ).fetchall()
        ]
        requirements = [
            {"type": r[0], "value": r[1], "evidence": r[2]}
            for r in conn.execute(
                "SELECT requirement_type, value, evidence FROM job_requirements WHERE job_id = %s",
                (job_id,),
            ).fetchall()
        ]
    return {
        "job_id": row[0], "title": row[1], "company": row[2], "location": row[3],
        "work_mode": row[4], "seniority": row[5], "salary_min": row[6], "salary_max": row[7],
        "description": row[8], "skills": skills, "requirements": requirements,
    }


def get_target_context(job_ids: list[str]) -> dict[str, Any]:
    """Todo lo que el agente necesita para redactar los candidatos ideales, con distancias por reglas."""
    profile = load_profile()
    home = infer_location(profile.get("home_district")) if profile else None
    jobs = []
    for job_id in job_ids[:10]:
        job = _job_context(job_id)
        if job is None:
            jobs.append({"job_id": job_id, "error": "Oferta no encontrada"})
            continue
        place = infer_location(job["location"])
        job["km_from_home"] = distance_km(home, place) if home and place and place.precision == "district" else None
        jobs.append(job)
    return {"real_profile": profile, "jobs": jobs}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")[:60] or "oferta"


def validate_target(profile: dict[str, Any]) -> list[str]:
    """Errores del esquema de un CV objetivo; lista vacía si es válido."""
    errors: list[str] = []
    sections = profile.get("sections")
    if not isinstance(sections, dict):
        return ["sections debe ser un objeto"]
    for name, items in sections.items():
        if name not in _SECTIONS:
            errors.append(f"sección desconocida: {name}")
            continue
        if not isinstance(items, list):
            errors.append(f"{name} debe ser una lista")
            continue
        for index, item in enumerate(items):
            where = f"{name}[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{where}: debe ser un objeto")
                continue
            if not isinstance(item.get("text"), str) or not item["text"].strip():
                errors.append(f"{where}: falta text")
            origin = item.get("origin")
            if origin not in _ORIGINS:
                errors.append(f"{where}: origin debe ser explicito, inferido o tipico")
            if origin == "explicito" and not item.get("quote") and not item.get("reason"):
                errors.append(f"{where}: un ítem explícito necesita quote o reason")
            if origin == "inferido" and not item.get("reason"):
                errors.append(f"{where}: un ítem inferido necesita reason")
            status = item.get("status")
            if status is not None and status not in _STATUS_RANK:
                errors.append(f"{where}: status debe ser cubierto, parcial o falta")
            if status == "cubierto" and not item.get("reason"):
                errors.append(f"{where}: 'cubierto' debe citar en reason la evidencia del perfil real")
    gaps = profile.get("gaps", [])
    if not isinstance(gaps, list):
        return [*errors, "gaps debe ser una lista"]
    for index, gap in enumerate(gaps):
        if not isinstance(gap, dict):
            errors.append(f"gaps[{index}]: debe ser un objeto")
            continue
        if gap.get("kind") not in _GAP_KINDS:
            errors.append(f"gaps[{index}]: kind debe ser dias, semanas o no_cerrable_rapido")
        if not gap.get("action"):
            errors.append(f"gaps[{index}]: falta action")
    return errors


def save_target(job_id: str, profile: dict[str, Any]) -> dict[str, Any]:
    """Valida y guarda un CV objetivo. Los datos de la oferta y la distancia los pone el código."""
    if not isinstance(profile, dict):
        return {"saved": False, "errors": ["profile debe ser un objeto"]}
    errors = validate_target(profile)
    if errors:
        return {"saved": False, "errors": errors}
    job = _job_context(job_id)
    if job is None:
        return {"saved": False, "errors": ["Oferta no encontrada"]}
    real = load_profile()
    home = infer_location(real.get("home_district")) if real else None
    place = infer_location(job["location"])
    document = {
        **{k: v for k, v in profile.items() if k in {"sections", "gaps", "aviso"}},
        "job_id": job_id,
        "title": job["title"],
        "company": job["company"],
        "hypothetical": True,
        "location": {
            "job": place.label if place else job["location"],
            "home": real.get("home_district") if real else None,
            "km_from_home": distance_km(home, place) if home and place and place.precision == "district" else None,
            "method": "haversine sobre centroides (aproximado)",
        },
    }
    directory = data_dir() / "targets"
    directory.mkdir(parents=True, exist_ok=True)
    # El sufijo del id evita que dos ofertas con misma empresa y título se sobrescriban.
    base = _slug(f"{job['company'] or 'sin_empresa'}_{job['title']}")
    name = f"{base}_{job_id[:8]}"
    (directory / f"{name}.json").write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"saved": True, "id": name}
