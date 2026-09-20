"""Memoria durable y explícita del agente; no es un volcado de conversaciones."""
from __future__ import annotations

import hashlib
import re
from typing import Any

from radar.db.database import connection

VALID_TYPES = {"preference", "goal", "decision", "learning", "constraint", "observation"}
VALID_SOURCES = {"user", "chat", "profile", "tool"}
FIELDS = ("id", "topic_key", "memory_type", "content", "source", "confidence", "updated_at")

def _key(content: str) -> str:
    return "manual/" + hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

def migrate_legacy(items: list[str]) -> None:
    for item in items:
        content = " ".join(str(item).split()).strip()[:200]
        if content:
            save_memory(content, topic_key=_key(content), source="user")

def save_memory(content: str, topic_key: str | None = None, memory_type: str = "preference", source: str = "user", confidence: float = 1.0) -> dict[str, Any]:
    content = " ".join(content.split()).strip()
    topic_key = (topic_key or _key(content)).strip()
    if not content or len(content) > 1000:
        raise ValueError("content debe tener entre 1 y 1000 caracteres")
    if not re.fullmatch(r"[a-zA-Z0-9._/-]{2,100}", topic_key):
        raise ValueError("topic_key inválido")
    if memory_type not in VALID_TYPES or source not in VALID_SOURCES:
        raise ValueError("Tipo o fuente de memoria inválidos")
    confidence = min(max(float(confidence), 0), 1)
    with connection() as conn:
        conn.execute("INSERT INTO agent_memories(topic_key,memory_type,content,source,confidence,last_confirmed_at) VALUES (%s,%s,%s,%s,%s,now()) ON CONFLICT(topic_key) DO UPDATE SET memory_type=excluded.memory_type, content=excluded.content, source=excluded.source, confidence=excluded.confidence, is_active=1, updated_at=now(), last_confirmed_at=now()", (topic_key, memory_type, content, source, confidence))
        row = conn.execute("SELECT id,topic_key,memory_type,content,source,confidence,updated_at FROM agent_memories WHERE topic_key=%s", (topic_key,)).fetchone()
    return dict(zip(FIELDS, row))

def list_memories(limit: int = 30) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute("SELECT id,topic_key,memory_type,content,source,confidence,updated_at FROM agent_memories WHERE is_active=1 ORDER BY updated_at DESC LIMIT %s", (min(max(limit, 1), 100),)).fetchall()
    return [dict(zip(FIELDS, row)) for row in rows]

def search_memories(query: str, limit: int = 8) -> list[dict[str, Any]]:
    terms = " ".join(re.findall(r"[\wáéíóúüñÁÉÍÓÚÜÑ]+", query))
    if not terms:
        return list_memories(limit)
    with connection() as conn:
        rows = conn.execute("SELECT m.id,m.topic_key,m.memory_type,m.content,m.source,m.confidence,m.updated_at FROM agent_memories_fts f JOIN agent_memories m ON m.rowid=f.rowid WHERE agent_memories_fts MATCH %s AND m.is_active=1 ORDER BY rank LIMIT %s", (terms, min(max(limit, 1), 30))).fetchall()
    return [dict(zip(FIELDS, row)) for row in rows]

def delete_memory(topic_key: str) -> None:
    with connection() as conn:
        conn.execute("DELETE FROM agent_memories WHERE topic_key=%s", (topic_key,))
