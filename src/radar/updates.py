"""Non-blocking UI release checks against the fixed public Radar repository."""
from __future__ import annotations

import re
import threading
import time

import httpx

from radar import __version__

RELEASE_URL = "https://github.com/apontebravopaologabriel-prog/radar/releases/latest"
API_URL = "https://api.github.com/repos/apontebravopaologabriel-prog/radar/releases/latest"
_lock = threading.Lock()
_cached: dict = {}
_checked_at = 0.0


def version(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", value)
    return tuple(map(int, match.groups())) if match else None


def check() -> dict:
    global _cached, _checked_at
    with _lock:
        if _cached and time.monotonic()-_checked_at < 86400:
            return _cached
        result = {"current": __version__, "available": False, "url": RELEASE_URL}
        try:
            response = httpx.get(API_URL, timeout=4, follow_redirects=False, headers={"Accept": "application/vnd.github+json"})
            response.raise_for_status()
            release = response.json()
            tag = release.get("tag_name", "")
            latest, current = version(tag), version(__version__)
            if latest and current and not release.get("draft") and not release.get("prerelease"):
                result.update(latest=tag, available=latest>current)
        except (httpx.HTTPError, ValueError, TypeError):
            result["status"] = "unavailable"
        _cached, _checked_at = result, time.monotonic()
        return result
