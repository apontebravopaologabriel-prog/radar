"""Endpoints del agente interno: configuración, chat, memoria, menciones y conversaciones."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from radar import tools
from radar.agent.loop import (
    agent_enabled,
    autocompact_pct,
    compact,
    consume_pending_proposal,
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
from radar.settings import set_setting, write_secret

router = APIRouter(prefix="/api")


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
        "autocompact_pct": autocompact_pct(),
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
    autocompact_pct: int | None = Field(default=None, ge=0, le=90)  # 0 = apagado


@router.put("/agent/settings")
def update_agent_settings(payload: AgentSettingsUpdate) -> dict[str, Any]:
    if payload.enabled is not None:
        set_setting("agent_enabled", "1" if payload.enabled else "0")
    if payload.read_only is not None:
        set_setting("agent_read_only", "1" if payload.read_only else "0")
    if payload.context_window is not None:
        set_setting("agent_context_window", str(payload.context_window))
    if payload.autocompact_pct is not None:
        set_setting("agent_autocompact_pct", str(payload.autocompact_pct))
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
    plan: bool = False
    last_prompt_tokens: int = Field(default=0, ge=0, le=5_000_000)


MAX_MESSAGE_CHARS = 60_000
MAX_HISTORY_CHARS = 600_000
MAX_IMAGE_DATA_CHARS = 1_500_000
MAX_IMAGES_PER_MESSAGE = 3
_VALID_DATA_IMAGE_PREFIXES = (
    "data:image/png;base64,",
    "data:image/jpeg;base64,",
    "data:image/jpg;base64,",
    "data:image/webp;base64,",
)


def _valid_message_content(role: str, content: Any) -> int | None:
    """Devuelve el peso en caracteres de texto si el contenido es válido, o None si debe rechazarse."""
    if content is None:
        return 0
    if isinstance(content, str):
        return len(content) if len(content) <= MAX_MESSAGE_CHARS else None
    if role == "user" and isinstance(content, list) and 1 <= len(content) <= MAX_IMAGES_PER_MESSAGE + 2:
        text_size = 0
        images = 0
        for part in content:
            if not isinstance(part, dict):
                return None
            ptype = part.get("type")
            if ptype == "text":
                txt = part.get("text")
                if not isinstance(txt, str) or len(txt) > MAX_MESSAGE_CHARS:
                    return None
                text_size += len(txt)
            elif ptype == "image_url":
                img = part.get("image_url")
                url = img.get("url") if isinstance(img, dict) else None
                if (
                    not isinstance(url, str)
                    or not url.startswith(_VALID_DATA_IMAGE_PREFIXES)
                    or len(url) > MAX_IMAGE_DATA_CHARS
                ):
                    return None
                images += 1
                if images > MAX_IMAGES_PER_MESSAGE:
                    return None
            else:
                return None
        return text_size if text_size <= MAX_MESSAGE_CHARS else None
    return None


def _valid_history(messages: list[dict[str, Any]]) -> bool:
    """Solo roles de conversación (nunca `system`), texto o bloques multimodales acotados y un tope de tamaño."""
    total_text = 0
    for m in messages:
        role = m.get("role")
        if role not in {"user", "assistant", "tool"}:
            return False
        size = _valid_message_content(role, m.get("content", ""))
        if size is None:
            return False
        total_text += size
    return total_text <= MAX_HISTORY_CHARS


@router.post("/chat")
def chat(payload: ChatRequest) -> StreamingResponse:
    if not agent_enabled():
        raise HTTPException(status_code=403, detail="agent_disabled")
    if not _valid_history(payload.messages):
        raise HTTPException(status_code=422, detail="Historial inválido")

    def events() -> Iterator[str]:
        for event in run_turn(load_config(), payload.messages, context=payload.context, plan=payload.plan,
                              last_prompt_tokens=payload.last_prompt_tokens):
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
    """Ejecuta (o rechaza) una escritura propuesta por el agente. Vincula nombre y argumentos si existe propuesta registrada."""
    if not agent_enabled():
        raise HTTPException(status_code=403, detail="agent_disabled")
    stored = consume_pending_proposal(payload.tool_call_id)
    if stored is not None:
        stored_name, stored_args = stored
        if stored_name != payload.name or stored_args != payload.arguments:
            raise HTTPException(status_code=422, detail="La propuesta no coincide con la acción registrada")
        tool_name, tool_args = stored_name, stored_args
    else:
        tool_name, tool_args = payload.name, payload.arguments
    entry = tools.REGISTRY.get(tool_name)
    if entry is None or not entry.chat or not entry.write or read_only():
        raise HTTPException(status_code=422, detail="Herramienta no confirmable")
    if not payload.approve:
        result: Any = {"cancelado_por_el_usuario": True}
    else:
        try:
            result = execute_tool(tool_name, tool_args)
        except Exception as exc:  # noqa: BLE001
            result = {"error": str(exc)[:500]}
    from radar.agent.loop import wrap_untrusted

    return {
        "message": {
            "role": "tool",
            "tool_call_id": payload.tool_call_id,
            "content": wrap_untrusted(result),
        },
        "result": result,
    }


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


@router.get("/mentions")
def mentions(q: str = Query(default="", max_length=60), limit: int = Query(default=8, ge=1, le=15)) -> dict[str, Any]:
    """Candidatos para `@` en el chat: lugares (distritos y ciudades) y ofertas vigentes por título o empresa."""
    from radar.db.queries import list_jobs
    from radar.geolocation import place_catalog
    from radar.normalize import normalize_text

    needle = normalize_text(q)
    catalog = place_catalog()
    places = [
        {"type": "place", "name": p["name"], "kind": p["kind"]}
        for p in [*catalog["lima"], *catalog["peru"]]
        if not needle or normalize_text(str(p["name"])).startswith(needle) or f" {needle}" in normalize_text(str(p["name"]))
    ]
    places.sort(key=lambda p: not normalize_text(p["name"]).startswith(needle))
    jobs = []
    if len(needle) >= 2:
        jobs = [
            {"type": "job", "id": j["id"], "name": j["title"], "company": j.get("company")}
            for j in list_jobs(limit=6, max_age_days=30, search=q)
        ]
    return {"places": places[: min(limit, 6)], "jobs": jobs[: max(limit - 6, 3)]}


@router.get("/conversations")
def list_conversations(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    _require_agent()
    from radar.db.database import connection

    with connection() as conn:
        rows = conn.execute(
            "SELECT id, title, updated_at, COALESCE(json_array_length(data, '$.lines'), 0) FROM conversations "
            "ORDER BY updated_at DESC LIMIT %s",
            (limit,),
        ).fetchall()
    return {"conversations": [{"id": r[0], "title": r[1], "updated_at": r[2], "lines": r[3]} for r in rows]}


@router.get("/conversations/search")
def search_saved_conversations(
    q: str = Query(min_length=2, max_length=100),
    limit: int = Query(default=8, ge=1, le=10),
) -> dict[str, Any]:
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
            "INSERT INTO conversations(title, data) VALUES (%s, %s) RETURNING id",
            (body.title, text),
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
