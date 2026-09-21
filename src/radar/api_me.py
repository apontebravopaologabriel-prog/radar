"""Perfil editable desde Ajustes: mismas reglas que la herramienta ``update_profile_fields`` del agente."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from radar import profile_edit

router = APIRouter(prefix="/api/me")


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
