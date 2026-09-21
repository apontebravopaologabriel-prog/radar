"""Actualización del mercado desde la app: captura ofertas de la carrera activa en segundo plano.

Usa los mismos comandos que `scripts/radar-refresh.sh` (Computrabajo y, si existe su entorno
separado, JobSpy), uno a la vez y sin shell. Solo una actualización a la vez.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from radar.careers import active_pack
from radar.db.queries import get_profile
from radar.db.repository import recompute_scores
from radar.geolocation import infer_location

PROJECT_DIR = Path(__file__).resolve().parents[2]
STEP_TIMEOUT = 150
MAX_STEPS = 24
MAX_LOCATIONS = 3
MAX_QUERIES = 4

_lock = threading.Lock()
_state: dict[str, Any] = {"running": False, "done": 0, "total": 0, "created": 0, "errors": [],
                          "started_at": None, "finished_at": None, "current": None}


def _binaries() -> dict[str, list[str]]:
    main = Path(sys.executable).parent / "radar"
    found = {"computrabajo": [str(main), "ingest", "--source", "computrabajo"]} if main.exists() else {}
    jobspy = PROJECT_DIR / ".venv-jobspy/bin/radar"
    if jobspy.exists():
        found["jobspy"] = [str(jobspy), "ingest", "--source", "jobspy"]
    return found


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


def _run_step(command: list[str]) -> dict[str, Any]:
    """Ejecuta un comando de ingesta y devuelve su resumen (última línea, un dict de Python)."""
    result = subprocess.run(command, capture_output=True, text=True, timeout=STEP_TIMEOUT, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip().splitlines()[-1][:200] if (result.stderr or result.stdout).strip() else f"salió con {result.returncode}")
    last = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "{}"
    try:
        parsed = ast.literal_eval(last)
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, SyntaxError):
        return {}


def _work(steps: list[list[str]]) -> None:
    for command in steps:
        with _lock:
            _state["current"] = f"{command[-6]} · {command[-4]}" if len(command) >= 6 else None
        try:
            summary = _run_step(command)
            with _lock:
                _state["created"] += int(summary.get("created", 0))
        except (RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
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
    binaries = _binaries()
    if not binaries:
        raise RuntimeError("No se encontró el comando `radar` para actualizar el mercado.")
    locations = search_locations(places)
    chosen = [q for q in (queries or list(active_pack().queries)) if q and not q.startswith("-")][:MAX_QUERIES]
    steps = [
        [*base, "--query", query, "--location", location, "--limit", str(min(max(limit, 1), 50)),
         "--max-age-days", str(max_age_days)]
        for location in locations for query in chosen for base in binaries.values()
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
    binaries = _binaries()
    if not binaries:
        raise RuntimeError("No se encontró el comando `radar` para actualizar el mercado.")
    is_district = point.precision == "district"
    city = "Lima" if is_district else point.label
    chosen = [q for q in list(active_pack().queries) if q and not q.startswith("-")][:MAX_QUERIES]
    steps: list[list[str]] = []
    for query in chosen:
        for name, base in binaries.items():
            if name == "jobspy":
                where, keyword = (f"{point.label}, Lima" if is_district else city), query
            else:
                where, keyword = city, (f"{query} {point.label}" if is_district else query)
            steps.append([*base, "--query", keyword, "--location", where, "--limit", str(min(max(limit, 1), 50)),
                          "--max-age-days", str(max_age_days)])
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
