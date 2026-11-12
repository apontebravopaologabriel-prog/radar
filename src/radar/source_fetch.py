"""Bound source downloads in disposable processes before database writes."""
from __future__ import annotations

import multiprocessing
import os
import signal
from collections.abc import Callable
from typing import Any


class SourceFetchError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _child(sender, function: Callable, args: tuple) -> None:
    if os.name == "posix":
        os.setsid()
    try:
        sender.send((True, function(*args)))
    except Exception as exc:  # noqa: BLE001 - transport errors to the parent
        response = getattr(exc, "response", None)
        status = getattr(exc, "status_code", None) or getattr(response, "status_code", None) or getattr(exc, "code", None)
        sender.send((False, (str(exc)[:500], status)))
    finally:
        sender.close()


def run_in_process(function: Callable, args: tuple, timeout: float) -> Any:
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_child, args=(sender, function, args))
    try:
        process.start()
    except BaseException:
        receiver.close()
        sender.close()
        raise
    sender.close()
    try:
        if not receiver.poll(timeout):
            raise TimeoutError(f"Source download exceeded {timeout:g} seconds")
        try:
            success, payload = receiver.recv()
        except EOFError as exc:
            raise SourceFetchError("Source worker exited without a result") from exc
        if not success:
            raise SourceFetchError(*payload)
        return payload
    finally:
        receiver.close()
        process.join(timeout=0.2)
        if process.is_alive():
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    process.kill()
            else:
                process.kill()
            process.join()
        process.close()


def _search(source_name: str, query: str, location: str | None, limit: int):
    from radar.pipeline import resolve_source

    return list(resolve_source(source_name).search(query, location, limit))


def fetch_jobs(source_name: str, query: str, location: str | None, limit: int, timeout: float):
    return run_in_process(_search, (source_name, query, location, limit), timeout)
