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


_CATALOG_AREAS = [
    ("Operaciones", "operaciones"),
    ("Producción", "produccion"),
    ("Mejora continua", "mejora-continua"),
    ("Procesos", "procesos"),
    ("Supply Chain", "supply-chain"),
    ("Logística", "logistica"),
    ("Compras", "compras"),
    ("Planeamiento", "planeamiento"),
    ("Demand Planning", "demand-planning"),
    ("Calidad", "calidad"),
    ("Data / BI", "data-bi"),
    ("Analytics", "analytics"),
    ("Automatización", "automatizacion"),
    ("Mantenimiento", "mantenimiento"),
    ("Proyectos / PMO", "proyectos-pmo"),
    ("Finanzas / Control de gestión", "finanzas-control"),
    ("Seguridad y Salud en el Trabajo", "sst"),
    ("Recursos Humanos / People Analytics", "rrhh-people-analytics"),
    ("Otras", "otras"),
    ("Ventas / Comercial", "ventas-comercial"),
]

_CATALOG_SKILLS = [
    ("Excel", "excel", "herramienta", "technical"),
    ("Power BI", "power-bi", "bi", "technical"),
    ("SQL", "sql", "datos", "technical"),
    ("Python", "python", "datos", "technical"),
    ("PostgreSQL", "postgresql", "datos", "technical"),
    ("SAP", "sap", "erp", "technical"),
    ("RPA", "rpa", "automatizacion", "technical"),
    ("Power Automate", "power-automate", "automatizacion", "technical"),
    ("Tableau", "tableau", "bi", "technical"),
    ("OR-Tools", "or-tools", "analitica", "technical"),
    ("S&OP", "s-op", "planeamiento", "technical"),
    ("English", "english", "idioma", "language"),
    ("Lean", "lean", "mejora", "methodology"),
    ("Six Sigma", "six-sigma", "calidad", "methodology"),
    ("Kaizen", "kaizen", "mejora", "methodology"),
    ("VSM", "vsm", "mejora", "methodology"),
    ("5S", "5s", "mejora", "methodology"),
    ("BPMN", "bpmn", "procesos", "methodology"),
    ("Project Management", "project-management", "proyectos", "methodology"),
    ("Scrum", "scrum", "proyectos", "methodology"),
    ("Forecasting", "forecasting", "planeamiento", "domain"),
    ("Optimization", "optimization", "analitica", "domain"),
    ("Supply Chain", "supply-chain", "supply-chain", "domain"),
    ("Inventory Management", "inventory-management", "supply-chain", "domain"),
    ("Demand Planning", "demand-planning", "planeamiento", "domain"),
    ("Comunicación", "comunicacion", "habilidad", "soft"),
    ("Trabajo en equipo", "trabajo-en-equipo", "habilidad", "soft"),
    ("Pensamiento analítico", "pensamiento-analitico", "habilidad", "soft"),
    ("Resolución de problemas", "resolucion-de-problemas", "habilidad", "soft"),
    ("Liderazgo", "liderazgo", "habilidad", "soft"),
    ("Adaptabilidad", "adaptabilidad", "habilidad", "soft"),
    ("Negociación", "negociacion", "habilidad", "soft"),
    ("Proactividad", "proactividad", "habilidad", "soft"),
    ("Atención al detalle", "atencion-al-detalle", "habilidad", "soft"),
    ("Orientación al cliente", "orientacion-al-cliente", "habilidad", "soft"),
    ("Toma de decisiones", "toma-de-decisiones", "habilidad", "soft"),
    ("Colaboración", "colaboracion", "habilidad", "soft"),
]

_CATALOG_SOURCES = [
    ("Computrabajo", "mcp", "https://www.computrabajo.com.pe"),
    ("JobSpy/Indeed", "library", "https://www.indeed.com"),
]


def _ensure_runtime_schema(conn: sqlite3.Connection) -> None:
    """Apply small additive guarantees to databases created before migrations."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    if "relevance_tier" not in columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN relevance_tier TEXT NOT NULL DEFAULT 'out_of_focus'")
    if "relevance_score" not in columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN relevance_score REAL NOT NULL DEFAULT 0")
    if "relevance_evidence" not in columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN relevance_evidence TEXT")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS jobs_fingerprint_unique_idx ON jobs (canonical_fingerprint)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS job_areas_one_primary_idx ON job_areas (job_id) WHERE is_primary = 1")
    conn.execute("CREATE INDEX IF NOT EXISTS jobs_relevance_idx ON jobs (relevance_tier, relevance_score DESC, is_active)")
    conn.executemany(
        "INSERT INTO industrial_areas(name, slug) VALUES (%s, %s) ON CONFLICT(name) DO NOTHING",
        _CATALOG_AREAS,
    )
    conn.executemany(
        "INSERT INTO skills(name, normalized_name, category, skill_type) VALUES (%s, %s, %s, %s) ON CONFLICT(name) DO NOTHING",
        _CATALOG_SKILLS,
    )
    conn.executemany(
        "INSERT INTO sources(name, source_type, base_url) VALUES (%s, %s, %s) ON CONFLICT(name) DO NOTHING",
        _CATALOG_SOURCES,
    )


def _configure_connection(conn: RadarConnection) -> None:
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.create_function("gen_random_uuid", 0, lambda: str(uuid.uuid4()))
    conn.create_function("now", 0, lambda: datetime.datetime.now(datetime.UTC).isoformat())


@contextmanager
def connection() -> Iterator[RadarConnection]:
    db_file = database_path()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    is_new = not db_file.exists()
    conn = sqlite3.connect(str(db_file), factory=RadarConnection, timeout=10.0)
    _configure_connection(conn)
    if is_new:
        _init_sqlite_db(conn)
    _ensure_runtime_schema(conn)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


@contextmanager
def readonly_connection() -> Iterator[sqlite3.Connection]:
    """Open the database strictly read-only, for ad-hoc analytics queries.

    Uses SQLite's URI mode=ro so the connection itself refuses writes at the
    OS level, independent of any SQL-text validation the caller has done.
    """
    db_file = database_path()
    conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True, timeout=5.0)
    try:
        yield conn
    finally:
        conn.close()
