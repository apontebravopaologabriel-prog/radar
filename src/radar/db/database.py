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

from radar.paths import default_data_dir
from radar.security import harden_data_dir

# Adaptadores explícitos: los predeterminados están obsoletos desde Python 3.12 (mismo formato).
sqlite3.register_adapter(datetime.datetime, lambda value: value.isoformat(" "))
sqlite3.register_adapter(datetime.date, lambda value: value.isoformat())

DEFAULT_DB_PATH = default_data_dir() / "radar.db"


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
    ("Diseño y medición del trabajo", "diseno-medicion-trabajo"),
    ("Investigación de operaciones y optimización", "investigacion-operaciones-optimizacion"),
    ("Ingeniería económica y control", "ingenieria-economica-control"),
    ("Facilities, energía y mantenimiento", "facilities-energia-mantenimiento"),
    ("Calidad y confiabilidad", "calidad-confiabilidad"),
    ("Ergonomía y factores humanos", "ergonomia-factores-humanos"),
    ("Operaciones y productividad", "operaciones-productividad"),
    ("Supply Chain, logística y compras", "supply-chain-logistica-compras"),
    ("Ingeniería de gestión y proyectos", "ingenieria-gestion-proyectos"),
    ("Seguridad y riesgos", "seguridad-riesgos"),
    ("Información, analítica y sistemas", "informacion-analitica-sistemas"),
    ("Diseño y manufactura", "diseno-manufactura"),
    ("Diseño de producto y desarrollo", "diseno-producto-desarrollo"),
    ("Ingeniería de sistemas", "ingenieria-sistemas"),
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


def _pack_areas() -> list[tuple[str, str]]:
    from radar.careers import list_packs

    return [(name, slug) for pack in list_packs() for name, slug in pack.area_slugs.items()]


def _pack_skills() -> list[tuple[str, str, str | None, str]]:
    from radar.careers import list_packs

    return [
        (name, name.lower().replace(" ", "-"), skill.category, skill.type)
        for pack in list_packs()
        for name, skill in pack.skills.items()
    ]


def _schema_section(start_marker: str, end_marker: str) -> str:
    """Tramo del esquema que las bases ya creadas deben recibir de forma aditiva (una sola fuente: schema_sqlite.sql)."""
    text = (Path(__file__).resolve().parent / "schema_sqlite.sql").read_text(encoding="utf-8")
    start = text.index(start_marker)
    return text[start : text.index(end_marker, start)]


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
    # Sin este índice cada oferta escaneaba toda la tabla job_sources (4 s por consulta con ~2 000 ofertas).
    conn.execute("CREATE INDEX IF NOT EXISTS job_sources_job_seen_idx ON job_sources (job_id, last_seen_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS job_scores_profile_idx ON job_scores (profile_id, total_score DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS applications_job_idx ON applications (job_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS jobs_relevance_idx ON jobs (relevance_tier, relevance_score DESC, is_active)")
    conn.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT (now()))")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS agent_usage (id TEXT PRIMARY KEY DEFAULT (gen_random_uuid()), provider TEXT NOT NULL, "
        "model TEXT NOT NULL, prompt_tokens INTEGER NOT NULL DEFAULT 0, completion_tokens INTEGER NOT NULL DEFAULT 0, "
        "created_at TEXT NOT NULL DEFAULT (now()))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY DEFAULT (gen_random_uuid()), title TEXT NOT NULL, "
        "data TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (now()), updated_at TEXT NOT NULL DEFAULT (now()))"
    )
    conn.execute("CREATE TABLE IF NOT EXISTS agent_memories (id TEXT PRIMARY KEY DEFAULT (gen_random_uuid()), topic_key TEXT NOT NULL UNIQUE, memory_type TEXT NOT NULL DEFAULT 'preference', content TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'user', confidence REAL NOT NULL DEFAULT 1.0, is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT (now()), updated_at TEXT NOT NULL DEFAULT (now()), last_confirmed_at TEXT)")
    conn.execute("CREATE INDEX IF NOT EXISTS agent_memories_active_idx ON agent_memories (is_active, updated_at DESC)")
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS agent_memories_fts USING fts5(topic_key, content, content='agent_memories', content_rowid='rowid')")
    conn.execute("CREATE TRIGGER IF NOT EXISTS agent_memories_ai AFTER INSERT ON agent_memories BEGIN INSERT INTO agent_memories_fts(rowid, topic_key, content) VALUES (new.rowid, new.topic_key, new.content); END")
    conn.execute("CREATE TRIGGER IF NOT EXISTS agent_memories_ad AFTER DELETE ON agent_memories BEGIN INSERT INTO agent_memories_fts(agent_memories_fts, rowid, topic_key, content) VALUES ('delete', old.rowid, old.topic_key, old.content); END")
    conn.execute("CREATE TRIGGER IF NOT EXISTS agent_memories_au AFTER UPDATE ON agent_memories BEGIN INSERT INTO agent_memories_fts(agent_memories_fts, rowid, topic_key, content) VALUES ('delete', old.rowid, old.topic_key, old.content); INSERT INTO agent_memories_fts(rowid, topic_key, content) VALUES (new.rowid, new.topic_key, new.content); END")
    conn.executescript(_schema_section("-- CV Studio", "CREATE TABLE IF NOT EXISTS market_snapshots"))
    conn.executemany(
        "INSERT INTO industrial_areas(name, slug) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        _CATALOG_AREAS + _pack_areas(),
    )
    conn.executemany(
        "INSERT INTO skills(name, normalized_name, category, skill_type) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
        _CATALOG_SKILLS + _pack_skills(),
    )
    conn.executemany(
        "INSERT INTO sources(name, source_type, base_url) VALUES (%s, %s, %s) ON CONFLICT(name) DO NOTHING",
        _CATALOG_SOURCES,
    )


_SCHEMA_READY: set[str] = set()


def _configure_connection(conn: RadarConnection) -> None:
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA cache_size = -32768;")  # 32 MB de caché de páginas
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA mmap_size = 268435456;")  # lecturas por memoria mapeada (256 MB)
    conn.create_function("gen_random_uuid", 0, lambda: str(uuid.uuid4()))
    conn.create_function("now", 0, lambda: datetime.datetime.now(datetime.UTC).isoformat())


@contextmanager
def connection() -> Iterator[RadarConnection]:
    db_file = database_path()
    created_dir = not db_file.parent.exists()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    is_new = not db_file.exists()
    conn = sqlite3.connect(str(db_file), factory=RadarConnection, timeout=10.0)
    _configure_connection(conn)
    key = str(db_file)
    if is_new:
        _init_sqlite_db(conn)
        _SCHEMA_READY.discard(key)
    if key not in _SCHEMA_READY:  # las garantías del esquema se aplican una vez por proceso y base
        _ensure_runtime_schema(conn)
        _SCHEMA_READY.add(key)
        harden_data_dir(db_file, owned_dir=created_dir or db_file.parent == DEFAULT_DB_PATH.parent)
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
