"""Búsqueda en las conversaciones guardadas del agente (recuerdo bajo demanda, sin cargarlas en cada mensaje)."""

from __future__ import annotations

import json
from typing import Any

from radar.db.database import connection
from radar.normalize import normalize_text

MAX_SCANNED = 200
SNIPPET_CHARS = 110


def _texts(data: dict[str, Any]) -> list[tuple[str, str]]:
    """Mensajes de la persona y del agente (rol, texto) de una conversación guardada; sin resultados de herramientas."""
    lines = [(("persona" if l.get("kind") == "user" else "agente"), str(l.get("text") or ""))
             for l in data.get("lines") or [] if l.get("kind") in ("user", "assistant")]
    if lines:
        return lines
    return [(("persona" if m.get("role") == "user" else "agente"), m["content"])
            for m in data.get("history") or [] if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)]


def _snippet(text: str, terms: list[str]) -> str:
    flat = " ".join(text.split())
    position = min((normalize_text(flat).find(t) for t in terms if normalize_text(flat).find(t) >= 0), default=0)
    start = max(0, position - SNIPPET_CHARS // 3)
    piece = flat[start:start + SNIPPET_CHARS]
    return ("…" if start else "") + piece + ("…" if start + SNIPPET_CHARS < len(flat) else "")


def search_conversations(query: str, limit: int = 5, exclude_id: str | None = None) -> list[dict[str, Any]]:
    """Conversaciones cuyo contenido contiene todas las palabras de `query` (sin distinguir tildes ni mayúsculas)."""
    terms = [t for t in normalize_text(query).split() if len(t) > 1][:6]
    if not terms:
        return []
    with connection() as conn:
        rows = conn.execute("SELECT id, title, updated_at, data FROM conversations ORDER BY updated_at DESC LIMIT %s",
                            (MAX_SCANNED,)).fetchall()
    found: list[dict[str, Any]] = []
    for cid, title, updated, raw in rows:
        if cid == exclude_id:
            continue
        try:
            messages = _texts(json.loads(raw))
        except (ValueError, TypeError):
            continue
        haystack = normalize_text(" ".join(text for _, text in messages) + " " + (title or ""))
        if not all(t in haystack for t in terms):
            continue
        hits = [(role, text) for role, text in messages if any(t in normalize_text(text) for t in terms)]
        found.append({"id": cid, "title": title, "updated_at": updated, "messages": len(messages),
                      "snippets": [f"{role}: {_snippet(text, terms)}" for role, text in hits[:3]]})
        if len(found) >= min(max(limit, 1), 10):
            break
    return found
