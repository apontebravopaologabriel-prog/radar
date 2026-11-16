"""Endpoints de mercado, feed, lugares, carreras, refresh y diagnóstico."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from radar import __version__, tools
from radar.agent.loop import agent_enabled, read_only
from radar.agent.provider import load_config
from radar.careers import (
    WEIGHT_KEYS,
    CareerPackError,
    active_pack,
    effective_weights,
    list_packs,
    load_pack,
)
from radar.db.queries import get_profile
from radar.db.repository import recompute_scores
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
from radar.settings import set_json_setting, set_setting

router = APIRouter(prefix="/api")


@router.get("/today")
def today(limit: int = Query(default=5, ge=1, le=20)) -> dict[str, Any]:
    return today_feed(limit)


@router.get("/setup/status")
def setup() -> dict[str, Any]:
    return setup_status()


@router.get("/places")
def places() -> dict[str, Any]:
    return {"groups": place_catalog()["groups"], "default": default_place()}


@router.get("/map/places")
def map_place_counts() -> dict[str, Any]:
    return {"places": map_places()}


@router.get("/nearby")
def nearby_jobs(
    place: str = Query(min_length=2, max_length=60),
    radius_km: float = Query(default=10.0, gt=0, le=50),
    limit: int = Query(default=40, ge=1, le=100),
) -> dict[str, Any]:
    result = nearby(place, radius_km, limit)
    if result is None:
        raise HTTPException(status_code=404, detail="Lugar no encontrado")
    return result


@router.get("/skills/impact")
def impact(limit: int = Query(default=8, ge=1, le=30)) -> dict[str, Any]:
    return {"skills": skill_impact(limit)}


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
    market_ids: list[str] = Field(default_factory=list, max_length=4)
    places: list[str] = Field(default_factory=list, max_length=3)
    limit: int = Field(default=50, ge=1, le=50)


class RefreshStatus(BaseModel):
    running: bool
    done: int
    total: int
    created: int
    errors: list[str]
    current: str | None
    started_at: float | None
    finished_at: float | None
    market_ids: list[str] = Field(default_factory=list)


@router.post("/refresh", status_code=202, response_model=RefreshStatus, response_model_exclude_unset=True)
def refresh(payload: RefreshRequest) -> dict[str, Any]:
    try:
        return start_refresh(payload.places or None, limit=payload.limit, market_ids=payload.market_ids or None)
    except CareerPackError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/refresh/status", response_model=RefreshStatus, response_model_exclude_unset=True)
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
    backups = sorted((path.parent / "backups").glob("radar-*.db"))
    config = load_config()
    return {
        "version": __version__,
        "database": {
            "path": str(path),
            "size_mb": round(path.stat().st_size / 1e6, 1) if path.exists() else 0,
            "backups": [b.name for b in backups][-5:],
        },
        "jobs": {"active": jobs, "last_14_days": fresh, "newest_published": str(newest) if newest else None},
        "career": active_pack().name,
        "agent": {
            "enabled": agent_enabled(),
            "provider": config.provider,
            "model": config.model,
            "key": bool(config.api_key),
            "read_only": read_only(),
            "conversations": conversations,
        },
        "refresh": refresh_status(),
        "tools": len(tools.chat_tools()),
    }


@router.post("/system/backup")
def create_backup() -> dict[str, Any]:
    """Crea una copia consistente de la base de datos SQLite en la carpeta `backups/`."""
    from radar.system import backup_database

    return backup_database()


@router.get("/markets")
def markets() -> dict:
    """Describe both independent market taxonomies without changing the active career."""
    return {
        "markets": [
            {
                "id": pack.id,
                "name": pack.name,
                "areas": {"core": sorted(pack.core_areas), "adjacent": sorted(pack.adjacent_areas)},
            }
            for pack in list_packs()
        ]
    }


@router.get("/markets/{market_id}/profile")
def market_profile(market_id: str) -> dict:
    from radar.markets import search_profile

    try:
        return search_profile(market_id)
    except CareerPackError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/markets/{market_id}/profile")
def update_market_profile(market_id: str, preferences: dict[str, list[str]]) -> dict:
    from radar.markets import save_search_profile

    try:
        return save_search_profile(market_id, preferences)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
