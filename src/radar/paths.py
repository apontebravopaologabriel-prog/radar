"""Carpetas de Radar según el sistema operativo (Linux, Windows, macOS).

En Linux coinciden con las rutas históricas (`~/.local/share/radar`, `~/.local/state/radar`), así que nada se
mueve. En Windows resultan en `%LOCALAPPDATA%\\radar`. `RADAR_DB_PATH` y `RADAR_STATE_DIR` siguen mandando.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from platformdirs import user_data_dir, user_state_dir

APP = "radar"


def default_data_dir() -> Path:
    return Path(user_data_dir(APP, appauthor=False))


def state_dir() -> Path:
    """Registros (`refresh.log`, `api.log`) y estado desechable."""
    raw = os.getenv("RADAR_STATE_DIR")
    return Path(raw).expanduser() if raw else Path(user_state_dir(APP, appauthor=False))


def frontend_dir() -> Path:
    """Carpeta del export estático del frontend: `RADAR_FRONTEND_DIR`, la del ejecutable empaquetado o la del repo."""
    raw = os.getenv("RADAR_FRONTEND_DIR")
    if raw:
        return Path(raw).expanduser()
    bundle = getattr(sys, "_MEIPASS", None)  # PyInstaller descomprime aquí los datos
    if bundle:
        return Path(bundle) / "frontend_out"
    return Path(__file__).resolve().parent.parent.parent / "frontend/out"
