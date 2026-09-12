from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg


def database_url() -> str:
    return os.getenv("DATABASE_URL", "postgresql://radar:radar_local_only@localhost:5433/radar")


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    with psycopg.connect(database_url()) as conn:
        yield conn
