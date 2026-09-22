"""Perfil editable desde Ajustes: mismas reglas que la herramienta ``update_profile_fields`` del agente."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from radar import cv_photo, profile_edit

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
