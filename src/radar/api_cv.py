"""Endpoints de solo lectura de la vista CVs (objetivos = favoritos). Ver docs/target-profiles.md."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from radar import cv_baseline, cv_targets

router = APIRouter(prefix="/api/cv")
MAX_COMPARED = 4


@router.get("/profile")
def cv_profile() -> dict[str, Any]:
    return {"profile": cv_targets.load_profile()}


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
    profile = cv_targets.load_profile() or {}
    targets = [t for t in (cv_baseline.combined_target(job_id, profile) for job_id in wanted) if t]
    return {"targets": targets, "matrix": cv_targets.build_matrix(targets)}


@router.get("/photo")
def cv_photo() -> FileResponse:
    # Ruta fija bajo el directorio de datos: nunca se acepta una ruta del cliente.
    path = cv_targets.photo_path()
    if path is None:
        raise HTTPException(status_code=404, detail="Sin foto configurada")
    return FileResponse(str(path), headers={"Cache-Control": "no-cache"})
