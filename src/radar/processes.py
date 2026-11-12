"""Optional follow-up for opportunities that have received a human response."""
from __future__ import annotations

import sqlite3
from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from radar.db.database import connection
from radar.db.queries import APPLICATION_ARCHIVED_AT
from radar.normalize import normalize_text

Stage = Literal["contact", "assessment", "interview", "offer", "closed"]


class ProcessInput(BaseModel):
    company: str = Field(min_length=1, max_length=300)
    title: str = Field(min_length=1, max_length=500)
    job_id: str | None = None
    url: str | None = Field(default=None, max_length=2000)
    stage: Stage = "contact"
    next_step: str | None = Field(default=None, max_length=500)
    due_date: date | None = None
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("company", "title")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("El campo no puede estar vacío")
        return value.strip()

    @field_validator("url")
    @classmethod
    def safe_url(cls, value: str | None) -> str | None:
        from urllib.parse import urlsplit
        if not value:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("Usa un enlace http o https")
        return value


class ProcessItem(ProcessInput):
    id: str
    source_application_id: str | None = None
    created_at: str
    updated_at: str
    archived_at: str | None = None


class ProcessList(BaseModel):
    processes: list[ProcessItem]


router = APIRouter(prefix="/api/processes", tags=["processes"])


def _read(conn, process_id: str) -> dict:
    cursor = conn.execute("SELECT * FROM processes WHERE id=%s", (process_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "Proceso no encontrado")
    return dict(zip([c[0] for c in cursor.description], row, strict=True))


@router.get("", response_model=ProcessList)
def list_processes() -> dict:
    with connection() as conn:
        cursor = conn.execute("""SELECT * FROM processes ORDER BY
            CASE WHEN due_date IS NULL OR due_date='' THEN 1 ELSE 0 END,
            due_date ASC, updated_at DESC, id ASC""")
        names = [c[0] for c in cursor.description]
        return {"processes": [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]}


class ArchiveEntry(BaseModel):
    id: str
    job_id: str | None
    company: str | None
    title: str
    url: str | None
    notes: str | None
    archived_at: str


class ArchivePage(BaseModel):
    entries: list[ArchiveEntry]
    has_more: bool


@router.get("/archive", response_model=ArchivePage)
def archive_history(q: str = Query("", max_length=300), page: int = Query(1, ge=1, le=1_000_000)) -> dict:
    size = 20
    with connection() as conn:
        conn.create_function("tracking_search", 1, normalize_text, deterministic=True)
        cursor = conn.execute(f"""
            WITH archived AS (
                SELECT 'p:' || p.id AS id, p.job_id, p.company, p.title, p.url, p.notes,
                    COALESCE(p.archived_at, {APPLICATION_ARCHIVED_AT}, p.updated_at) AS archived_at
                FROM processes p LEFT JOIN applications a ON a.job_id=p.job_id
                WHERE p.stage='closed' OR a.status IN ('rejected', 'ignored')
                UNION ALL
                SELECT 'a:' || a.id, a.job_id, c.name, j.title,
                    (SELECT source_url FROM job_sources WHERE job_id=j.id ORDER BY last_seen_at DESC LIMIT 1),
                    a.notes, {APPLICATION_ARCHIVED_AT}
                FROM applications a JOIN jobs j ON j.id=a.job_id
                LEFT JOIN companies c ON c.id=j.company_id
                WHERE (a.status='rejected' OR (a.status='ignored' AND a.applied_at IS NOT NULL))
                    AND NOT EXISTS (SELECT 1 FROM processes p WHERE p.job_id=a.job_id)
            )
            SELECT * FROM archived
            WHERE instr(tracking_search(title || ' ' || COALESCE(company, '')), %s) > 0
            ORDER BY julianday(archived_at) DESC, id LIMIT %s OFFSET %s
        """, (normalize_text(q), size + 1, (page - 1) * size))
        names = [column[0] for column in cursor.description]
        rows = cursor.fetchall()
    return {"entries": [dict(zip(names, row, strict=True)) for row in rows[:size]], "has_more": len(rows) > size}


@router.post("", response_model=ProcessItem, status_code=201)
def create_process(payload: ProcessInput) -> dict:
    values = payload.model_dump(mode="json")
    with connection() as conn:
        try:
            cursor = conn.execute(
                f"INSERT INTO processes ({','.join(values)},archived_at) "
                f"VALUES ({','.join(['%s'] * len(values))}, CASE WHEN %s='closed' THEN now() END) RETURNING id",
                [*values.values(), payload.stage],
            )
            return _read(conn, cursor.fetchone()[0])
        except sqlite3.IntegrityError as exc:
            if payload.job_id and not conn.execute("SELECT 1 FROM jobs WHERE id=%s", (payload.job_id,)).fetchone():
                raise HTTPException(404, "Oferta no encontrada") from exc
            raise HTTPException(409, "Esta oferta ya tiene un proceso; ábrelo desde Procesos") from exc


@router.put("/{process_id}", response_model=ProcessItem)
def update_process(process_id: str, payload: ProcessInput) -> dict:
    values = payload.model_dump(mode="json")
    with connection() as conn:
        old = _read(conn, process_id)
        if values["job_id"] != old["job_id"]:
            raise HTTPException(422, "La oferta vinculada no se puede cambiar")
        conn.execute(
            f"UPDATE processes SET {','.join(f'{key}=%s' for key in values)}, updated_at=now(), "
            "archived_at=CASE WHEN %s='closed' THEN "
            "CASE WHEN stage='closed' THEN COALESCE(archived_at, updated_at) ELSE now() END END WHERE id=%s",
            [*values.values(), payload.stage, process_id],
        )
        return _read(conn, process_id)
