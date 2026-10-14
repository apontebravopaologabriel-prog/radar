from datetime import UTC, datetime, timedelta

import pytest

from radar import scheduler, system
from radar.settings import get_setting, set_setting


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "radar.db"))
    monkeypatch.setenv("RADAR_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(scheduler, "systemd_timer_installed", lambda: False)
    monkeypatch.setattr(scheduler, "_running", False)


NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


def test_due_when_never_captured_overdue_or_off():
    assert scheduler.is_due(NOW)  # nunca capturó: toca ya
    set_setting("refresh_last_at", (NOW - timedelta(days=3)).isoformat())
    assert not scheduler.is_due(NOW)
    set_setting("refresh_last_at", (NOW - timedelta(days=7, minutes=1)).isoformat())
    assert scheduler.is_due(NOW)
    set_setting("refresh_every_days", "0")
    assert not scheduler.is_due(NOW) and scheduler.next_run(NOW) is None


def test_schedule_is_managed_without_systemd(monkeypatch):
    out = system.set_schedule(3)
    assert out["changed"] == "cada 3 día(s)" and out["backend"] == "internal" and out["every"] == "3d"
    assert get_setting("refresh_every_days") == "3"
    assert system.set_schedule(0)["every"] is None
    with pytest.raises(ValueError):
        system.set_schedule(45)
    assert system.schedule_status()["available"] is True


def test_tick_runs_one_capture_at_a_time_and_records_the_time(monkeypatch):
    done = []
    monkeypatch.setattr("radar.capture.run_capture", lambda log=print, **_: done.append(1) or log("ok"))
    started = []
    real = scheduler.threading.Thread

    class Inline:  # ejecuta el hilo en línea para que la prueba sea determinista
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            started.append(1)
            self.target()

    monkeypatch.setattr(scheduler.threading, "Thread", Inline)
    assert scheduler.tick(NOW) is True and done == [1] and get_setting("refresh_last_at")
    assert not scheduler.tick(datetime.now(UTC)) and done == [1]  # recién capturó: no toca
    scheduler._running = True
    set_setting("refresh_last_at", (NOW - timedelta(days=30)).isoformat())
    assert scheduler.tick(NOW) is False  # ya hay una en curso
    scheduler.threading.Thread = real
    assert (scheduler.state_dir() / "refresh.log").read_text(encoding="utf-8").strip() == "ok"


def test_internal_scheduler_does_not_start_when_systemd_timer_exists(monkeypatch):
    monkeypatch.setattr(scheduler, "systemd_timer_installed", lambda: True)
    assert scheduler.should_start() is False
    monkeypatch.setattr(scheduler, "systemd_timer_installed", lambda: False)
    monkeypatch.setenv("RADAR_INTERNAL_SCHEDULER", "0")
    assert scheduler.should_start() is False
