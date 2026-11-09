"""Registro base y decorador `@tool` compartido por las familias de herramientas de Radar."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any

from pydantic import create_model

from radar.freshness import DEFAULT_MAX_AGE_DAYS


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    fn: Callable[..., dict]
    write: bool
    chat: bool  # expuesta al agente de chat de la app

    def json_schema(self) -> dict[str, Any]:
        """Esquema JSON de los parámetros, derivado de la firma de la función."""
        fields = {
            name: (
                p.annotation if p.annotation is not inspect.Parameter.empty else Any,
                ... if p.default is inspect.Parameter.empty else p.default,
            )
            for name, p in inspect.signature(self.fn).parameters.items()
        }
        schema = create_model(f"{self.name}_args", **fields).model_json_schema()  # type: ignore[call-overload]
        schema.pop("title", None)
        for prop in schema.get("properties", {}).values():
            prop.pop("title", None)
            # El modelo decide qué omitir por `required` (o su ausencia), no por el valor por defecto:
            # Tool.call() ya lo aplica al ejecutar. Quitarlo ahorra bytes en cada mensaje sin cambiar nada.
            prop.pop("default", None)
        return schema

    def call(self, arguments: dict[str, Any]) -> dict:
        """Valida los argumentos contra la firma (tipos y requeridos) y ejecuta."""
        fields = {
            name: (
                p.annotation if p.annotation is not inspect.Parameter.empty else Any,
                ... if p.default is inspect.Parameter.empty else p.default,
            )
            for name, p in inspect.signature(self.fn).parameters.items()
        }
        model = create_model(f"{self.name}_args", **fields)  # type: ignore[call-overload]
        parsed = model(**arguments)
        return self.fn(**parsed.model_dump(exclude_unset=True))


REGISTRY: dict[str, Tool] = {}

MARKET_READS = frozenset({
    "search_saved_jobs", "get_market_summary", "list_recommended_jobs", "get_today_feed",
    "find_jobs_near", "get_job_details", "explain_job_fit", "compare_jobs", "get_skill_demand",
    "get_market_breakdown", "get_place_profile", "compare_places", "get_salary_stats",
    "plan_learning", "get_skill_impact", "audit_classification",
})


def _market_reader(fn):
    from radar.query_context import CURRENT_QUERY, resolve_context, using_query

    signature = inspect.signature(fn)

    @wraps(fn)
    def scoped(*args, **kwargs):
        market_id = kwargs.pop("market_id", None)
        supplied = dict(signature.bind_partial(*args, **kwargs).arguments)
        if fn.__name__ in {"find_jobs_near", "compare_places"}:
            supplied["place"] = ""
            supplied["near"] = ""
        base = CURRENT_QUERY.get()
        if "max_age_days" not in supplied and not (base and "max_age_days" in base.values()):
            parameter = signature.parameters.get("max_age_days")
            supplied["max_age_days"] = parameter.default if parameter else DEFAULT_MAX_AGE_DAYS
        scope = resolve_context({**supplied, "market_id": market_id}, base)
        bound = signature.bind_partial(*args, **kwargs)
        for name, value in scope.values().items():
            if name == "place" and fn.__name__ == "find_jobs_near":
                continue
            if name in signature.parameters:
                bound.arguments[name] = None if value == "" else value
        with using_query(scope):
            result = fn(*bound.args, **bound.kwargs)
        return {**result, "query_context": scope.values()}

    scoped.__signature__ = signature.replace(parameters=[*signature.parameters.values(),
        inspect.Parameter("market_id", inspect.Parameter.KEYWORD_ONLY, default=None, annotation=str | None)])
    return scoped


def tool(*, write: bool = False, chat: bool = True):
    def register(fn: Callable[..., dict]) -> Callable[..., dict]:
        if fn.__name__ in MARKET_READS:
            fn = _market_reader(fn)
        REGISTRY[fn.__name__] = Tool(
            fn.__name__, inspect.getdoc(fn) or fn.__name__, fn, write, chat
        )
        return fn

    return register


def chat_tools() -> list[Tool]:
    return [t for t in REGISTRY.values() if t.chat]


# Grupos que el chat carga bajo demanda con `load_tools`: sus esquemas pesan en cada mensaje y casi nunca
# se usan. Las herramientas fuera de estos grupos (mercado, ofertas, seguimiento, memoria) van siempre.
TOOL_GROUPS: dict[str, tuple[str, tuple[str, ...]]] = {
    "analitica": ("comparar puestos o distritos, estadísticas salariales, demanda de skills, plan de aprendizaje y consultas SQL libres",
                  ("compare_jobs", "compare_places", "get_salary_stats", "get_skill_demand", "plan_learning", "run_readonly_sql")),
    "cv": ("ver o editar el CV, brecha y plan de cierre, el estudio de CV por oferta (documento, sugerencias de cambios), preparar la postulación",
           ("get_my_cv", "update_cv", "get_closure_plan", "preview_cv", "build_cv", "close_gap", "cv_doc_get", "cv_doc_propose",
            "prepare_application", "list_application_packages")),
    "perfil": ("ver o editar el perfil completo, la línea de carrera, las carreras y paquetes de carrera",
               ("get_user_profile", "get_my_profile", "update_profile_fields", "record_career_event", "get_career_timeline",
                "list_career_tracks", "set_career_track", "create_career_pack")),
    "sistema": ("estado, configuración y mantenimiento del sistema, captura de mercado, evolución histórica, esquema SQL, auditoría de áreas y pesos del score",
                ("audit_classification", "reclassify_jobs", "refresh_market", "get_refresh_status",
                 "get_system_status", "get_setup_status", "get_market_history", "get_data_schema",
                 "set_refresh_schedule", "run_maintenance", "set_score_weights")),
}


def group_of(name: str) -> str | None:
    return next((group for group, (_, names) in TOOL_GROUPS.items() if name in names), None)
