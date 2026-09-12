from __future__ import annotations

import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from radar.db.queries import (
    applications,
    career_timeline,
    get_profile,
    job_history,
    list_jobs,
    market_history,
    market_summary,
    recommendations,
)
from radar.db.repository import add_career_event, capture_market_snapshot, track_application
from radar.freshness import DEFAULT_MAX_AGE_DAYS
from radar.pipeline import run_ingestion

load_dotenv()
mcp = FastMCP("radar")


@mcp.tool()
def ingest_jobs(
    source: str,
    query: str,
    location: str = "Lima",
    limit: int = 25,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> dict:
    """Busca e importa ofertas. Nunca postula ni modifica el perfil del usuario."""
    if source not in {"computrabajo", "jobspy"}:
        raise ValueError("source debe ser computrabajo o jobspy")
    return run_ingestion(source, query, location, min(limit, 100), max_age_days)


@mcp.tool()
def health() -> dict:
    """Indica que Radar MCP está disponible."""
    return {"status": "ok", "version": "0.1.0"}


@mcp.tool()
def search_saved_jobs(
    limit: int = 20,
    seniority: str | None = None,
    area: str | None = None,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> dict:
    """Consulta ofertas ya guardadas en PostgreSQL."""
    return {"jobs": list_jobs(limit, seniority, area, max_age_days)}


@mcp.tool()
def get_market_summary() -> dict:
    """Devuelve métricas objetivas del mercado almacenado."""
    return market_summary()


@mcp.tool()
def get_user_profile() -> dict:
    """Devuelve el perfil separado de las estadísticas del mercado."""
    return {"profile": get_profile()}


@mcp.tool()
def list_recommended_jobs(
    limit: int = 10, max_age_days: int = DEFAULT_MAX_AGE_DAYS
) -> dict:
    """Devuelve recomendaciones recientes y verificables con enlace directo."""
    return recommendations(limit, max_age_days)


@mcp.tool()
def get_career_timeline(limit: int = 50) -> dict:
    """Devuelve la evolución del perfil y los eventos profesionales registrados."""
    return {"events": career_timeline(limit)}


@mcp.tool()
def get_job_history(job_id: str, limit: int = 20) -> dict:
    """Devuelve observaciones históricas de una oferta sin borrar registros antiguos."""
    return {"job_id": job_id, "observations": job_history(job_id, limit)}


@mcp.tool()
def record_career_event(
    event_type: str,
    title: str,
    description: str | None = None,
    started_on: str | None = None,
    ended_on: str | None = None,
) -> dict:
    """Registra explícitamente un curso, proyecto, empleo, logro o meta profesional."""
    return {"event_id": add_career_event(None, event_type, title, description, started_on, ended_on)}


@mcp.tool()
def capture_market_history(snapshot_date: str | None = None) -> dict:
    """Guarda una fotografía del mercado activo para comparaciones futuras."""
    return {"metrics_saved": capture_market_snapshot(snapshot_date)}


@mcp.tool()
def get_market_history(limit: int = 90) -> dict:
    """Consulta snapshots históricos semanales o mensuales del mercado."""
    return {"snapshots": market_history(limit)}


@mcp.tool()
def track_job_application(job_id: str, status: str = "saved", notes: str | None = None) -> dict:
    """Registra o actualiza una postulación y conserva cada cambio de estado."""
    return {"application_id": track_application(job_id, status, notes)}


@mcp.tool()
def list_job_applications(limit: int = 50) -> dict:
    """Lista postulaciones registradas con su estado y enlace original."""
    return {"applications": applications(limit)}


def main() -> None:
    mcp.run(transport=os.getenv("RADAR_MCP_TRANSPORT", "stdio"))
