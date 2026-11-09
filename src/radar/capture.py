"""Cross-platform scheduled market capture driven by the active career packs.

Download workers have bounded lifetimes; database writes and maintenance stay
in the parent. Independent source failures do not stop the remaining searches.
The CLI, systemd service and internal scheduler share this entry point.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from radar.careers import active_pack, load_pack

STEP_TIMEOUT = 180
DEFAULT_MAX_AGE_DAYS = 10
DEFAULT_STALE_DAYS = 45
DEFAULT_LIVENESS_LIMIT = 150
LIMA_LIMIT = 50
CITY_LIMIT = 25


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() not in {"0", "false", "no", ""}


def _cities(raw: str | list[str] | None) -> list[str]:
    if raw is None:
        raw = os.getenv("RADAR_CITIES", "")
    items = raw.split(",") if isinstance(raw, str) else raw
    return [city.strip() for city in items if city and city.strip()]


def plan_steps(
    cities: list[str],
    computrabajo: bool,
    queries: tuple[str, ...],
    city_queries: tuple[str, ...],
    extra_sources: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Lista ordenada de búsquedas: Lima con las amplias del paquete y cada ciudad con las cortas."""
    configured_extras = os.getenv("RADAR_EXTRA_SOURCES", "").strip()
    defaults = [name for name, flag in (("bumeran", "RADAR_BUMERAN_ENABLED"), ("empleos", "RADAR_EMPLEOS_ENABLED")) if _flag(flag, True)]
    extras = [
        s.strip().lower()
        for s in (extra_sources if extra_sources is not None else configured_extras.split(",") if configured_extras else defaults)
        if s and s.strip()
    ]
    sources = list(dict.fromkeys(["jobspy", *(["computrabajo"] if computrabajo else []), *extras]))
    steps = [{"source": s, "query": q, "location": "Lima", "limit": LIMA_LIMIT} for q in queries for s in sources]
    for city in cities:
        steps += [{"source": s, "query": q, "location": city, "limit": CITY_LIMIT} for q in city_queries for s in sources]
    return steps


def run_capture(
    cities: str | list[str] | None = None,
    max_age_days: int | None = None,
    computrabajo: bool | None = None,
    log: Callable[[str], None] = lambda line: print(line, flush=True),  # sin búfer: `tail -f refresh.log` ve el avance
    step_timeout: float = STEP_TIMEOUT,
    market_ids: list[str] | None = None,
) -> dict[str, Any]:
    from radar.db.repository import capture_market_snapshot, expire_stale_jobs, repair_data_quality
    from radar.liveness import check_application_status
    from radar.pipeline import run_ingestion
    from radar.system import backup_database

    age = max_age_days if max_age_days is not None else int(os.getenv("RADAR_MAX_AGE_DAYS", DEFAULT_MAX_AGE_DAYS))
    use_computrabajo = computrabajo if computrabajo is not None else _flag("RADAR_COMPUTRABAJO_ENABLED", True)
    from radar.settings import get_json_setting

    selected = market_ids or get_json_setting("capture_market_ids", []) or [active_pack().id]
    packs = [load_pack(key) for key in dict.fromkeys(selected)]
    planned = [plan_steps(_cities(cities), use_computrabajo, p.market_queries, p.queries) for p in packs]
    steps = []
    # Interleave packs so a limited run does not systematically starve the second market.
    by_key = {}
    for i in range(max((len(p) for p in planned), default=0)):
        for pack, plan in zip(packs, planned, strict=True):
            if i >= len(plan):
                continue
            step = plan[i]
            key = (step["source"], step["query"], step["location"])
            if key not in by_key:
                by_key[key] = {**step, "market_ids": []}
                steps.append(by_key[key])
            by_key[key]["market_ids"].append(pack.id)
    failed: list[str] = []
    created = 0
    blocked_counts: dict[str, int] = {}
    skipped: list[str] = []
    maintenance_failed: list[str] = []

    def run_step(label: str, fn: Callable[[], Any], *, source: str | None = None) -> Any:
        log(f"[{label}]")
        try:
            result = fn()
            if source:
                blocked_counts[source] = 0
            return result
        except Exception as exc:  # noqa: BLE001 - isolate independent source failures
            log(f"[{label}] FAILED: {str(exc)[:200]}")
            failed.append(label)
            if source:
                response = getattr(exc, "response", None)
                status = getattr(exc, "status_code", None) or getattr(response, "status_code", None)
                blocked_counts[source] = blocked_counts.get(source, 0) + 1 if status == 403 else 0
            else:
                maintenance_failed.append(label)
            return None

    log(f"{datetime.now(UTC).isoformat(timespec='seconds')} Radar capture: markets={','.join(p.id for p in packs)} max_age_days={age} steps={len(steps)}")
    for step in steps:
        where = "" if step["location"] == "Lima" else f" [{step['location']}]"
        if blocked_counts.get(step["source"], 0) >= 2:
            skipped.append(f"{step['source']}{where}: {step['query']}")
            continue
        stats = run_step(
            f"{step['source']}{where}: {step['query']}",
            lambda s=step: run_ingestion(s["source"], s["query"], s["location"], s["limit"], age,
                                         search_timeout=step_timeout, market_ids=s["market_ids"]), source=step["source"],
        )
        if isinstance(stats, dict):
            created += int(stats.get("created", 0))
    run_step("quality: repair-data", repair_data_quality)
    run_step("quality: expire-stale", lambda: expire_stale_jobs(int(os.getenv("RADAR_STALE_AFTER_DAYS", DEFAULT_STALE_DAYS))))
    run_step("quality: check-applications", lambda: check_application_status(int(os.getenv("RADAR_LIVENESS_CHECK_LIMIT", DEFAULT_LIVENESS_LIMIT))))
    run_step("market: snapshot", capture_market_snapshot)
    run_step("backup: sqlite", backup_database)
    source_failures = sum(1 for label in failed if not label.startswith(("quality:", "market:", "backup:")))
    summary = {"steps": len(steps), "failed": failed, "created": created,
               "source_successes": len(steps) - source_failures - len(skipped),
               "skipped": skipped, "maintenance_failed": maintenance_failed,
               "status": "failed" if maintenance_failed or source_failures + len(skipped) == len(steps) else "partial" if failed or skipped else "success"}
    log(f"SUMMARY: {len(failed)} step(s) failed: {', '.join(failed)}" if failed else "SUMMARY: all steps completed")
    if skipped:
        log(f"PAUSED: {len(skipped)} searches skipped after consecutive HTTP 403 responses")
    log(datetime.now(UTC).isoformat(timespec="seconds"))
    return summary
