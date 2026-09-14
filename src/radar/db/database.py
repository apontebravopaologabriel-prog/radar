from __future__ import annotations

import datetime
import os
import re
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path.home() / ".local/share/radar/radar.db"


def database_path() -> Path:
    raw = os.getenv("RADAR_DB_PATH")
    if raw:
        return Path(raw).expanduser()
    db_url = os.getenv("DATABASE_URL", "")
    if db_url.startswith("sqlite:///"):
        return Path(db_url[len("sqlite:///") :]).expanduser()
    return DEFAULT_DB_PATH


class RadarConnection(sqlite3.Connection):
    """Subclase de conexión SQLite que traduce %s a ? y maneja parámetros."""

    def execute(self, sql: str, parameters: tuple[Any, ...] | list[Any] = ()):
        clean_sql = re.sub(r"(?<!%)(?:%%)*%s", "?", sql)
        return super().execute(clean_sql, parameters)

    def executemany(self, sql: str, seq_of_parameters: Any):
        clean_sql = re.sub(r"(?<!%)(?:%%)*%s", "?", sql)
        return super().executemany(clean_sql, seq_of_parameters)


def _init_sqlite_db(conn: sqlite3.Connection) -> None:
    schema_path = Path(__file__).resolve().parent / "schema_sqlite.sql"
    if schema_path.exists():
        conn.executescript(schema_path.read_text(encoding="utf-8"))


def _configure_connection(conn: RadarConnection) -> None:
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.create_function("gen_random_uuid", 0, lambda: str(uuid.uuid4()))
    conn.create_function("now", 0, lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


@contextmanager
def connection() -> Iterator[RadarConnection]:
    db_file = database_path()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    is_new = not db_file.exists()
    conn = sqlite3.connect(str(db_file), factory=RadarConnection, timeout=10.0)
    _configure_connection(conn)
    if is_new:
        _init_sqlite_db(conn)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
