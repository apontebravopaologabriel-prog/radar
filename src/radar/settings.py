"""Ajustes de la aplicación (clave/valor en SQLite) y secretos fuera de la base.

Los ajustes no sensibles viven en `app_settings`. Las claves de API de proveedores de LLM viven en
un archivo `0600` aparte: la base es consultable desde el editor SQL de Análisis y no debe contener
secretos.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from pathlib import Path
from typing import Any

from radar.db.database import connection, database_path

log = logging.getLogger(__name__)


def get_setting(key: str, default: str | None = None) -> str | None:
    with connection() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key=%s", (key,)).fetchone()
    return row[0] if row else default


def set_setting(key: str, value: str | None) -> None:
    with connection() as conn:
        if value is None:
            conn.execute("DELETE FROM app_settings WHERE key=%s", (key,))
        else:
            conn.execute(
                "INSERT INTO app_settings(key,value) VALUES (%s,%s) "
                "ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()",
                (key, value),
            )


def get_json_setting(key: str, default: Any = None) -> Any:
    raw = get_setting(key)
    return json.loads(raw) if raw else default


def set_json_setting(key: str, value: Any) -> None:
    set_setting(key, json.dumps(value, ensure_ascii=False))


def secrets_path() -> Path:
    return database_path().parent / "secrets.json"


def read_secrets() -> dict[str, str]:
    path = secrets_path()
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


KEYRING_SERVICE = "radar"


def _keyring():
    """Módulo `keyring` si se debe usar el almacén del sistema (Credential Manager en Windows), o None.

    `RADAR_SECRETS_BACKEND`: `file` (archivo 0600), `keyring` (almacén del sistema) o `auto` (por defecto: almacén
    del sistema solo en Windows, donde `chmod` no protege un archivo)."""
    choice = os.getenv("RADAR_SECRETS_BACKEND", "auto").lower()
    if choice == "file" or (choice == "auto" and os.name != "nt"):
        return None
    try:
        import keyring
        from keyring.errors import (
            NoKeyringError,  # noqa: F401 - comprueba que la instalación está completa
        )

        return keyring
    except ImportError:
        return None


def _write_file_secret(name: str, value: str | None) -> None:
    secrets = read_secrets()
    if value:
        secrets[name] = value
    else:
        secrets.pop(name, None)
    path = secrets_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(secrets, handle)
    os.chmod(path, 0o600)


def write_secret(name: str, value: str | None) -> None:
    store = _keyring()
    if store is not None:
        try:
            if value:
                store.set_password(KEYRING_SERVICE, name, value)
            else:
                with contextlib.suppress(Exception):  # borrar lo que no existe no es un error
                    store.delete_password(KEYRING_SERVICE, name)
            if name in read_secrets():  # no deja una copia en texto plano
                _write_file_secret(name, None)
            return
        except Exception:
            log.warning("El almacén de credenciales del sistema no está disponible; se usa el archivo protegido", exc_info=True)
    _write_file_secret(name, value)


def read_secret(name: str) -> str | None:
    store = _keyring()
    if store is not None:
        try:
            value = store.get_password(KEYRING_SERVICE, name)
        except Exception:  # noqa: BLE001
            value = None
        if value:
            return value
        legacy = read_secrets().get(name)
        if legacy:  # migra una clave guardada antes en el archivo
            write_secret(name, legacy)
        return legacy
    return read_secrets().get(name)
