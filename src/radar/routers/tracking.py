"""Endpoints de seguimiento de postulaciones (`/api/applications*`)."""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from radar.db.database import connection
from radar.db.queries import applications
from radar.db.repository import track_application, untrack_application
from radar.freshness import visible_date_bounds

router = APIRouter(prefix="/api")


class ApplicationItem(BaseModel):
    id: str
    job_id: str
    title: str
    company: str | None
    status: str  # Existing rows may contain statuses outside the HTTP write set.
    notes: str | None
    applied_at: str | None
    updated_at: str
    url: str | None
    location: str | None
    work_mode: str | None
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    primary_area: str | None
    archived_at: str | None
    published_at: str | None


class ApplicationList(BaseModel):
    applications: list[ApplicationItem]


@router.get("/applications", response_model=ApplicationList)
def list_applications() -> dict[str, Any]:
    return {"applications": applications(200, include_tracking_details=True)}


class TrackingApplicationItem(ApplicationItem):
    archived_from_applied: bool


class TrackingApplications(BaseModel):
    applications: list[TrackingApplicationItem]
    activity: dict[str, int]


@router.get("/applications/tracking", response_model=TrackingApplications)
def tracking_applications() -> dict[str, Any]:
    first_day, _ = visible_date_bounds(7)
    with connection() as conn:
        activity = dict(conn.execute(
            """SELECT date(applied_at, '-5 hours'), COUNT(*) FROM applications
               WHERE date(applied_at, '-5 hours') IS NOT NULL GROUP BY 1"""
        ).fetchall())
    return {
        "applications": applications(include_tracking_details=True, tracking_since=f"{first_day}T00:00:00-05:00"),
        "activity": activity,
    }


class ApplicationUpdate(BaseModel):
    status: str = Field(pattern="^(saved|applied|responded|interview|offer|rejected|ignored)$")
    notes: str | None = Field(default=None, max_length=1000)


class ApplicationUpdated(BaseModel):
    application_id: str
    status: str


@router.put("/applications/{job_id}", response_model=ApplicationUpdated)
def update_application(job_id: str, payload: ApplicationUpdate) -> dict[str, str]:
    try:
        application_id = track_application(job_id, payload.status, payload.notes)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=404, detail="Oferta no encontrada") from exc
    return {"application_id": application_id, "status": payload.status}


class ApplicationRemoved(BaseModel):
    removed: bool


@router.delete("/applications/{job_id}", response_model=ApplicationRemoved)
def remove_application(job_id: str) -> dict[str, bool]:
    """Quita el seguimiento de una oferta (error al marcar «postulé»). No toca la oferta."""
    return {"removed": untrack_application(job_id)}
