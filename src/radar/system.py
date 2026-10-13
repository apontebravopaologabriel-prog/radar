"""Estado y mantenimiento del sistema: temporizador de captura, salud de la BD y tareas de mantenimiento.

Todo pasa por listas cerradas de acciones (sin shell ni rutas libres): el temporizador es siempre
`radar-refresh.timer` del usuario y las tareas son las de `run_maintenance`.
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from radar.db.database import connection, database_path

TIMER_UNIT = "radar-refresh.timer"
MAX_INTERVAL_DAYS = 30
BACKUPS_KEPT = 5
TASKS = ("repair_data", "expire_stale", "check_applications", "market_snapshot", "backup")


def timer_path() -> Path:
    return Path.home() / ".config/systemd/user" / TIMER_UNIT


def _systemctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, timeout=20, check=False)


def _use_internal() -> bool:
    """Sin temporizador de systemd (Windows, macOS, instalador) manda el planificador interno."""
    from radar import scheduler

    return not scheduler.systemd_timer_installed()


def _require_systemd() -> None:
    if not shutil.which("systemctl"):
        raise ValueError("Este equipo no usa systemd: el temporizador solo se administra en Linux con systemd.")
    if not timer_path().exists():
        raise ValueError(f"No existe {timer_path()}; instala el temporizador de Radar primero (docs/operations.md).")


def schedule_status() -> dict[str, Any]:
    """Cada cuánto corre la captura automática y cuándo fue/será la próxima."""
    if _use_internal():
        from radar import scheduler

        return scheduler.status()
    text = timer_path().read_text(encoding="utf-8")
    interval = re.search(r"^OnUnitActiveSec=(\S+)", text, re.MULTILINE)
    on_boot = re.search(r"^OnBootSec=(\S+)", text, re.MULTILINE)
    state = _systemctl("is-active", TIMER_UNIT).stdout.strip() or None
    next_run = last_run = None
    listing = _systemctl("list-timers", TIMER_UNIT, "--output=json", "--no-pager").stdout
    try:
        row = next(iter(json.loads(listing) or []), {})
        stamp = lambda us: datetime.fromtimestamp(us / 1e6).astimezone().isoformat(timespec="minutes") if us else None
        next_run, last_run = stamp(row.get("next")), stamp(row.get("last"))
    except (ValueError, TypeError):
        pass
    return {"available": True, "every": interval.group(1) if interval else None,
            "on_boot": on_boot.group(1) if on_boot else None, "state": state, "next_run": next_run, "last_run": last_run}


def set_schedule(days: int, on_boot: bool | None = None) -> dict[str, Any]:
    """Cambia la frecuencia de la captura automática (`days` 1-30; 0 la desactiva). `on_boot` añade o quita el
    disparo 5 min después de cada arranque."""
    if _use_internal():
        from radar import scheduler

        scheduler.set_days(days)
        return {"changed": "desactivada" if days == 0 else f"cada {days} día(s)", **scheduler.status()}
    _require_systemd()
    if days == 0:
        _systemctl("disable", "--now", TIMER_UNIT)
        return {"changed": "desactivada", **schedule_status()}
    if not 1 <= days <= MAX_INTERVAL_DAYS:
        raise ValueError(f"days debe estar entre 1 y {MAX_INTERVAL_DAYS} (0 la desactiva)")
    path = timer_path()
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"^OnUnitActiveSec=.*$", f"OnUnitActiveSec={days}d", text, flags=re.MULTILINE)
    text = re.sub(r"^Description=.*$", f"Description=Run Radar market refresh every {days} day(s)", text, flags=re.MULTILINE)
    if on_boot is False:
        text = re.sub(r"^OnBootSec=.*\n", "", text, flags=re.MULTILINE)
    elif on_boot is True and not re.search(r"^OnBootSec=", text, re.MULTILINE):
        text = text.replace("[Timer]\n", "[Timer]\nOnBootSec=5min\n", 1)
    path.write_text(text, encoding="utf-8")
    _systemctl("daemon-reload")
    _systemctl("enable", "--now", TIMER_UNIT)
    _systemctl("restart", TIMER_UNIT)
    return {"changed": f"cada {days} día(s)", **schedule_status()}


def system_status() -> dict[str, Any]:
    """Foto del sistema: BD, ofertas, captura, temporizador, clasificación y agente (sin claves)."""
    from radar import maintenance
    from radar.agent.loop import agent_enabled, month_usage, monthly_cap, read_only
    from radar.agent.provider import load_config
    from radar.careers import active_pack
    from radar.refresh import refresh_status

    path = database_path()
    with connection() as conn:
        integrity = conn.execute("PRAGMA quick_check").fetchone()[0]
        tiers = dict(conn.execute("SELECT relevance_tier, count(*) FROM jobs WHERE is_active=1 GROUP BY 1").fetchall())
        newest = conn.execute("SELECT max(published_at) FROM jobs").fetchone()[0]
        last_run = conn.execute("SELECT max(finished_at) FROM ingestion_runs WHERE status='success'").fetchone()[0]
    backups = sorted((path.parent / "backups").glob("radar-*.db"))
    config = load_config()
    return {
        "database": {"path": str(path), "size_mb": round(path.stat().st_size / 1e6, 1) if path.exists() else 0,
                     "integrity": integrity, "backups": [b.name for b in backups][-3:]},
        "jobs_active_by_tier": tiers, "newest_published": str(newest) if newest else None,
        "last_successful_ingestion": str(last_run) if last_run else None,
        "refresh": refresh_status(), "schedule": schedule_status(),
        "classification_rules_stale": maintenance.rules_stale(), "career": active_pack().name,
        "agent": {"enabled": agent_enabled(), "provider": config.provider, "model": config.model, "key": bool(config.api_key),
                  "read_only": read_only(), "tokens_month": month_usage(), "token_cap": monthly_cap()},
    }


def backup_database() -> dict[str, Any]:
    """Copia consistente de la BD (API de respaldo de SQLite) en `backups/` junto a ella; conserva las últimas 5."""
    with connection():  # asegura que la BD y su esquema existan antes de copiarla
        pass
    source = database_path()
    folder = source.parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"radar-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}.db"
    src, dst = sqlite3.connect(source), sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    old = sorted(folder.glob("radar-*.db"))[:-BACKUPS_KEPT]
    for item in old:
        item.unlink()
    return {"backup": str(target), "size_mb": round(target.stat().st_size / 1e6, 1), "removed_old": len(old)}


def run_maintenance(task: str, days: int = 45, limit: int = 40) -> dict[str, Any]:
    """Ejecuta una tarea de mantenimiento de la lista cerrada `TASKS`."""
    from radar.db.repository import capture_market_snapshot, expire_stale_jobs, repair_data_quality
    from radar.liveness import check_application_status

    if task not in TASKS:
        raise ValueError(f"task debe ser una de: {', '.join(TASKS)}")
    if task == "repair_data":
        return {"task": task, "result": repair_data_quality()}
    if task == "expire_stale":
        return {"task": task, "deactivated": expire_stale_jobs(min(max(days, 7), 365))}
    if task == "check_applications":
        return {"task": task, "result": check_application_status(min(max(limit, 1), 60), 7)}
    if task == "market_snapshot":
        return {"task": task, "metrics_saved": capture_market_snapshot(None)}
    return {"task": task, **backup_database()}
