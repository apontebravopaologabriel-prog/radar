import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from radar import capture, scheduled_capture, scheduler
from radar.settings import get_setting, set_setting
from radar.source_fetch import SourceFetchError, run_in_process


def return_value():
    return [1, 2, 3]


def forbidden():
    request = httpx.Request("GET", "https://example.com")
    httpx.Response(403, request=request).raise_for_status()


def urllib_forbidden():
    import urllib.error

    raise urllib.error.HTTPError("https://example.com", 403, "Forbidden", None, None)


def delayed_write(path):
    time.sleep(2)
    Path(path).write_text("late")


def test_worker_results_and_errors():
    assert run_in_process(return_value, (), 10) == [1, 2, 3]
    with pytest.raises(SourceFetchError) as exc:
        run_in_process(forbidden, (), 10)
    assert exc.value.status_code == 403
    # urllib raises HTTPError, which exposes `.code` and no `response.status_code`.
    with pytest.raises(SourceFetchError) as exc:
        run_in_process(urllib_forbidden, (), 10)
    assert exc.value.status_code == 403


def test_timeout_terminates_worker(tmp_path):
    marker = tmp_path / "late"
    with pytest.raises(TimeoutError):
        run_in_process(delayed_write, (str(marker),), 1)
    time.sleep(2.2)
    assert not marker.exists()


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "radar.db"))
    monkeypatch.setenv("RADAR_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(scheduled_capture, "interval_days", lambda: 2)


def test_pause_forbidden_source_without_stopping_market(isolated, monkeypatch):
    calls = []
    def ingest(source, *a, **kw):
        calls.append(source)
        if source == "computrabajo":
            raise SourceFetchError("Forbidden", 403)
        return {"created": 1}
    monkeypatch.setattr("radar.pipeline.run_ingestion", ingest)
    result = capture.run_capture(log=lambda _: None)
    assert calls.count("computrabajo") == 2
    assert calls.count("jobspy") > 2
    assert result["status"] == "partial" and result["skipped"]
    assert result["created"] == len([source for source in calls if source != "computrabajo"])


def test_backup_failure_is_fatal(isolated, monkeypatch):
    monkeypatch.setattr("radar.pipeline.run_ingestion", lambda *a, **kw: {"created": 0})
    def fail():
        raise OSError("backup disk full")
    monkeypatch.setattr("radar.system.backup_database", fail)
    result = capture.run_capture(computrabajo=False, log=lambda _: None)
    assert result["status"] == "failed" and result["maintenance_failed"] == ["backup: sqlite"]


@pytest.mark.parametrize("outcome", ["success", "partial"])
def test_persistent_schedule(isolated, monkeypatch, outcome):
    calls = []
    monkeypatch.setattr(capture, "run_capture", lambda *a: calls.append(True) or {"status": outcome})
    now = datetime(2026, 11, 7, tzinfo=UTC)
    assert scheduled_capture.run_scheduled(now=now)["status"] == outcome
    assert scheduled_capture.run_scheduled(now=now+timedelta(hours=1))["status"] == "skipped"
    assert scheduled_capture.run_scheduled(now=now+timedelta(days=2))["status"] == outcome
    assert len(calls) == 2


def test_failed_backoff_and_lock(isolated, monkeypatch):
    monkeypatch.setattr(capture, "run_capture", lambda *a: {"status": "failed"})
    now = datetime(2026, 11, 7, tzinfo=UTC)
    assert scheduled_capture.run_scheduled(now=now)["status"] == "failed"
    assert scheduled_capture.run_scheduled(now=now+timedelta(minutes=10))["status"] == "skipped"
    with scheduled_capture.capture_lock() as acquired:
        assert acquired
        assert scheduled_capture.run_scheduled(now=now+timedelta(hours=1))["reason"] == "capture already running"


@pytest.mark.parametrize("status,code", [("success", 0), ("partial", 2), ("failed", 1)])
def test_cli_status(isolated, monkeypatch, status, code):
    from radar.cli import main
    monkeypatch.setattr("sys.argv", ["radar", "refresh"])
    monkeypatch.setattr(capture, "run_capture", lambda *a: {"status": status})
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == code


def test_internal_partial_waits_for_interval(isolated, monkeypatch):
    previous=(datetime.now(UTC)-timedelta(days=10)).isoformat()
    set_setting("refresh_last_at", previous)
    monkeypatch.setattr(capture, "run_capture", lambda **kw: {"status": "partial"})
    scheduler._capture()
    assert get_setting("refresh_last_at") == previous
    assert get_setting("refresh_last_status") == "partial"
    assert not scheduler.is_due(datetime.now(UTC)+timedelta(minutes=16))


def test_total_source_failure_is_fatal(isolated, monkeypatch):
    def fail(*args, **kwargs):
        raise SourceFetchError("Forbidden", 403)
    monkeypatch.setattr("radar.pipeline.run_ingestion", fail)
    result = capture.run_capture(log=lambda _: None)
    assert result["status"] == "failed"
    assert result["source_successes"] == 0
    assert not result["maintenance_failed"]


def test_scheduled_capture_includes_enabled_public_portals(monkeypatch):
    monkeypatch.delenv("RADAR_EXTRA_SOURCES", raising=False)
    for flag in ("RADAR_BUMERAN_ENABLED", "RADAR_EMPLEOS_ENABLED"):
        monkeypatch.delenv(flag, raising=False)
    plan = capture.plan_steps([], True, ("analista", "practicante"), ())
    assert [step["source"] for step in plan[:4]] == ["jobspy", "computrabajo", "bumeran", "empleos"]
    monkeypatch.setenv("RADAR_BUMERAN_ENABLED", "0")
    assert "bumeran" not in {s["source"] for s in capture.plan_steps([], True, ("analista",), ())}
    assert {s["source"] for s in capture.plan_steps([], False, ("analista",), (), extra_sources=[])} == {"jobspy"}
