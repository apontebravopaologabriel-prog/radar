"""Factual CV profile and saved-offer comparisons."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from radar.cv import baseline as cv_baseline
from radar.cv import store as cv_store

router = APIRouter(prefix="/api/cv")
MAX_COMPARED = 4


@router.get("/profile")
def cv_profile() -> dict[str, Any]:
    return {"profile": cv_store.load_profile()}


@router.get("/selection")
def cv_selection() -> dict[str, Any]:
    """Favoritos activos ordenados por cercanía al perfil real."""
    return {"targets": cv_baseline.ranked_selection()}


@router.get("/targets")
def cv_target_profiles(ids: str | None = Query(default=None, max_length=600)) -> dict[str, Any]:
    """Detalle y matriz de hasta 4 objetivos; sin ``ids`` toma los mejor rankeados."""
    if ids:
        wanted = [value for value in ids.split(",") if value][:MAX_COMPARED]
    else:
        wanted = [t["id"] for t in cv_baseline.ranked_selection()[:3]]
    profile = cv_store.load_profile() or {}
    targets = [t for t in (cv_baseline.combined_target(job_id, profile) for job_id in wanted) if t]
    return {"targets": targets, "matrix": cv_store.build_matrix(targets)}
