from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from radar.api_agent import router as agent_router
from radar.auth import AccessMiddleware
from radar.auth import router as auth_router
from radar.api_cv import router as cv_router
from radar.db.analytics import QueryError, QueryTimeout, describe_schema, run_readonly_query
from radar.db.queries import (
    get_profile,
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
from radar.geolocation import infer_location

FRONTEND_OUT = Path(__file__).resolve().parent.parent.parent / "frontend/out"

app = FastAPI(title="Radar Career Intelligence API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("RADAR_API_ALLOW_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://127.0.0.1:8100").split(","),
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["*"],
)

app.add_middleware(AccessMiddleware)
app.include_router(auth_router)
app.include_router(cv_router)
app.include_router(agent_router)

if FRONTEND_OUT.exists():
    next_dir = FRONTEND_OUT / "_next"
    if next_dir.exists():
        app.mount("/_next", StaticFiles(directory=str(next_dir)), name="next_static")

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

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse(url="/radar")


def _with_location(job: dict[str, Any]) -> dict[str, Any]:
    point = infer_location(job.get("location"))
    result = dict(job)
    result["latitude"] = point.latitude if point else None
    result["longitude"] = point.longitude if point else None
    result["district"] = point.label if point and point.precision == "district" else None
    result["location_precision"] = point.precision if point else "unknown"
    result["location_confidence"] = point.confidence if point else 0
    result["geocoding_source"] = point.source if point else None
    return result


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/jobs")
def jobs(
    search: str | None = None,
    seniority: str | None = None,
    area: str | None = None,
    work_mode: str | None = None,
    source: str | None = None,
    skill: str | None = None,
    relevance_tier: str | None = None,
    min_salary: float | None = None,
    max_age_days: int = Query(default=14, ge=1, le=365),
    include_hidden: bool = False,
) -> dict[str, Any]:
    rows = list_jobs(
        limit=None,
        seniority=seniority,
        area=area,
        max_age_days=max_age_days,
        search=search,
        work_mode=work_mode,
        min_salary=min_salary,
        include_hidden=include_hidden,
        source=source,
        skill=skill,
        relevance_tier=relevance_tier,
    )
    return {"jobs": [_with_location(row) for row in rows], "total": len(rows)}


@app.get("/api/map/jobs")
def map_jobs(
    search: str | None = None,
    seniority: str | None = None,
    area: str | None = None,
    work_mode: str | None = None,
    source: str | None = None,
    relevance_tier: str | None = None,
    min_salary: float | None = None,
    max_age_days: int = Query(default=14, ge=1, le=365),
) -> dict[str, Any]:
    rows = list_jobs(
        limit=None,
        seniority=seniority,
        area=area,
        max_age_days=max_age_days,
        search=search,
        work_mode=work_mode,
        min_salary=min_salary,
        source=source,
        relevance_tier=relevance_tier,
    )
    features = []
    for row in rows:
        item = _with_location(row)
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
    max_age_days: int = Query(default=30, ge=1, le=365),
    area: str | None = None,
    seniority: str | None = None,
    work_mode: str | None = None,
) -> dict[str, Any]:
    return skill_overview(max_age_days=max_age_days, area=area, seniority=seniority, work_mode=work_mode)


@app.get("/api/skills/history")
def skills_history(limit: int = Query(default=180, ge=1, le=2000)) -> dict[str, Any]:
    return {"snapshots": skill_history(limit)}


class JobStatusUpdate(BaseModel):
    status: str = Field(pattern="^(visible|hidden)$")
    reason: str | None = Field(default=None, pattern="^(closed|not_interested|applied|duplicate|other)$")
    note: str | None = Field(default=None, max_length=1000)


@app.get("/api/jobs/hidden")
def hidden_jobs() -> dict[str, Any]:
    rows = list_hidden_jobs()
    return {"jobs": [_with_location(row) for row in rows], "total": len(rows)}


@app.get("/api/jobs/favorites")
def favorite_jobs() -> dict[str, Any]:
    rows = list_favorite_jobs()
    return {"jobs": [_with_location(row) for row in rows], "total": len(rows)}


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
    if payload.status == "hidden" and not payload.reason:
        raise HTTPException(status_code=422, detail="El motivo es obligatorio al ocultar una oferta")
    try:
        set_job_user_status(job_id, payload.status, payload.reason, payload.note)
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
    uvicorn.run(
        "radar.api:app",
        host=os.getenv("RADAR_API_HOST", "127.0.0.1"),
        port=int(os.getenv("RADAR_API_PORT", "8100")),
        reload=False,
    )


if __name__ == "__main__":
    main()
