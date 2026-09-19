"""Read-only SQL console used by the frontend's analysis terminal.

Every query here runs against a connection opened with SQLite's `mode=ro`
URI flag, so writes fail at the OS/driver level regardless of what the SQL
text says. The text validation below is a second, independent layer: it
rejects anything that isn't a single SELECT/WITH statement before the query
ever reaches SQLite, and a progress handler aborts anything that runs too
long (e.g. an accidental cross join over a large table).
"""

from __future__ import annotations

import re
import sqlite3
import time
from typing import Any

from .database import readonly_connection

MAX_ROWS = 500
QUERY_TIMEOUT_SECONDS = 5.0

_ALLOWED_START = re.compile(r"^\s*(with|select)\b", re.IGNORECASE)
_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(insert|update|delete|drop|alter|attach|detach|pragma|vacuum|replace|create|reindex)\b",
    re.IGNORECASE,
)
_HAS_LIMIT = re.compile(r"\blimit\b", re.IGNORECASE)
_LINE_COMMENT = re.compile(r"--[^\n]*")

# Whitelisted so PRAGMA table_info(...) never receives untrusted input.
SCHEMA_TABLES = [
    "jobs",
    "companies",
    "industrial_areas",
    "job_areas",
    "skills",
    "job_skills",
    "sources",
    "job_sources",
    "user_profile",
    "user_skills",
    "market_snapshots",
]


class QueryError(ValueError):
    """The query was rejected before or during execution."""


class QueryTimeout(QueryError):
    """The query ran longer than QUERY_TIMEOUT_SECONDS and was cancelled."""


def _validate(sql: str) -> str:
    stripped = sql.strip()
    if stripped.endswith(";"):
        stripped = stripped[:-1].rstrip()
    if not stripped:
        raise QueryError("La consulta está vacía.")
    # SQLite executes '-- ...' comments fine on its own; they're stripped
    # here only so a leading comment (e.g. a hint like "cambia 'Python' por
    # tu skill") doesn't fail the SELECT/WITH check or trip a false keyword
    # match inside the comment text itself.
    without_comments = _LINE_COMMENT.sub("", stripped).strip()
    if ";" in without_comments:
        raise QueryError("Solo se permite una consulta a la vez (sin ';' en el medio).")
    if not _ALLOWED_START.match(without_comments):
        raise QueryError("Solo se permiten consultas SELECT o WITH.")
    if _FORBIDDEN_KEYWORDS.search(without_comments):
        raise QueryError("La consulta contiene una palabra clave no permitida.")
    return stripped


def _apply_row_cap(sql: str, max_rows: int) -> str:
    if _HAS_LIMIT.search(sql):
        return sql
    return f"{sql}\nLIMIT {max_rows}"


def run_readonly_query(sql: str, max_rows: int = MAX_ROWS) -> dict[str, Any]:
    clean = _validate(sql)
    bounded = _apply_row_cap(clean, max_rows)
    started = time.perf_counter()

    with readonly_connection() as conn:
        def _check_deadline() -> int:
            return 1 if (time.perf_counter() - started) > QUERY_TIMEOUT_SECONDS else 0

        conn.set_progress_handler(_check_deadline, 10_000)
        try:
            cursor = conn.execute(bounded)
            rows = cursor.fetchmany(max_rows + 1)
            columns = [description[0] for description in cursor.description] if cursor.description else []
        except sqlite3.OperationalError as exc:
            if "interrupted" in str(exc).lower():
                raise QueryTimeout("La consulta tardó demasiado y fue cancelada.") from exc
            raise QueryError(str(exc)) from exc
        finally:
            conn.set_progress_handler(None, 0)

    truncated = len(rows) > max_rows
    if truncated:
        rows = rows[:max_rows]
    return {
        "columns": columns,
        "rows": [list(row) for row in rows],
        "row_count": len(rows),
        "truncated": truncated,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
    }


def describe_schema() -> dict[str, Any]:
    tables: list[dict[str, Any]] = []
    with readonly_connection() as conn:
        for name in SCHEMA_TABLES:
            try:
                cursor = conn.execute(f"PRAGMA table_info({name})")
            except sqlite3.OperationalError:
                continue
            columns = [{"name": row[1], "type": row[2]} for row in cursor.fetchall()]
            if columns:
                tables.append({"table": name, "columns": columns})
    return {"tables": tables}
