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
from radar.agent.loop import (
    agent_enabled,
    compact,
    context_window,
    execute_tool,
    get_memory,
    month_usage,
    monthly_cap,
    read_only,
    run_turn,
    set_memory,
)
from radar.agent.memory import delete_memory, list_memories, save_memory, search_memories
from radar.agent.provider import NO_KEY_PROVIDERS, PROVIDERS, ProviderError, load_config
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
from radar.refresh import refresh_status, start_refresh
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


class CustomCareer(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    areas: dict[str, list[str]] = Field(min_length=1, max_length=20)
    skills: list[str] = Field(default_factory=list, max_length=60)
    queries: list[str] = Field(default_factory=list, max_length=6)


@router.post("/career/custom")
def create_custom_career(payload: CustomCareer) -> dict[str, Any]:
    from radar.careers import save_custom_pack

    try:
        pack = save_custom_pack(payload.name, payload.areas, payload.skills, payload.queries)
    except CareerPackError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    set_setting("career", pack.id)
    return _career_payload()


class RefreshRequest(BaseModel):
    places: list[str] = Field(default_factory=list, max_length=3)
    limit: int = Field(default=15, ge=1, le=50)


@router.post("/refresh", status_code=202)
def refresh(payload: RefreshRequest) -> dict[str, Any]:
    try:
        return start_refresh(payload.places or None, limit=payload.limit)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/refresh/status")
def refresh_state() -> dict[str, Any]:
    return refresh_status()


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
        "reasoning_effort": config.reasoning_effort or "auto",
        "has_key": bool(config.api_key),
        "needs_key": config.provider not in NO_KEY_PROVIDERS,
        "ready": config.ready,
        "enabled": agent_enabled(),
        "read_only": read_only(),
        "context_window": context_window(),
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
    reasoning_effort: str = Field(default="auto", pattern="^(auto|none|low|high|max)$")
    base_url: str | None = Field(default=None, max_length=300, pattern="^https?://")
    api_key: str | None = Field(default=None, max_length=400)
    monthly_token_cap: int | None = Field(default=None, ge=1000, le=100_000_000)
    enabled: bool | None = None
    read_only: bool | None = None
    context_window: int | None = Field(default=None, ge=2000, le=2_000_000)


@router.put("/agent/settings")
def update_agent_settings(payload: AgentSettingsUpdate) -> dict[str, Any]:
    if payload.enabled is not None:
        set_setting("agent_enabled", "1" if payload.enabled else "0")
    if payload.read_only is not None:
        set_setting("agent_read_only", "1" if payload.read_only else "0")
    if payload.context_window is not None:
        set_setting("agent_context_window", str(payload.context_window))
    set_setting("llm_provider", payload.provider)
    set_setting("llm_model", payload.model or None)
    set_setting("llm_reasoning_effort", None if payload.reasoning_effort == "auto" else payload.reasoning_effort)
    set_setting("llm_base_url", payload.base_url or None)
    if payload.api_key is not None:  # cadena vacía = borrar la clave
        write_secret(f"llm_key_{payload.provider}", payload.api_key.strip() or None)
    if payload.monthly_token_cap is not None:
        set_setting("agent_monthly_token_cap", str(payload.monthly_token_cap))
    return _agent_settings()


class ChatRequest(BaseModel):
    messages: list[dict[str, Any]] = Field(min_length=1, max_length=80)
    focus: str = Field(default="", max_length=200)
    context: dict[str, Any] = Field(default_factory=dict)


def _valid_history(messages: list[dict[str, Any]]) -> bool:
    return all(
        m.get("role") in {"user", "assistant", "tool"} and isinstance(m.get("content", ""), (str, type(None)))
        for m in messages
    )


@router.post("/chat")
def chat(payload: ChatRequest) -> StreamingResponse:
    if not agent_enabled():
        raise HTTPException(status_code=403, detail="agent_disabled")
    if not _valid_history(payload.messages):
        raise HTTPException(status_code=422, detail="Historial inválido")

    def events() -> Iterator[str]:
        for event in run_turn(load_config(), payload.messages, context=payload.context):
            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-store"}
    )


class MemoryBody(BaseModel):
    items: list[str] = Field(max_length=30)


class StructuredMemoryBody(BaseModel):
    topic_key: str = Field(min_length=2, max_length=100)
    content: str = Field(min_length=1, max_length=1000)
    memory_type: str = "preference"
    source: str = "user"
    confidence: float = Field(default=1.0, ge=0, le=1)


@router.get("/agent/memory")
def read_memory() -> dict[str, Any]:
    return {"items": get_memory()}


@router.put("/agent/memory")
def write_memory(body: MemoryBody) -> dict[str, Any]:
    return {"items": set_memory(body.items)}


@router.get("/agent/memories")
def read_structured_memories(query: str = Query(default="", max_length=200), limit: int = Query(default=30, ge=1, le=100)) -> dict[str, Any]:
    return {"memories": search_memories(query, limit) if query.strip() else list_memories(limit)}


@router.post("/agent/memories")
def create_structured_memory(body: StructuredMemoryBody) -> dict[str, Any]:
    return {"memory": save_memory(body.content, body.topic_key, body.memory_type, body.source, body.confidence)}


@router.delete("/agent/memories/{topic_key:path}")
def remove_structured_memory(topic_key: str) -> dict[str, Any]:
    delete_memory(topic_key)
    return {"deleted": topic_key}


@router.get("/agent/tools")
def agent_tools() -> dict[str, Any]:
    """Herramientas que el agente puede usar (equivale a /tools)."""
    return {
        "read_only_mode": read_only(),
        "tools": [
            {"name": t.name, "write": t.write, "summary": t.description.splitlines()[0]}
            for t in tools.chat_tools()
        ],
    }


