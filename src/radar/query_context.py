"""Immutable per-call market context; never shared between requests or workers."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from radar.careers import active_pack, load_pack


@dataclass(frozen=True)
class QueryContext:
    filters: tuple[tuple[str, str | int | float], ...]

    def values(self):
        return dict(self.filters)


CURRENT_QUERY: ContextVar[QueryContext | None] = ContextVar("radar_query", default=None)
FILTERS = {"geo_scope", "market_id", "max_age_days", "area", "seniority", "work_mode", "min_salary",
           "source", "skill", "search", "relevance_tier", "profile_mode", "place", "near", "radius_km",
           "include_applied", "include_hidden"}


def resolve_context(values: dict, base: QueryContext | None = None) -> QueryContext:
    result = base.values() if base else {"market_id": active_pack().id, "relevance_tier": "market",
                                       "include_applied": False, "include_hidden": False}
    market = values.get("market_id") or result["market_id"]
    load_pack(market)
    if market != result["market_id"]:
        result = {k: v for k, v in result.items() if k not in {"area", "skill", "profile_mode"}}
    result["market_id"] = market
    for key in FILTERS - {"market_id"}:
        if key in values and values[key] is not None:
            value = values[key]
            if key in {"include_applied", "include_hidden"} and not isinstance(value, bool):
                raise ValueError(f"Filtro booleano inválido: {key}")
            if not isinstance(value, (str, int, float)):
                raise ValueError(f"Filtro inválido: {key}")
            result[key] = value
    if "max_age_days" in result:
        result["max_age_days"] = int(result["max_age_days"])
        if not 1 <= result["max_age_days"] <= 365:
            raise ValueError("Antigüedad inválida")
    if "min_salary" in result:
        result["min_salary"] = float(result["min_salary"]) if result["min_salary"] != "" else ""
    return QueryContext(tuple(sorted(result.items())))


def ui_context(context: dict | None) -> QueryContext | None:
    filters = (context or {}).get("filters") or {}
    if not isinstance(filters, dict) or not filters.get("market_id"):
        return None
    geo = {"place": (context or {}).get("district") or ""}
    radar = (context or {}).get("radar")
    if (context or {}).get("mode") == "radar" and isinstance(radar, dict):
        geo = {"place": "", "near": radar.get("center") or "", "radius_km": float(radar.get("radiusKm", 5))}
    return resolve_context({"max_age_days": 7, **geo, **filters})


@contextmanager
def using_query(context: QueryContext | None):
    token = CURRENT_QUERY.set(context)
    try:
        yield
    finally:
        CURRENT_QUERY.reset(token)
