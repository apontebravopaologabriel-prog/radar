"""Endpoints de solo lectura de la vista CVs (objetivos = favoritos). Ver docs/cv.md."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from radar import cv_baseline, cv_build, cv_doc, cv_packages, cv_plan, cv_targets

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


# --- CV Studio: documento por oferta, vista previa, sugerencias y carpetas de postulación -----------------


def _studio_call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class OpsRequest(BaseModel):
    ops: list[dict[str, Any]] = Field(min_length=1, max_length=25)


class OptionsRequest(BaseModel):
    template: str | None = Field(default=None, max_length=20)
    photo: bool | None = None
    pages: int | None = Field(default=None, ge=1, le=3)


class ExportRequest(BaseModel):
    formats: list[str] = Field(default_factory=lambda: ["pdf"], max_length=2)


@router.get("/studio/{job_id}")
def studio_state(job_id: str) -> dict[str, Any]:
    return _studio_call(cv_doc.state, job_id)


@router.get("/studio/{job_id}/page/{page}.png")
def studio_page(job_id: str, page: int, scale: float = Query(default=1.4, ge=0.5, le=3.0)) -> Response:
    image = _studio_call(cv_doc.page_image, job_id, page, scale)
    return Response(content=image, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.post("/studio/{job_id}/ops")
def studio_ops(job_id: str, request: OpsRequest) -> dict[str, Any]:
    return _studio_call(cv_doc.add_ops, job_id, request.ops, "user")


@router.post("/studio/{job_id}/options")
def studio_options(job_id: str, request: OptionsRequest) -> dict[str, Any]:
    return _studio_call(cv_doc.set_options, job_id, request.template, request.photo, request.pages)


@router.post("/studio/{job_id}/undo")
def studio_undo(job_id: str) -> dict[str, Any]:
    return _studio_call(cv_doc.undo, job_id)


@router.post("/studio/{job_id}/redo")
def studio_redo(job_id: str) -> dict[str, Any]:
    return _studio_call(cv_doc.redo, job_id)


@router.post("/studio/{job_id}/reset")
def studio_reset(job_id: str) -> dict[str, Any]:
    return _studio_call(cv_doc.reset, job_id)


@router.post("/studio/{job_id}/suggestions/{suggestion_id}/accept")
def studio_accept(job_id: str, suggestion_id: str) -> dict[str, Any]:
    return _studio_call(cv_doc.accept, job_id, suggestion_id)


@router.post("/studio/{job_id}/suggestions/{suggestion_id}/reject")
def studio_reject(job_id: str, suggestion_id: str) -> dict[str, Any]:
    return _studio_call(cv_doc.reject, job_id, suggestion_id)


@router.post("/studio/{job_id}/suggestions/accept-safe")
def studio_accept_safe(job_id: str) -> dict[str, Any]:
    return _studio_call(cv_doc.accept_safe, job_id)


@router.post("/studio/{job_id}/export")
def studio_export(job_id: str, request: ExportRequest) -> dict[str, Any]:
    return _studio_call(cv_packages.export, job_id, request.formats)


@router.get("/packages")
def packages_list(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
    return {"packages": cv_packages.list_packages(limit), "settings": cv_packages.settings()}


@router.get("/packages/{job_id}/files/{name}")
def package_file(job_id: str, name: str) -> FileResponse:
    path = cv_packages.file_path(job_id, name)  # solo nombres simples dentro de la carpeta registrada
    if path is None:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return FileResponse(str(path), filename=path.name, headers={"Cache-Control": "no-store"})


@router.post("/packages/{job_id}/open-folder")
def package_open_folder(job_id: str) -> dict[str, Any]:
    return _studio_call(cv_packages.open_folder, job_id)


class AppliedRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=500)


@router.post("/packages/{job_id}/applied")
def package_applied(job_id: str, request: AppliedRequest) -> dict[str, Any]:
    return _studio_call(cv_packages.mark_applied, job_id, request.notes)


class CvSettingsRequest(BaseModel):
    export_dir: str | None = Field(default=None, max_length=400)
    filename_pattern: str | None = Field(default=None, max_length=80)
    ascii_filenames: bool | None = None


@router.get("/settings")
def cv_settings_view() -> dict[str, Any]:
    return cv_packages.settings()


@router.put("/settings")
def cv_settings_update(request: CvSettingsRequest) -> dict[str, Any]:
    return _studio_call(cv_packages.update_settings, request.export_dir, request.filename_pattern, request.ascii_filenames)