@router.get("/doctor")
def doctor() -> dict[str, Any]:
    """Diagnóstico rápido de la instalación (equivale a /doctor)."""
    from radar.db.database import connection, database_path

    path = database_path()
    with connection() as conn:
        jobs = conn.execute("SELECT count(*) FROM jobs WHERE is_active=1").fetchone()[0]
        fresh = conn.execute(
            "SELECT count(*) FROM jobs WHERE is_active=1 AND date(published_at) >= date('now','-14 days')"
        ).fetchone()[0]
        newest = conn.execute("SELECT max(published_at) FROM jobs").fetchone()[0]
        conversations = conn.execute("SELECT count(*) FROM conversations").fetchone()[0]
    config = load_config()
    return {
        "version": "0.1.0",
        "database": {"path": str(path), "size_mb": round(path.stat().st_size / 1e6, 1) if path.exists() else 0},
        "jobs": {"active": jobs, "last_14_days": fresh, "newest_published": str(newest) if newest else None},
        "career": active_pack().name,
        "agent": {"enabled": agent_enabled(), "provider": config.provider, "model": config.model,
                  "key": bool(config.api_key), "read_only": read_only(), "conversations": conversations},
        "refresh": refresh_status(),
        "tools": len(tools.chat_tools()),
    }


@router.post("/chat/compact")
def compact_chat(payload: ChatRequest) -> dict[str, Any]:
    """Resume la conversación para liberar contexto (equivale a /compactar)."""
    if not agent_enabled():
        raise HTTPException(status_code=403, detail="agent_disabled")
    if not _valid_history(payload.messages):
        raise HTTPException(status_code=422, detail="Historial inválido")
    try:
        return compact(load_config(), payload.messages, focus=payload.focus)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


class ConfirmRequest(BaseModel):
    tool_call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    approve: bool


@router.post("/chat/confirm")
def confirm(payload: ConfirmRequest) -> dict[str, Any]:
    """Ejecuta (o rechaza) una escritura propuesta por el agente. Solo herramientas de escritura."""
    if not agent_enabled():
        raise HTTPException(status_code=403, detail="agent_disabled")
    entry = tools.REGISTRY.get(payload.name)
    if entry is None or not entry.chat or not entry.write or read_only():
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


# --- Conversaciones guardadas (en la base local del usuario) -------------------------------------

MAX_CONVERSATION_CHARS = 400_000
MAX_CONVERSATIONS = 200


class ConversationBody(BaseModel):
    title: str = Field(default="Conversación", max_length=120)
    data: dict[str, Any]


def _require_agent() -> None:
    if not agent_enabled():
        raise HTTPException(status_code=403, detail="agent_disabled")


def _serialize(body: ConversationBody) -> str:
    text = json.dumps(body.data, ensure_ascii=False)
    if len(text) > MAX_CONVERSATION_CHARS:
        raise HTTPException(status_code=413, detail="Conversación demasiado larga")
    return text


@router.get("/conversations")
def list_conversations(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    _require_agent()
    from radar.db.database import connection

    with connection() as conn:
        rows = conn.execute(
            "SELECT id, title, updated_at, COALESCE(json_array_length(data, '$.lines'), 0) FROM conversations "
            "ORDER BY updated_at DESC LIMIT %s", (limit,)
        ).fetchall()
    return {"conversations": [{"id": r[0], "title": r[1], "updated_at": r[2], "lines": r[3]} for r in rows]}


@router.get("/conversations/search")
def search_saved_conversations(q: str = Query(min_length=2, max_length=100), limit: int = Query(default=8, ge=1, le=10)) -> dict[str, Any]:
    _require_agent()
    from radar.agent.history import search_conversations

    return {"conversations": search_conversations(q, limit)}


@router.post("/conversations", status_code=201)
def create_conversation(body: ConversationBody) -> dict[str, str]:
    _require_agent()
    from radar.db.database import connection

    text = _serialize(body)
    with connection() as conn:
        count = conn.execute("SELECT count(*) FROM conversations").fetchone()[0]
        if count >= MAX_CONVERSATIONS:
            conn.execute(
                "DELETE FROM conversations WHERE id IN (SELECT id FROM conversations ORDER BY updated_at LIMIT %s)",
                (count - MAX_CONVERSATIONS + 1,),
            )
        new_id = conn.execute(
            "INSERT INTO conversations(title, data) VALUES (%s, %s) RETURNING id", (body.title, text)
        ).fetchone()[0]
    return {"id": new_id}


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str) -> dict[str, Any]:
    _require_agent()
    from radar.db.database import connection

    with connection() as conn:
        row = conn.execute("SELECT id, title, data FROM conversations WHERE id=%s", (conversation_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    return {"id": row[0], "title": row[1], "data": json.loads(row[2])}


@router.put("/conversations/{conversation_id}")
def save_conversation(conversation_id: str, body: ConversationBody) -> dict[str, str]:
    _require_agent()
    from radar.db.database import connection

    text = _serialize(body)
    with connection() as conn:
        updated = conn.execute(
            "UPDATE conversations SET title=%s, data=%s, updated_at=now() WHERE id=%s",
            (body.title, text, conversation_id),
        ).rowcount
    if not updated:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    return {"id": conversation_id}


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str) -> dict[str, bool]:
    from radar.db.database import connection

    with connection() as conn:
        conn.execute("DELETE FROM conversations WHERE id=%s", (conversation_id,))
    return {"deleted": True}


@router.delete("/conversations")
def delete_all_conversations() -> dict[str, int]:
    """Borrar el historial siempre está permitido, incluso con el agente apagado."""
    from radar.db.database import connection

    with connection() as conn:
        deleted = conn.execute("DELETE FROM conversations").rowcount
    return {"deleted": deleted}
