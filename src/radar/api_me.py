"""Perfil editable desde Ajustes: mismas reglas que la herramienta ``update_profile_fields`` del agente."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from radar import cv_import, cv_photo, cv_profile, profile_edit

router = APIRouter(prefix="/api/me")
_PHOTO_FIELD = File(...)


@router.get("")
def my_profile() -> dict[str, Any]:
    return {"profile": profile_edit.get_full()}


@router.patch("")
def patch_my_profile(fields: dict[str, Any]) -> dict[str, Any]:
    """Cambio parcial: solo se tocan los campos enviados. Devuelve el antes/después y un ``undo`` reenviable."""
    try:
        return profile_edit.patch(fields)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/photo")
async def upload_photo(file: UploadFile = _PHOTO_FIELD) -> dict[str, Any]:
    """Sube la foto de perfil: se valida, se limpia de metadatos y se guarda como ``photo.jpg``."""
    try:
        size = cv_photo.save_photo(await file.read())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"has_photo": True, "size": size}


@router.delete("/photo")
def delete_photo() -> dict[str, Any]:
    return {"has_photo": False, "removed": cv_photo.remove_photo()}


@router.get("/setup")
def setup_state() -> dict:
    return cv_import.status()


@router.put("/setup/draft")
def setup_draft(draft: dict) -> dict:
    try:
        return cv_import.save_draft(draft)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/cv/preview")
async def preview_cv(file: UploadFile = _PHOTO_FIELD, career_id: str = Form("industrial_engineering")) -> dict:
    data = await file.read(cv_import.MAX_BYTES + 1)
    try:
        return await run_in_threadpool(cv_import.preview, data, file.filename or "", career_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/setup/confirm")
def confirm_setup(draft: dict) -> dict:
    try:
        return cv_import.apply(draft)
    except cv_profile.ProfileConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/cv/changes")
def cv_import_changes(draft: dict) -> dict:
    try:
        return cv_import.changes(draft)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/cv")
def factual_cv() -> dict:
    try:
        original = cv_import.original()
        return {**cv_profile.read(), "original_name": original[1] if original else None}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/cv")
def edit_factual_cv(payload: dict) -> dict:
    try:
        return cv_profile.save(payload.get("sections"), payload.get("revision", ""))
    except cv_profile.ProfileConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/cv/original")
def original_cv() -> FileResponse:
    found = cv_import.original()
    if found is None:
        raise HTTPException(status_code=404, detail="Adjunta y confirma tu CV para conservar el archivo original.")
    return FileResponse(found[0], filename=found[1], headers={"Cache-Control": "no-store"})


@router.post("/cv/undo-import")
def undo_cv_import(payload: dict) -> dict:
    try:
        return cv_import.undo_import(payload.get("backup"), payload.get("revision", ""))
    except cv_profile.ProfileConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/updates")
def application_update() -> dict:
    from radar.updates import check

    return check()
