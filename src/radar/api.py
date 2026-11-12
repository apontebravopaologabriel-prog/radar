from __future__ import annotations

import os
import sqlite3
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.gzip import GZipMiddleware

from radar import __version__
from radar.analysis import AnalysisScope, Dimension, matching_jobs
from radar.analysis import router as analysis_router
from radar.api_agent import router as agent_router
from radar.api_cv import router as cv_router
from radar.api_mcp import router as mcp_router
from radar.api_me import router as me_router
from radar.auth import AccessMiddleware
from radar.auth import router as auth_router
from radar.db.analytics import QueryError, QueryTimeout, describe_schema, run_readonly_query
from radar.db.queries import (
    get_job,
    get_profile,
    list_applied_jobs,
    list_favorite_jobs,
    list_hidden_jobs,
    list_jobs,
    market_history,
    market_summary,
    remove_job_favorite,
    set_job_favorite,
    set_job_user_status,
    skill_history,
    skill_overview,
)
from radar.paths import frontend_dir
from radar.processes import router as processes_router
from radar.security import LocalGuardMiddleware, restrict_umask

FRONTEND_OUT = frontend_dir()

@asynccontextmanager
async def _lifespan(_: FastAPI):
    from radar import scheduler

    scheduler.start()  # solo si no hay temporizador de systemd (Windows, macOS, instalador)
    yield
    scheduler.stop()


app = FastAPI(title="Radar Career Intelligence API", version=__version__, lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("RADAR_API_ALLOW_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://127.0.0.1:8100").split(","),
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["*"],
)

class _SelectiveGZip(GZipMiddleware):
    """Comprime las respuestas grandes (listas de ofertas ~6 MB) sin tocar el streaming del chat."""

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith("/api/chat"):
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


app.add_middleware(_SelectiveGZip, minimum_size=1024, compresslevel=5)
app.add_middleware(AccessMiddleware)
app.add_middleware(LocalGuardMiddleware)
app.include_router(auth_router)
app.include_router(cv_router)
app.include_router(me_router)
app.include_router(mcp_router)
app.include_router(agent_router)
app.include_router(processes_router)

if FRONTEND_OUT.exists():
    next_dir = FRONTEND_OUT / "_next"
    if next_dir.exists():
        app.mount("/_next", StaticFiles(directory=str(next_dir)), name="next_static")

    maplibre_dir = FRONTEND_OUT / "maplibre"  # worker de MapLibre (ver frontend/scripts/copy-maplibre-worker.mjs)
    if maplibre_dir.exists():
        app.mount("/maplibre", StaticFiles(directory=str(maplibre_dir)), name="maplibre_worker")

    @app.get("/radar", include_in_schema=False)
    @app.get("/radar/", include_in_schema=False)
    def serve_radar_ui():
        # The HTML shell must always revalidate: it references content-hashed
        # /_next/static assets that are replaced (not versioned) on every build,
        # so a cached stale shell can point at files that no longer exist.
        headers = {"Cache-Control": "no-cache"}
        radar_html = FRONTEND_OUT / "radar.html"
        if radar_html.exists():
            return FileResponse(str(radar_html), headers=headers)
        return FileResponse(str(FRONTEND_OUT / "index.html"), headers=headers)

    @app.get("/ajustes", include_in_schema=False)
    @app.get("/ajustes/", include_in_schema=False)
    def serve_settings_ui():
        return FileResponse(str(FRONTEND_OUT / "ajustes.html"), headers={"Cache-Control": "no-cache"})

    _ROOT_ASSETS = {
        "manifest.webmanifest": "application/manifest+json",
        "icon-180.png": "image/png",
        "icon-192.png": "image/png",
        "icon-512.png": "image/png",
    }

    @app.get("/{asset_name}", include_in_schema=False)
    def serve_root_asset(asset_name: str):
        media_type = _ROOT_ASSETS.get(asset_name)
        path = FRONTEND_OUT / asset_name
        if media_type is None or not path.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(str(path), media_type=media_type, headers={"Cache-Control": "no-cache"})

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse(url="/radar")


