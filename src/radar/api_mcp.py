"""Endpoints de «Conectar un cliente de IA»: muestra la configuración MCP y la instala con confirmación explícita."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from radar import mcp_config

router = APIRouter(prefix="/api/mcp")


class InstallRequest(BaseModel):
    client: str = Field(pattern="^(claude_desktop|cursor|gemini_cli)$")


@router.get("/config")
def mcp_config_view() -> dict[str, Any]:
    return mcp_config.describe()


@router.post("/install")
def mcp_install(payload: InstallRequest) -> dict[str, Any]:
    try:
        return mcp_config.install(payload.client)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo escribir la configuración: {exc}") from exc
