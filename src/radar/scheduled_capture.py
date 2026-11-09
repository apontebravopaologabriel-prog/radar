"""Persist scheduled attempts across boots and serialize timer invocations."""
from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from radar.paths import state_dir


def interval_days() -> int:
    from radar import scheduler, system

    path = system.timer_path()
    if path.exists():
        match = re.search(r"^OnUnitActiveSec=(\d+)d$", path.read_text(), re.MULTILINE)
        if match:
            return int(match.group(1))
    return scheduler.days()


def read_state() -> dict:
    try:
        value = json.loads((state_dir() / "scheduled-capture.json").read_text())
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}


def next_due(state: dict, days: int, now: datetime) -> datetime:
    field = "last_attempt" if state.get("status") == "failed" else "completed_at"
    try:
        stamp = datetime.fromisoformat(state[field])
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
    except (KeyError, TypeError, ValueError):
        return now
    return stamp + (timedelta(hours=1) if field == "last_attempt" else timedelta(days=days))


@contextmanager
def capture_lock():
    folder = state_dir()
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "scheduled-capture.lock").open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
        try:
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        yield True


def _write_state(state: dict) -> None:
    folder = state_dir()
    with tempfile.NamedTemporaryFile(mode="w", dir=folder, delete=False) as handle:
        temporary = handle.name
        json.dump(state, handle)
    try:
        os.replace(temporary, folder / "scheduled-capture.json")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def run_scheduled(*args, now: datetime | None = None) -> dict:
    from radar.capture import run_capture

    provided_now = now
    now = now or datetime.now(UTC)
    with capture_lock() as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "capture already running"}
        days = interval_days()
        state = read_state()
        if days == 0 or next_due(state, days, now) > now:
            print("Scheduled capture skipped: interval has not elapsed", flush=True)
            return {"status": "skipped", "reason": "not due"}
        try:
            result = run_capture(*args)
        except Exception:
            state.update(last_attempt=(provided_now or datetime.now(UTC)).isoformat(), status="failed")
            _write_state(state)
            raise
        finished = provided_now or datetime.now(UTC)
        state.update(last_attempt=finished.isoformat(), status=result["status"])
        if result["status"] in {"success", "partial"}:
            state["completed_at"] = finished.isoformat()
        _write_state(state)
        return result
