"""Herramientas de mercado y ofertas de Radar."""

from __future__ import annotations

from radar import __version__, insights
from radar.db.queries import job_history, list_jobs, market_history, recommendations
from radar.db.repository import capture_market_snapshot
from radar.feed import nearby, today_feed
from radar.freshness import DEFAULT_MAX_AGE_DAYS
from radar.links import google_maps_search_url
from radar.pipeline import run_ingestion
from radar.tools_registry import tool


@tool(write=True, chat=False)
def ingest_jobs(
    source: str,
    query: str,
    location: str = "Lima",
    limit: int = 25,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> dict:
    """Busca e importa ofertas. Nunca postula ni modifica el perfil del usuario."""
    if source not in {"computrabajo", "jobspy", "bumeran", "empleos"}:
        raise ValueError("source debe ser computrabajo, jobspy, bumeran o empleos")
    return run_ingestion(source, query, location, min(limit, 100), max_age_days)


@tool(chat=False)
def health() -> dict:
    """Indica que Radar está disponible."""
    return {"status": "ok", "version": __version__}


def _smart_snippet(description: str, search: str | None, default_len: int = 110, match_len: int = 160) -> str:
    """Si hay `search`, centra el extracto en la primera aparición del término buscado (ej. almuerzo, SAP, horario)
    para que el agente vea la evidencia sin llamar a get_job_details en cada oferta."""
    flat = " ".join((description or "").split())
    if not flat:
        return ""
    if not search or not search.strip():
        return flat[:default_len]
    from radar.normalize import normalize_text

    norm_flat = normalize_text(flat)
    terms = [t for t in normalize_text(search).split() if len(t) > 1]
    pos = min((norm_flat.find(t) for t in terms if norm_flat.find(t) >= 0), default=-1)
    if pos < 0:
        return flat[:default_len]
    start = max(0, pos - match_len // 3)
    piece = flat[start : start + match_len]
    return ("…" if start > 0 else "") + piece + ("…" if start + match_len < len(flat) else "")


@tool()
def search_saved_jobs(
    limit: int = 20,
    seniority: str | None = None,
    area: str | None = None,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    search: str | None = None,
    sector: str | None = None,
    exclude_sector: str | None = None,
    include_applied: bool = False,
    include_hidden: bool = False,
) -> dict:
    """Busca ofertas del mercado. Excluye cerradas, postuladas y ocultas. `search`: texto (centra `snippet` en la
    coincidencia dentro de la descripción); `exclude_sector`: sectores separados por coma. Devuelve IDs y enlaces."""
    limit = min(max(limit, 1), 30)
    excluded = [x.strip() for x in (exclude_sector or "").split(",") if x.strip()]
    jobs = list_jobs(
        limit,
        seniority,
        area,
        max_age_days,
        search=search,
        sector=sector,
        exclude_sectors=excluded or None,
        include_applied=include_applied,
        include_hidden=include_hidden,
    )
    slim = []
    for job in jobs:  # sin la descripción completa (≈3 KB por oferta): eso lo da get_job_details
        item = {k: job.get(k) for k in ("id", "title", "company", "location", "seniority", "work_mode", "salary_min",
                                        "salary_max", "salary_currency", "published_at", "primary_area", "sector",
                                        "relevance_tier", "relevance_score", "url", "is_favorite", "user_application")}
        item["snippet"] = _smart_snippet(job.get("description") or job.get("description_clean") or "", search)
        item["google_maps_url"] = google_maps_search_url(job.get("company"), job.get("location"))
        slim.append(item)
    return {"jobs": slim}


@tool(chat=False)
def get_market_summary() -> dict:
    """Devuelve métricas objetivas del mercado almacenado."""
    areas = insights.market_breakdown("area", limit=30)
    demand = insights.skill_demand(limit=30)
    return {"total_active_jobs": areas["total"],
            "by_area": [{"area": r["value"], "job_count": r["jobs"]} for r in areas["rows"]],
            "top_skills": [{"skill": r["skill"], "job_count": r["jobs"]} for r in demand["skills"]]}


@tool(chat=False)
def list_recommended_jobs(
    limit: int = 10,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    include_applied: bool = False,
    include_hidden: bool = False,
) -> dict:
    """Devuelve recomendaciones recientes y verificables con enlace directo. Excluye por defecto postuladas y ocultas."""
    return recommendations(min(max(limit, 1), 20), max_age_days, include_applied=include_applied, include_hidden=include_hidden)


@tool()
def get_today_feed(limit: int = 5) -> dict:
    """Ofertas frescas que encajan con el perfil, con el motivo en una línea. Excluye las ocultas
    o ya gestionadas."""
    return today_feed(limit)


@tool()
def find_jobs_near(
    place: str,
    radius_km: float = 5.0,
    limit: int = 15,
    include_applied: bool = False,
    include_hidden: bool = False,
) -> dict:
    """Ofertas en un radio (km) de un distrito o ciudad por cercanía. Excluye postuladas u ocultas salvo
    `include_applied` o `include_hidden`. En `by_place`, `precision` "district" es distrito real; "city"/"department"
    son ofertas sin distrito específico."""
    return nearby(place, radius_km, limit, include_applied=include_applied, include_hidden=include_hidden)


@tool()
def get_job_details(job_id: str) -> dict:
    """Ficha completa de una oferta: descripción, skills exigidas, salario, ubicación, tu puntaje de
    encaje y tu seguimiento. Los ids salen de search_saved_jobs, get_today_feed o find_jobs_near."""
    return insights.job_details(job_id)


@tool()
def explain_job_fit(job_id: str) -> dict:
    """Desglose del puntaje de encaje de una oferta: aporte de cada dimensión, skills que coinciden y
    las que faltan."""
    return insights.explain_fit(job_id)


@tool()
def compare_jobs(job_ids: list[str]) -> dict:
    """Compara 2 a 4 ofertas: datos clave, encaje, skills comunes y exclusivas de cada una."""
    return insights.compare(job_ids)


@tool()
def get_skill_demand(area: str | None = None, max_age_days: int = 30, limit: int = 15) -> dict:
    """Skills más pedidas por el mercado (nº de ofertas y % del total), con tu nivel en cada una.
    `area` filtra por área primaria."""
    return insights.skill_demand(area, max_age_days, limit)


@tool()
def get_market_breakdown(by: str, max_age_days: int = 14, limit: int = 10, area: str | None = None,
                         place: str | None = None, sector: str | None = None, exclude_sector: str | None = None,
                         search: str | None = None) -> dict:
    """Cuenta ofertas del mercado por area/place/company/work_mode/seniority/sector/source.
    `exclude_sector`: varios con coma. En place, precision city/department no es un distrito."""
    return insights.market_breakdown(by, max_age_days, limit, area, place, sector, exclude_sector, search)


@tool()
def get_place_profile(place: str, max_age_days: int = 30) -> dict:
    """Radiografía de UN distrito o ciudad: nº de ofertas de ese lugar (no del total), áreas, empresas, modalidad,
    seniority, salario mediano y señales de producción. Úsala cuando la persona pregunte por el distrito seleccionado."""
    return insights.place_profile(place, max_age_days)


@tool()
def compare_places(place_a: str, place_b: str, max_age_days: int = 30, focus: str | None = None) -> dict:
    """Compara dos distritos en volumen, áreas, modalidad, seniority, salario mediano y señales de producción.
    `focus` solo resalta un tramo si la persona lo pidió; sin él, la comparación es general."""
    return insights.compare_places(place_a, place_b, max_age_days, focus)


@tool()
def get_salary_stats(area: str | None = None, place: str | None = None, max_age_days: int = 60) -> dict:
    """Mínimo, mediana y máximo de los salarios publicados (solo ofertas que los declaran)."""
    return insights.salary_stats(area, place, max_age_days)


@tool()
def plan_learning(limit: int = 5) -> dict:
    """Skills que más suben tu encaje si las aprendes, con su demanda en el mercado. Base para un plan."""
    return insights.learning_plan(limit)


@tool()
def get_data_schema() -> dict:
    """Tablas y columnas consultables con run_readonly_sql."""
    return insights.data_schema()


@tool()
def run_readonly_sql(sql: str) -> dict:
    """SELECT/WITH, máx. 50 filas; último recurso. Alcance no verificado: no equivale a esta vista.
    Clasificación por mercado: job_market_classifications (job_id,market_id,areas,skills,relevance_tier).
    El error incluye el esquema. Prefiere herramientas de mercado para conteos y vigencia."""
    return {**insights.readonly_sql(sql), "query_scope": "unscoped_sql"}


@tool(chat=False)
def get_skill_impact(limit: int = 8) -> dict:
    """Simula qué skill faltante sube más el encaje si se aprende (nivel básico)."""
    from radar.feed import skill_impact

    return skill_impact(limit)


@tool(chat=False)
def get_job_history(job_id: str, limit: int = 20) -> dict:
    """Devuelve observaciones históricas de una oferta sin borrar registros antiguos."""
    return {"job_id": job_id, "observations": job_history(job_id, limit)}


@tool()
def get_market_history(limit: int = 90) -> dict:
    """Consulta snapshots históricos semanales o mensuales del mercado."""
    return {"snapshots": market_history(min(limit, 90)), "scope": "legacy_reference_snapshots"}


@tool(write=True, chat=False)
def capture_market_history(snapshot_date: str | None = None) -> dict:
    """Guarda una fotografía del mercado activo para comparaciones futuras."""
    return {"metrics_saved": capture_market_snapshot(snapshot_date)}
