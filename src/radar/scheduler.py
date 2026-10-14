"""Planificador interno de la captura automática, para sistemas sin systemd (Windows, macOS, instalaciones empaquetadas).

Corre dentro del proceso de la API: cada minuto comprueba si toca capturar (`refresh_every_days` y
`refresh_last_at` en `app_settings`) y, si toca, ejecuta `capture.run_capture` en un hilo. En Linux con el
temporizador `radar-refresh.timer` instalado no se inicia, para no capturar dos veces. Solo corre mientras Radar está abierto
(o en segundo plano, si la persona lo deja así); al abrir, una captura vencida se ejecuta tras un breve retraso.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from radar.paths import state_dir
from radar.settings import get_setting, set_setting

DEFAULT_DAYS = 7
MAX_DAYS = 30
START_DELAY_SECONDS = 120  # equivale a «5 minutos tras el arranque» del temporizador de systemd
TICK_SECONDS = 60

log = logging.getLogger(__name__)
_lock = threading.Lock()
_running = False
_thread: threading.Thread | None = None
_stop = threading.Event()


def days() -> int:
    raw = get_setting("refresh_every_days")
    return min(int(raw), MAX_DAYS) if raw is not None and raw.isdigit() else DEFAULT_DAYS


def last_run() -> datetime | None:
    raw = get_setting("refresh_last_at")
    try:
        return datetime.fromisoformat(raw) if raw else None
    except ValueError:
        return None


def next_run(now: datetime | None = None) -> datetime | None:
    interval = days()
    if interval == 0:
        return None
    last = last_run()
    return (last + timedelta(days=interval)) if last else (now or datetime.now(UTC))


def is_due(now: datetime | None = None) -> bool:
    due_at = next_run(now)
    return due_at is not None and (now or datetime.now(UTC)) >= due_at


def set_days(value: int) -> None:
    if not 0 <= value <= MAX_DAYS:
        raise ValueError(f"days debe estar entre 1 y {MAX_DAYS} (0 la desactiva)")
    set_setting("refresh_every_days", str(value))


def status() -> dict[str, Any]:
    interval = days()
    upcoming, last = next_run(), last_run()
    return {"available": True, "backend": "internal", "every": f"{interval}d" if interval else None,
            "state": "active" if interval and _thread is not None and _thread.is_alive() else ("inactive" if not interval else "stopped"),
            "next_run": upcoming.astimezone().isoformat(timespec="minutes") if upcoming else None,
            "last_run": last.astimezone().isoformat(timespec="minutes") if last else None, "running": _running}


def run_now() -> bool:
    """Lanza una captura en segundo plano. Devuelve False si ya hay una en curso."""
    global _running
    with _lock:
        if _running:
            return False
        _running = True
    threading.Thread(target=_capture, daemon=True, name="radar-scheduled-capture").start()
    return True


def _capture() -> None:
    global _running
    from radar.capture import run_capture

    folder = state_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with open(folder / "refresh.log", "a", encoding="utf-8") as handle:
            def log(line: str) -> None:
                handle.write(line + "\n")
                handle.flush()

            run_capture(log=log)
    except Exception:  # noqa: BLE001 - una captura fallida no debe tumbar la app
        log.exception("La captura programada falló")
    finally:
        set_setting("refresh_last_at", datetime.now(UTC).isoformat(timespec="seconds"))
        with _lock:
            _running = False


def tick(now: datetime | None = None) -> bool:
    """Un ciclo del planificador: lanza la captura si toca y no hay otra en curso."""
    return is_due(now) and run_now()


def _loop() -> None:
    if _stop.wait(START_DELAY_SECONDS):
        return
    while True:
        try:
            tick()
        except Exception:
            log.exception("Ciclo del planificador falló")
        if _stop.wait(TICK_SECONDS):
            return


def systemd_timer_installed() -> bool:
    from radar import system

    return bool(system.shutil.which("systemctl")) and system.timer_path().exists()


def should_start() -> bool:
    return os.getenv("RADAR_INTERNAL_SCHEDULER", "1") != "0" and not systemd_timer_installed()


def start() -> bool:
    global _thread
    if not should_start() or (_thread is not None and _thread.is_alive()):
        return False
    _stop.clear()
    _thread = threading.Thread(target=_loop, daemon=True, name="radar-scheduler")
    _thread.start()
    return True


def stop() -> None:
    _stop.set()
