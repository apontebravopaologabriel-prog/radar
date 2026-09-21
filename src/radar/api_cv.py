"""Endpoints de solo lectura de la vista CVs (objetivos = favoritos). Ver docs/target-profiles.md."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from radar import cv_baseline, cv_build, cv_plan, cv_targets

router = APIRouter(prefix="/api/cv")
MAX_COMPARED = 4


@router.get("/profile")
def cv_profile() -> dict[str, Any]:
    return {"profile": cv_targets.load_profile()}


@router.get("/selection")
def cv_selection() -> dict[str, Any]:
    """Favoritos activos ordenados por cercanía al perfil real."""
    return {"targets": cv_baseline.ranked_selection()}


@router.get("/plan")
def cv_closure_plan(limit: int = Query(default=10, ge=1, le=30)) -> dict[str, Any]:
    """Skills a cerrar primero entre todos los objetivos, ponderadas por demanda del mercado."""
    return cv_plan.closure_plan(limit)


class BuildRequest(BaseModel):
    job_id: str = Field(min_length=1, max_length=64)
    formats: list[str] | None = None


@router.get("/build/preview")
def cv_build_preview(job_id: str = Query(min_length=1, max_length=64)) -> dict[str, Any]:
    """Qué entraría en el CV para esta oferta y qué se omite, sin escribir archivos."""
    try:
        return cv_build.select(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/build")
def cv_build_files(request: BuildRequest) -> dict[str, Any]:
    """Genera el DOCX/PDF del CV para la oferta (carpeta ``cvs/<fecha>/``, sin sobrescribir)."""
    try:
        return cv_build.build(request.job_id, request.formats)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/files/{day}/{name}")
def cv_generated_file(day: str, name: str) -> FileResponse:
    # Solo archivos ya generados bajo cvs/, con extensión permitida: nunca una ruta arbitraria.
    path = cv_build.resolve_file(f"{day}/{name}")
    if path is None:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return FileResponse(str(path), filename=path.name, headers={"Cache-Control": "no-store"})


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
