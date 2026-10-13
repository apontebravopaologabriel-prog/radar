"""Captura programada del mercado, multiplataforma (antes `scripts/radar-refresh.sh`).

Corre en el mismo proceso: consulta cada portal con las búsquedas del paquete de carrera activo, aísla cada paso
(un fallo o un tiempo agotado se registra en el resumen y no detiene el resto), repara datos, desactiva ofertas
vencidas, guarda la fotografía del mercado y hace una copia de la base. Lo usan `radar refresh`, el
temporizador de systemd y, más adelante, el planificador interno.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from radar.careers import active_pack

STEP_TIMEOUT = 180
DEFAULT_MAX_AGE_DAYS = 10
DEFAULT_STALE_DAYS = 45
DEFAULT_LIVENESS_LIMIT = 150
LIMA_LIMIT = 50
CITY_LIMIT = 25


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() not in {"0", "false", "no", ""}


def _run_with_timeout(fn: Callable[[], Any], timeout: float) -> Any:
    """Ejecuta `fn` en un hilo; si no termina a tiempo se abandona (el hilo es daemon) y se informa."""
    box: dict[str, Any] = {}

    def target() -> None:
        try:
            box["value"] = fn()
        except Exception as exc:  # noqa: BLE001 - cada paso es opcional y se resume al final
            box["error"] = exc

    thread = threading.Thread(target=target, daemon=True, name="radar-capture-step")
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise TimeoutError(f"sin respuesta tras {int(timeout)} s")
    if "error" in box:
        raise box["error"]
    return box.get("value")


def _cities(raw: str | list[str] | None) -> list[str]:
    if raw is None:
        raw = os.getenv("RADAR_CITIES", "")
    items = raw.split(",") if isinstance(raw, str) else raw
    return [city.strip() for city in items if city and city.strip()]


def plan_steps(cities: list[str], computrabajo: bool, queries: tuple[str, ...], city_queries: tuple[str, ...]) -> list[dict[str, Any]]:
    """Lista ordenada de búsquedas: Lima con las amplias del paquete y cada ciudad con las cortas."""
    sources = ["jobspy", *(["computrabajo"] if computrabajo else [])]
    steps = [{"source": s, "query": q, "location": "Lima", "limit": LIMA_LIMIT} for s in sources for q in queries]
    for city in cities:
        steps += [{"source": s, "query": q, "location": city, "limit": CITY_LIMIT} for q in city_queries for s in sources]
    return steps


def run_capture(
    cities: str | list[str] | None = None,
    max_age_days: int | None = None,
    computrabajo: bool | None = None,
    log: Callable[[str], None] = lambda line: print(line, flush=True),  # sin búfer: `tail -f refresh.log` ve el avance
    step_timeout: float = STEP_TIMEOUT,
) -> dict[str, Any]:
    from radar.db.repository import capture_market_snapshot, expire_stale_jobs, repair_data_quality
    from radar.liveness import check_application_status
    from radar.pipeline import run_ingestion
    from radar.system import backup_database

    age = max_age_days if max_age_days is not None else int(os.getenv("RADAR_MAX_AGE_DAYS", DEFAULT_MAX_AGE_DAYS))
    use_computrabajo = computrabajo if computrabajo is not None else _flag("RADAR_COMPUTRABAJO_ENABLED", True)
    pack = active_pack()
    steps = plan_steps(_cities(cities), use_computrabajo, pack.market_queries, pack.queries)
    failed: list[str] = []
    created = 0

    def run_step(label: str, fn: Callable[[], Any], *, limited: bool = True) -> Any:
        """`limited`: solo las consultas a portales tienen límite de tiempo. El mantenimiento local (reparar, expirar,
        comprobar, respaldar) corre sin límite: abandonarlo a medias dejaría un hilo reteniendo la base de datos."""
        log(f"[{label}]")
        try:
            return _run_with_timeout(fn, step_timeout) if limited else fn()
        except Exception as exc:  # noqa: BLE001
            log(f"[{label}] FAILED: {str(exc)[:200]}")
            failed.append(label)
            return None

    log(f"{datetime.now(UTC).isoformat(timespec='seconds')} Radar capture: career={pack.id} max_age_days={age} steps={len(steps)}")
    for step in steps:
        where = "" if step["location"] == "Lima" else f" [{step['location']}]"
        stats = run_step(
            f"{step['source']}{where}: {step['query']}",
            lambda s=step: run_ingestion(s["source"], s["query"], s["location"], s["limit"], age),
        )
        if isinstance(stats, dict):
            created += int(stats.get("created", 0))
    run_step("quality: repair-data", repair_data_quality, limited=False)
    run_step("quality: expire-stale", lambda: expire_stale_jobs(int(os.getenv("RADAR_STALE_AFTER_DAYS", DEFAULT_STALE_DAYS))), limited=False)
    run_step("quality: check-applications", lambda: check_application_status(int(os.getenv("RADAR_LIVENESS_CHECK_LIMIT", DEFAULT_LIVENESS_LIMIT))), limited=False)
    run_step("market: snapshot", capture_market_snapshot, limited=False)
    run_step("backup: sqlite", backup_database, limited=False)
    summary = {"steps": len(steps), "failed": failed, "created": created}
    log(f"SUMMARY: {len(failed)} step(s) failed: {', '.join(failed)}" if failed else "SUMMARY: all steps completed")
    log(datetime.now(UTC).isoformat(timespec="seconds"))
    return summary