def _slimmed(job: dict[str, Any], slim: bool) -> dict[str, Any]:
    if slim:
        job["has_description"] = bool(job.get("description"))
        job.pop("description", None)
    return job


def _with_location(job: dict[str, Any]) -> dict[str, Any]:
    from radar.geolocation import with_location

    return with_location(job)

class JobFields(BaseModel):
    id: str
    title: str
    company: str | None
    location: str | None
    seniority: str | None
    work_mode: str | None
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    url: str | None
    published_at: str | None
    primary_area: str | None
    sector: str | None
    relevance_tier: str
    relevance_score: float
    relevance_evidence: str | None
    hours_per_week: float | None
    schedule_text: str | None
    application_status: str
    application_checked_at: str | None
    user_status: str
    user_reason: str | None
    is_favorite: bool
    user_application: str | None
    latitude: float | None
    longitude: float | None
    district: str | None
    place_id: str | None
    location_precision: str
    location_confidence: float
    geocoding_source: str | None


class SlimJob(JobFields):
    has_description: bool


class FullJob(JobFields):
    description: str | None


class JobPage(BaseModel):
    jobs: list[SlimJob | FullJob]
    total: int
    offset: int


class FullJobList(BaseModel):
    jobs: list[FullJob]
    total: int


class JobById(BaseModel):
    job: SlimJob


class JobDescription(BaseModel):
    id: str
    description: str | None


class JobMapPoint(BaseModel):
    type: Literal["Point"]
    coordinates: tuple[float, float]


class JobMapFeature(BaseModel):
    type: Literal["Feature"]
    geometry: JobMapPoint
    properties: SlimJob | FullJob


class JobMap(BaseModel):
    type: Literal["FeatureCollection"]
    features: list[JobMapFeature]
    total: int
    mapped: int


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}

app.include_router(analysis_router)


class AnalysisOffersScope(AnalysisScope):
    dimension: Dimension | None = None
    value: str | None = None
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


@app.get("/api/analytics/offers", response_model=JobPage)
def analysis_offers(
    scope: Annotated[AnalysisOffersScope, Query()],
):
    base = AnalysisScope.model_validate(scope.model_dump(exclude={"dimension", "value", "limit", "offset"}))
    rows = matching_jobs(base, scope.dimension, scope.value)
    return {"jobs": [_slimmed(dict(row), True) for row in rows[scope.offset:scope.offset + scope.limit]],
            "total": len(rows), "offset": scope.offset}


