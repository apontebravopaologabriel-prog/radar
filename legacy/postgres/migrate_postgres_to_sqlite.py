#!/usr/bin/env python3
"""Migra todos los datos de Radar desde PostgreSQL a SQLite nativo."""

from __future__ import annotations

import datetime
import decimal
import json
import os
import sqlite3
import uuid
from pathlib import Path

import psycopg

SQLITE_PATH = Path(os.getenv("RADAR_DB_PATH", Path.home() / ".local/share/radar/radar.db")).expanduser()
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "src/radar/db/schema_sqlite.sql"
POSTGRES_URL = os.getenv("DATABASE_URL", "postgresql://radar:radar_local_only@localhost:5433/radar")

TABLE_ORDER = [
    "sources",
    "companies",
    "jobs",
    "job_sources",
    "industrial_areas",
    "job_areas",
    "skills",
    "job_skills",
    "user_profile",
    "user_skills",
    "job_scores",
    "job_observations",
    "profile_versions",
    "career_events",
    "applications",
    "application_events",
    "job_user_status",
    "job_user_favorites",
    "market_snapshots",
    "ingestion_runs",
    "job_requirements",
]


def serialize_value(val):
    if val is None:
        return None
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, decimal.Decimal):
        return float(val)
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.isoformat()
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    if isinstance(val, bool):
        return 1 if val else 0
    return val


def main():
    print("Iniciando migración de PostgreSQL a SQLite...")
    print(f"Origen: {POSTGRES_URL}")
    print(f"Destino: {SQLITE_PATH}")

    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SQLITE_PATH.exists():
        backup_path = SQLITE_PATH.with_suffix(f".bak.{int(datetime.datetime.now(datetime.UTC).timestamp())}")
        print(f"Base SQLite existente encontrada. Respaldando a {backup_path}")
        SQLITE_PATH.rename(backup_path)

    pg_conn = psycopg.connect(POSTGRES_URL)
    sqlite_conn = sqlite3.connect(str(SQLITE_PATH))
    sqlite_conn.execute("PRAGMA journal_mode = WAL;")
    sqlite_conn.execute("PRAGMA synchronous = NORMAL;")
    sqlite_conn.execute("PRAGMA foreign_keys = OFF;")  # Temporal durante carga masiva

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    sqlite_conn.executescript(schema_sql)

    total_migrated = 0
    for table in TABLE_ORDER:
        with pg_conn.cursor() as pg_cur:
            pg_cur.execute(f"SELECT * FROM {table};")
            cols = [desc[0] for desc in pg_cur.description]
            rows = pg_cur.fetchall()

        if not rows:
            print(f"  - {table:22}: 0 registros (vacía)")
            continue

        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join([f'"{c}"' for c in cols])
        insert_sql = f'INSERT INTO {table} ({col_names}) VALUES ({placeholders});'

        transformed_rows = []
        for row in rows:
            transformed_rows.append([serialize_value(v) for v in row])

        sqlite_conn.executemany(insert_sql, transformed_rows)
        sqlite_conn.commit()

        # Verificación
        cur = sqlite_conn.execute(f"SELECT count(*) FROM {table};")
        sqlite_count = cur.fetchone()[0]
        assert sqlite_count == len(rows), f"Discrepancia en {table}: PG={len(rows)} vs SQLite={sqlite_count}"
        print(f"  ✓ {table:22}: {len(rows):5d} registros migrados y verificados")
        total_migrated += len(rows)

    sqlite_conn.execute("PRAGMA foreign_keys = ON;")
    sqlite_conn.close()
    pg_conn.close()

    print(f"\n¡Migración completada con éxito! Total registros transferidos: {total_migrated}")
    print(f"Archivo SQLite: {SQLITE_PATH} ({SQLITE_PATH.stat().st_size / (1024*1024):.2f} MB)")


if __name__ == "__main__":
    main()
