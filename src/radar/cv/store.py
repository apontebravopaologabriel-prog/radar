"""Lectura del perfil factual (`cv_master.json`), distancias aproximadas y matriz de comparación."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from radar.db.database import connection, database_path
from radar.db.queries import get_profile
from radar.geolocation import LIMA_DISTRICTS, LocationPoint, infer_location

_STATUS_RANK = {"cubierto": 0, "parcial": 1, "falta": 2}


def data_dir() -> Path:
    return database_path().parent


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
    profile.pop("photo_path", None)
    profile.pop("has_photo", None)
    # Las herramientas autodeclaradas viven en la base (se editan en Ajustes o con el agente): una copia guardada
    # en el archivo quedaría vieja. Si hay perfil en la base, manda; si no, se conserva lo del archivo.
    account = get_profile()
    if account and account["skills"]:
        profile["tools_declared_in_db"] = {
            "_nota": "Niveles autodeclarados en tu perfil de Radar; no verificados con evidencia.",
            **{name: level for name, level in account["skills"].items() if level != "none"},
        }
    return profile


def build_matrix(targets: list[dict[str, Any]]) -> dict[str, Any]:
    """Requisitos con ``key`` cruzados por puesto; con varios ítems por clave gana el peor estado."""
    columns = [
        {"id": t["id"], "title": t.get("title"), "company": t.get("company")} for t in targets
    ]
    rows: dict[str, dict[str, Any]] = {}
    for target in targets:
        items = [*target.get("baseline", [])]
        for section in ("experience", "tools"):
            items.extend(target.get("sections", {}).get(section, []))
        for item in items:
            if not isinstance(item, dict):
                continue
            key, status = item.get("key"), item.get("status")
            if not key or status not in _STATUS_RANK:
                continue
            label = item.get("label") or item.get("text") or key
            row = rows.setdefault(key, {"key": key, "label": label, "cells": {}, "agent_cells": []})
            current = row["cells"].get(target["id"])
            if current is None or _STATUS_RANK[status] > _STATUS_RANK[current]:
                row["cells"][target["id"]] = status
            if item.get("status_source") == "agente" and target["id"] not in row["agent_cells"]:
                row["agent_cells"].append(target["id"])
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
               FROM jobs j LEFT JOIN companies c ON c.id = j.company_id
               WHERE j.id = %s""",
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