@app.get("/api/jobs", response_model=JobPage)
def jobs(
    geo_scope: str | None = Query(default=None, pattern="^lima_callao$"),
    market_id: str | None = None,
    profile_mode: str = Query(default="market", pattern="^(market|saved)$"),
    search: str | None = None,
    seniority: str | None = None,
    area: str | None = None,
    work_mode: str | None = None,
    source: str | None = None,
    skill: str | None = None,
    relevance_tier: str | None = None,
    min_salary: Annotated[float | None, Query(ge=0)] = None,
    max_salary: Annotated[float | None, Query(ge=0)] = None,
    max_age_days: int = Query(default=14, ge=1, le=365),
    include_hidden: bool = False,
    include_applied: bool = True,
    slim: bool = False,
    limit: int | None = Query(default=None, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Sin `limit` devuelve todo (lo que usa el mapa); con `limit`/`offset` pagina y `total` sigue siendo el conteo completo."""
    if min_salary is not None and max_salary is not None and min_salary > max_salary:
        raise HTTPException(422, "El mínimo no puede superar el máximo")
    if profile_mode == "saved" and not market_id:
        raise HTTPException(status_code=422, detail="El perfil necesita un mercado")
    if market_id:
        from radar.careers import CareerPackError, load_pack

        try:
            load_pack(market_id)
        except CareerPackError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    rows = list_jobs(
        limit=None,
        market_id=market_id,
        geo_scope=geo_scope,
        profile_mode=profile_mode,
        seniority=seniority,
        area=area,
        max_age_days=max_age_days,
        search=search,
        work_mode=work_mode,
        min_salary=min_salary,
        max_salary=max_salary,
        include_hidden=include_hidden,
        include_applied=include_applied,
        source=source,
        skill=skill,
        relevance_tier=relevance_tier,
    )
    page = rows[offset : offset + limit] if limit is not None else rows[offset:]
    return {"jobs": [_slimmed(_with_location(row), slim) for row in page], "total": len(rows), "offset": offset}


@app.get("/api/jobs/{job_id}/description", response_model=JobDescription)
def job_description(job_id: str) -> dict[str, Any]:
    """Descripción completa de una oferta; los listados con `slim=1` no la incluyen (pesa ~80 % del payload)."""
    from radar.db.database import connection

    with connection() as conn:
        row = conn.execute("SELECT description_clean FROM jobs WHERE id=%s", (job_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Oferta no encontrada")
    return {"id": job_id, "description": row[0]}


@app.get("/api/map/jobs", response_model=JobMap)
def map_jobs(
    search: str | None = None,
    seniority: str | None = None,
    area: str | None = None,
    work_mode: str | None = None,
    source: str | None = None,
    relevance_tier: str | None = None,
    min_salary: Annotated[float | None, Query(ge=0)] = None,
    max_salary: Annotated[float | None, Query(ge=0)] = None,
    max_age_days: int = Query(default=14, ge=1, le=365),
    slim: bool = False,
) -> dict[str, Any]:
    if min_salary is not None and max_salary is not None and min_salary > max_salary:
        raise HTTPException(422, "El mínimo no puede superar el máximo")
    rows = list_jobs(
        limit=None,
        seniority=seniority,
        area=area,
        max_age_days=max_age_days,
        search=search,
        work_mode=work_mode,
        min_salary=min_salary,
        max_salary=max_salary,
        source=source,
        relevance_tier=relevance_tier,
    )
    features = []
    for row in rows:
        item = _slimmed(_with_location(row), slim)
        if item["latitude"] is None or item["longitude"] is None:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [item["longitude"], item["latitude"]]},
                "properties": item,
            }
        )
    return {"type": "FeatureCollection", "features": features, "total": len(rows), "mapped": len(features)}


@app.get("/api/market/summary")
def market() -> dict[str, Any]:
    return market_summary()


@app.get("/api/market/history")
def history(limit: int = Query(default=90, ge=1, le=500)) -> dict[str, Any]:
    return {"snapshots": market_history(limit)}


@app.get("/api/profile")
def profile() -> dict[str, Any]:
    return {"profile": get_profile()}


@app.get("/api/skills/overview")
def skills_overview(
    geo_scope: str | None = Query(default=None, pattern="^lima_callao$"),
    market_id: str | None = None,
    profile_mode: str = Query(default="market", pattern="^(market|saved)$"),
    relevance_tier: str | None = None,
    search: str | None = None,
    source: str | None = None,
    min_salary: Annotated[float | None, Query(ge=0)] = None,
    max_salary: Annotated[float | None, Query(ge=0)] = None,
    max_age_days: int = Query(default=30, ge=1, le=365),
    area: str | None = None,
    seniority: str | None = None,
    work_mode: str | None = None,
    include_applied: bool = True,
) -> dict[str, Any]:
    if min_salary is not None and max_salary is not None and min_salary > max_salary:
        raise HTTPException(422, "El mínimo no puede superar el máximo")
    if profile_mode == "saved" and not market_id:
        raise HTTPException(status_code=422, detail="El perfil necesita un mercado")
    if market_id:
        from radar.careers import CareerPackError
        from radar.markets import market_skills

        try:
            return market_skills(market_id, geo_scope=geo_scope, max_age_days=max_age_days, area=area, seniority=seniority,
                                 work_mode=work_mode, profile_mode=profile_mode, relevance_tier=relevance_tier,
                                 search=search, source=source, min_salary=min_salary, max_salary=max_salary, include_applied=include_applied)
        except CareerPackError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return skill_overview(max_age_days=max_age_days, area=area, seniority=seniority, work_mode=work_mode,
                          include_applied=include_applied)


@app.get("/api/skills/history")
def skills_history(limit: int = Query(default=180, ge=1, le=2000)) -> dict[str, Any]:
    return {"snapshots": skill_history(limit)}


class JobStatusUpdate(BaseModel):
    status: str = Field(pattern="^(visible|hidden)$")
    reason: str | None = Field(default=None, pattern="^(closed|not_interested|applied|duplicate|other)$")
    note: str | None = Field(default=None, max_length=1000)


@app.get("/api/jobs/hidden", response_model=FullJobList)
def hidden_jobs() -> dict[str, Any]:
    rows = list_hidden_jobs()
    return {"jobs": [_with_location(row) for row in rows], "total": len(rows)}


@app.get("/api/jobs/favorites", response_model=FullJobList)
def favorite_jobs() -> dict[str, Any]:
    rows = list_favorite_jobs()
    return {"jobs": [_with_location(row) for row in rows], "total": len(rows)}


@app.get("/api/jobs/applied", response_model=FullJobList)
def applied_jobs() -> dict[str, Any]:
    rows = list_applied_jobs()
    return {"jobs": [_with_location(row) for row in rows], "total": len(rows)}


class JobUrlImport(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    title: str | None = Field(default=None, max_length=300)
    company: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=30000)
    favorite: bool = False
    application_status: str | None = Field(
        default=None, pattern="^(saved|applied|responded|interview|offer|rejected|ignored|visible)$"
    )
    notes: str | None = Field(default=None, max_length=1000)


@app.post("/api/jobs/import-url")
def import_job_by_url(payload: JobUrlImport) -> dict[str, Any]:
    """Importa una sola oferta desde su URL pública, calcula su encaje y opcionalmente registra seguimiento."""
    from radar.security import UnsafeUrlError
    from radar.single_import import fetch_and_ingest_single_job

    try:
        return fetch_and_ingest_single_job(
            payload.url,
            title=payload.title,
            company=payload.company,
            location=payload.location,
            description=payload.description,
            favorite=payload.favorite,
            application_status=payload.application_status,
            notes=payload.notes,
        )
    except (ValueError, UnsafeUrlError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/jobs/{job_id}", response_model=JobById)
def job_by_id(job_id: str) -> dict[str, Any]:
    """Una oferta por id: lo usa el chat para abrir en el mapa una oferta que no está en la vista actual."""
    row = get_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Oferta no encontrada")
    return {"job": _slimmed(_with_location(row), True)}


@app.put("/api/jobs/{job_id}/favorite")
def add_favorite(job_id: str) -> dict[str, bool]:
    try:
        set_job_favorite(job_id)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=404, detail="Oferta no encontrada") from exc
    return {"is_favorite": True}


@app.delete("/api/jobs/{job_id}/favorite")
def delete_favorite(job_id: str) -> dict[str, bool]:
    remove_job_favorite(job_id)
    return {"is_favorite": False}


@app.patch("/api/jobs/{job_id}/status")
def update_job_status(job_id: str, payload: JobStatusUpdate) -> dict[str, str]:
    try:
        set_job_user_status(job_id, payload.status, payload.reason, payload.note)
        if payload.status == "hidden" and payload.reason == "applied":
            from radar.db.repository import track_application

            track_application(job_id, "applied", payload.note)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=404, detail="Oferta no encontrada") from exc
    return {"status": payload.status}


class AnalyticsQueryRequest(BaseModel):
    sql: str = Field(min_length=1, max_length=4000)


@app.post("/api/analytics/query")
def analytics_query(payload: AnalyticsQueryRequest) -> dict[str, Any]:
    try:
        return run_readonly_query(payload.sql)
    except QueryTimeout as exc:
        raise HTTPException(status_code=408, detail=str(exc)) from exc
    except QueryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/analytics/schema")
def analytics_schema() -> dict[str, Any]:
    return describe_schema()


def main() -> None:
    from multiprocessing import freeze_support

    freeze_support()
    restrict_umask()
    uvicorn.run(
        "radar.api:app",
        host=os.getenv("RADAR_API_HOST", "127.0.0.1"),
        port=int(os.getenv("RADAR_API_PORT", "8100")),
        reload=False,
    )


if __name__ == "__main__":
    main()
