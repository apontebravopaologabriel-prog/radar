"""Actualización del mercado desde la app: captura ofertas de la carrera activa en segundo plano.

Usa la misma ingesta que `radar refresh` (Computrabajo y, si `python-jobspy` está instalado, Indeed/LinkedIn),
dentro del proceso y un paso a la vez. Solo una actualización a la vez.
"""

from __future__ import annotations

import importlib.util
import os
import threading
import time
from typing import Any

from radar.careers import active_pack
from radar.db.queries import get_profile
from radar.db.repository import recompute_scores
from radar.geolocation import infer_location

STEP_TIMEOUT = 150
MAX_STEPS = 24
MAX_LOCATIONS = 3
MAX_QUERIES = 4

_lock = threading.Lock()
_state: dict[str, Any] = {"running": False, "done": 0, "total": 0, "created": 0, "errors": [],
                          "started_at": None, "finished_at": None, "current": None}


def _sources() -> list[str]:
    """Fuentes disponibles en esta instalación: Computrabajo, JobSpy (Indeed/LinkedIn/Google), Bumeran y Empleos Perú."""
    items = ["computrabajo", *(["jobspy"] if importlib.util.find_spec("jobspy") else [])]
    if os.getenv("RADAR_BUMERAN_ENABLED", "1").strip().lower() not in {"0", "false", "no"}:
        items.append("bumeran")
    if os.getenv("RADAR_EMPLEOS_ENABLED", "1").strip().lower() not in {"0", "false", "no"}:
        items.append("empleos")
    return items


def search_locations(places: list[str] | None = None) -> list[str]:
    """Nombres que entienden las fuentes: 'Lima' para cualquier distrito de Lima/Callao, o la ciudad."""
    names: list[str] = []
    for place in places or (get_profile() or {}).get("locations", []) or ["Lima"]:
        point = infer_location(place)
        if point is None:
            continue
        name = "Lima" if point.precision == "district" else point.label
        if name not in names:
            names.append(name)
    return (names or ["Lima"])[:MAX_LOCATIONS]


def _run_step(step: dict[str, Any]) -> dict[str, Any]:
    """Ejecuta una búsqueda de ingesta en el proceso y devuelve su resumen; falla si el portal no responde a tiempo."""
    from radar.capture import _run_with_timeout
    from radar.pipeline import run_ingestion

    result = _run_with_timeout(
        lambda: run_ingestion(step["source"], step["query"], step["location"], step["limit"], step["max_age_days"]),
        STEP_TIMEOUT,
    )
    return result if isinstance(result, dict) else {}


def _work(steps: list[dict[str, Any]]) -> None:
    for step in steps:
        with _lock:
            _state["current"] = f"{step['query']} · {step['location']}"
        try:
            summary = _run_step(step)
            with _lock:
                _state["created"] += int(summary.get("created", 0))
        except Exception as exc:  # noqa: BLE001 - un portal caído no detiene la actualización
            with _lock:
                _state["errors"].append(str(exc)[:160])
        with _lock:
            _state["done"] += 1
    profile = get_profile()
    if profile:
        try:
            recompute_scores(profile["id"])
        except Exception as exc:  # noqa: BLE001 - se informa, no se interrumpe
            with _lock:
                _state["errors"].append(f"puntaje: {exc}"[:160])
    with _lock:
        _state.update(running=False, current=None, finished_at=time.time())


def start_refresh(
    places: list[str] | None = None,
    queries: list[str] | None = None,
    limit: int = 15,
    max_age_days: int = 14,
) -> dict[str, Any]:
    sources = _sources()
    locations = search_locations(places)
    chosen = [q for q in (queries or list(active_pack().queries)) if q and not q.startswith("-")][:MAX_QUERIES]
    steps = [
        {"source": source, "query": query, "location": location, "limit": min(max(limit, 1), 50), "max_age_days": max_age_days}
        for location in locations for query in chosen for source in sources
    ][:MAX_STEPS]
    with _lock:
        if _state["running"]:
            raise RuntimeError("Ya hay una actualización en curso.")
        _state.update(running=True, done=0, total=len(steps), created=0, errors=[],
                      started_at=time.time(), finished_at=None, current=None)
    threading.Thread(target=_work, args=(steps,), daemon=True, name="radar-refresh").start()
    return refresh_status()


def start_place_refresh(place: str, limit: int = 25, max_age_days: int = 14) -> dict[str, Any]:
    """Trae ofertas nuevas enfocadas en un distrito o ciudad, en segundo plano.

    Las fuentes solo buscan por ciudad: JobSpy (Indeed/LinkedIn) acepta «Distrito, Lima» como ubicación y en
    Computrabajo el distrito se añade a la palabra clave. El resultado se sesga hacia ese lugar, no se limita a él.
    """
    point = infer_location(place)
    if point is None or (point.precision == "department" and point.label == "Lima" and place.strip().lower() != "lima"):
        raise ValueError(f"Lugar desconocido: {place}")
    sources = _sources()
    is_district = point.precision == "district"
    city = "Lima" if is_district else point.label
    chosen = [q for q in list(active_pack().queries) if q and not q.startswith("-")][:MAX_QUERIES]
    steps: list[dict[str, Any]] = []
    for query in chosen:
        for name in sources:
            if name == "jobspy":
                where, keyword = (f"{point.label}, Lima" if is_district else city), query
            else:
                where, keyword = city, (f"{query} {point.label}" if is_district else query)
            steps.append({"source": name, "query": keyword, "location": where,
                          "limit": min(max(limit, 1), 50), "max_age_days": max_age_days})
    steps = steps[:MAX_STEPS]
    with _lock:
        if _state["running"]:
            raise RuntimeError("Ya hay una actualización en curso.")
        _state.update(running=True, done=0, total=len(steps), created=0, errors=[],
                      started_at=time.time(), finished_at=None, current=None)
    threading.Thread(target=_work, args=(steps,), daemon=True, name="radar-refresh").start()
    return {**refresh_status(), "place": point.label, "note": "Se ejecuta en segundo plano; consulta get_refresh_status."}


def refresh_status() -> dict[str, Any]:
    with _lock:
        return dict(_state, errors=list(_state["errors"]))
