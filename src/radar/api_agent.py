"""Endpoints de la app móvil/web: feed Hoy, seguimiento, ajustes, carrera y chat del agente."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from radar import tools
from radar.agent.loop import execute_tool, month_usage, monthly_cap, run_turn
from radar.agent.provider import NO_KEY_PROVIDERS, PROVIDERS, load_config
from radar.careers import (
    WEIGHT_KEYS,
    CareerPackError,
    active_pack,
    effective_weights,
    list_packs,
    load_pack,
)
from radar.db.queries import applications, get_profile
from radar.db.repository import recompute_scores, track_application
from radar.feed import (
    default_place,
    map_places,
    nearby,
    setup_status,
    skill_impact,
    today_feed,
)
from radar.geolocation import place_catalog
from radar.settings import set_json_setting, set_setting, write_secret

router = APIRouter(prefix="/api")


# --- Hoy, impacto de skills y seguimiento ---------------------------------------------------------


@router.get("/today")
def today(limit: int = Query(default=5, ge=1, le=20)) -> dict[str, Any]:
    return today_feed(limit)


@router.get("/setup/status")
def setup() -> dict[str, Any]:
    return setup_status()


@router.get("/places")
def places() -> dict[str, Any]:
    catalog = place_catalog()
    return {
        "groups": [
            {"label": "Lima y Callao (distritos)", "places": [p["name"] for p in catalog["lima"]]},
            {"label": "Resto del Perú (ciudades)", "places": [p["name"] for p in catalog["peru"]]},
        ],
        "default": default_place(),
    }


@router.get("/map/places")
def map_place_counts() -> dict[str, Any]:
    return map_places()


@router.get("/nearby")
def nearby_jobs(
    place: str = Query(min_length=1, max_length=80),
    radius_km: float = Query(default=5.0, ge=0.5, le=2500),
    limit: int = Query(default=30, ge=1, le=60),
) -> dict[str, Any]:
    try:
        return nearby(place, radius_km, limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/skills/impact")
def impact(limit: int = Query(default=8, ge=1, le=30)) -> dict[str, Any]:
    return skill_impact(limit)


@router.get("/applications")
def list_applications() -> dict[str, Any]:
    return {"applications": applications(200)}


class ApplicationUpdate(BaseModel):
    status: str = Field(pattern="^(saved|applied|interview|offer|rejected|ignored)$")
    notes: str | None = Field(default=None, max_length=1000)


@router.put("/applications/{job_id}")
def update_application(job_id: str, payload: ApplicationUpdate) -> dict[str, str]:
    try:
        application_id = track_application(job_id, payload.status, payload.notes)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=404, detail="Oferta no encontrada") from exc
    return {"application_id": application_id, "status": payload.status}


# --- Perfil y carrera -----------------------------------------------------------------------------


class ProfileUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    education: str | None = Field(default=None, max_length=200)
    areas: list[str] = Field(default_factory=list, max_length=20)
    locations: list[str] = Field(default_factory=list, max_length=20)
    work_modes: list[str] = Field(default_factory=list, max_length=5)
    skills: dict[str, str] = Field(default_factory=dict)


@router.put("/profile")
def save_user_profile(payload: ProfileUpdate) -> dict[str, Any]:
    try:
        profile_id = tools.update_profile(
            payload.name, payload.areas, payload.locations, payload.skills,
            payload.education, payload.work_modes,
        )["profile_id"]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"profile_id": profile_id, "profile": get_profile()}


def _career_payload() -> dict[str, Any]:
    pack = active_pack()
    return {
        "active": pack.id,
        "name": pack.name,
        "areas": {"core": sorted(pack.core_areas), "adjacent": sorted(pack.adjacent_areas)},
        "skills": [
            {"name": s.name, "type": s.type, "category": s.category}
            for s in pack.skills.values()
        ],
        "queries": list(pack.queries),
        "weights": effective_weights(pack),
        "tracks": [{"id": p.id, "name": p.name} for p in list_packs()],
    }


@router.get("/career")
def career() -> dict[str, Any]:
    return _career_payload()


class CareerUpdate(BaseModel):
    career_id: str = Field(min_length=1, max_length=64)


@router.put("/career")
def set_career(payload: CareerUpdate) -> dict[str, Any]:
    try:
        pack = load_pack(payload.career_id)
    except CareerPackError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    set_setting("career", pack.id)
    return _career_payload()


class WeightsUpdate(BaseModel):
    weights: dict[str, float]


@router.put("/career/weights")
def set_weights(payload: WeightsUpdate) -> dict[str, Any]:
    unknown = set(payload.weights) - set(WEIGHT_KEYS)
    if unknown or any(v < 0 or v > 1 for v in payload.weights.values()):
        raise HTTPException(status_code=422, detail="Pesos inválidos")
    set_json_setting("score_weights", payload.weights)
    profile = get_profile()
    if profile:
        recompute_scores(profile["id"])
    return _career_payload()


# --- Agente ---------------------------------------------------------------------------------------


def _agent_settings() -> dict[str, Any]:
    config = load_config()
    return {
        "provider": config.provider,
        "base_url": config.base_url,
        "model": config.model,
        "has_key": bool(config.api_key),
        "needs_key": config.provider not in NO_KEY_PROVIDERS,
        "ready": config.ready,
        "monthly_token_cap": monthly_cap(),
        "tokens_used_this_month": month_usage(),
        "providers": {k: v for k, v in PROVIDERS.items()},
    }


@router.get("/agent/settings")
def agent_settings() -> dict[str, Any]:
    return _agent_settings()


class AgentSettingsUpdate(BaseModel):
    provider: str = Field(pattern="^(deepseek|openai|openrouter|ollama|custom)$")
    model: str | None = Field(default=None, max_length=100)
    base_url: str | None = Field(default=None, max_length=300, pattern="^https?://")
    api_key: str | None = Field(default=None, max_length=400)
    monthly_token_cap: int | None = Field(default=None, ge=1000, le=100_000_000)


@router.put("/agent/settings")
def update_agent_settings(payload: AgentSettingsUpdate) -> dict[str, Any]:
    set_setting("llm_provider", payload.provider)
    set_setting("llm_model", payload.model or None)
    set_setting("llm_base_url", payload.base_url or None)
    if payload.api_key is not None:  # cadena vacía = borrar la clave
        write_secret(f"llm_key_{payload.provider}", payload.api_key.strip() or None)
    if payload.monthly_token_cap is not None:
        set_setting("agent_monthly_token_cap", str(payload.monthly_token_cap))
    return _agent_settings()


class ChatRequest(BaseModel):
    messages: list[dict[str, Any]] = Field(min_length=1, max_length=80)


def _valid_history(messages: list[dict[str, Any]]) -> bool:
    return all(
        m.get("role") in {"user", "assistant", "tool"} and isinstance(m.get("content", ""), (str, type(None)))
        for m in messages
    )


@router.post("/chat")
def chat(payload: ChatRequest) -> StreamingResponse:
    if not _valid_history(payload.messages):
        raise HTTPException(status_code=422, detail="Historial inválido")

    def events() -> Iterator[str]:
        for event in run_turn(load_config(), payload.messages):
            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-store"}
    )


class ConfirmRequest(BaseModel):
    tool_call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    approve: bool


@router.post("/chat/confirm")
def confirm(payload: ConfirmRequest) -> dict[str, Any]:
    """Ejecuta (o rechaza) una escritura propuesta por el agente. Solo herramientas de escritura."""
    entry = tools.REGISTRY.get(payload.name)
    if entry is None or not entry.chat or not entry.write:
        raise HTTPException(status_code=422, detail="Herramienta no confirmable")
    if not payload.approve:
        result: Any = {"cancelado_por_el_usuario": True}
    else:
        try:
            result = execute_tool(payload.name, payload.arguments)
        except (ValidationError, ValueError, sqlite3.IntegrityError) as exc:
            result = {"error": str(exc)[:300]}
    from radar.agent.loop import wrap_untrusted

    return {
        "message": {
            "role": "tool",
            "tool_call_id": payload.tool_call_id,
            "content": wrap_untrusted(result),
        },
        "result": result,
    }
