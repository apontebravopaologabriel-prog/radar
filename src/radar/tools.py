"""Capa única de herramientas de Radar.

El servidor MCP (Antigravity, Claude Code...) y el agente de chat de la app usan estas mismas
funciones. Cada herramienta declara si escribe: las de escritura exigen confirmación explícita en el
chat y nunca envían mensajes ni postulan.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import create_model

from radar import cv_baseline, cv_targets
from radar.careers import CareerPackError, list_packs, load_pack, save_custom_pack
from radar.db.queries import (
    applications,
    career_timeline,
    get_profile,
    job_history,
    list_jobs,
    market_history,
    market_summary,
    recommendations,
    remove_job_favorite,
    set_job_favorite,
)
from radar.db.repository import (
    add_career_event,
    capture_market_snapshot,
    save_profile,
    track_application,
)
from radar.feed import nearby, setup_status, skill_impact, today_feed
from radar.freshness import DEFAULT_MAX_AGE_DAYS
from radar.help import help_topics, read_help
from radar.pipeline import run_ingestion
from radar.settings import get_setting, set_setting


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
        return self.fn(**model(**arguments).model_dump())


REGISTRY: dict[str, Tool] = {}


def tool(*, write: bool = False, chat: bool = True):
    def register(fn: Callable[..., dict]) -> Callable[..., dict]:
        REGISTRY[fn.__name__] = Tool(
            fn.__name__, inspect.getdoc(fn) or fn.__name__, fn, write, chat
        )
        return fn

    return register


def chat_tools() -> list[Tool]:
    return [t for t in REGISTRY.values() if t.chat]


# --- Mercado y ofertas -------------------------------------------------------------------------


@tool(write=True, chat=False)
def ingest_jobs(
    source: str,
    query: str,
    location: str = "Lima",
    limit: int = 25,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> dict:
    """Busca e importa ofertas. Nunca postula ni modifica el perfil del usuario."""
    if source not in {"computrabajo", "jobspy"}:
        raise ValueError("source debe ser computrabajo o jobspy")
    return run_ingestion(source, query, location, min(limit, 100), max_age_days)


@tool(chat=False)
def health() -> dict:
    """Indica que Radar está disponible."""
    return {"status": "ok", "version": "0.1.0"}


@tool()
def search_saved_jobs(
    limit: int = 20,
    seniority: str | None = None,
    area: str | None = None,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    search: str | None = None,
) -> dict:
    """Consulta ofertas ya guardadas (título, empresa, ubicación, área, salario, enlace)."""
    limit = min(max(limit, 1), 30)
    return {"jobs": list_jobs(limit, seniority, area, max_age_days, search=search)}


@tool()
def get_market_summary() -> dict:
    """Devuelve métricas objetivas del mercado almacenado."""
    return market_summary()


@tool()
def list_recommended_jobs(limit: int = 10, max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> dict:
    """Devuelve recomendaciones recientes y verificables con enlace directo."""
    return recommendations(min(max(limit, 1), 20), max_age_days)


@tool()
def get_today_feed(limit: int = 5) -> dict:
    """Ofertas frescas que encajan con el perfil, con el motivo en una línea. Excluye las ocultas
    o ya gestionadas."""
    return today_feed(limit)


@tool()
def find_jobs_near(place: str, radius_km: float = 5.0, limit: int = 15) -> dict:
    """Ofertas recientes dentro de un radio (km) de un distrito de Lima/Callao o de una ciudad del
    Perú (Arequipa, Trujillo, Cusco...), de la más cercana a la más lejana. Distancia aproximada
    entre centroides."""
    return nearby(place, radius_km, limit)


@tool()
def get_skill_impact(limit: int = 8) -> dict:
    """Simula qué skill faltante sube más el encaje si se aprende (nivel básico)."""
    return skill_impact(limit)


@tool()
def get_job_history(job_id: str, limit: int = 20) -> dict:
    """Devuelve observaciones históricas de una oferta sin borrar registros antiguos."""
    return {"job_id": job_id, "observations": job_history(job_id, limit)}


@tool()
def get_market_history(limit: int = 90) -> dict:
    """Consulta snapshots históricos semanales o mensuales del mercado."""
    return {"snapshots": market_history(min(limit, 90))}


@tool(write=True, chat=False)
def capture_market_history(snapshot_date: str | None = None) -> dict:
    """Guarda una fotografía del mercado activo para comparaciones futuras."""
    return {"metrics_saved": capture_market_snapshot(snapshot_date)}


# --- Guía y configuración ------------------------------------------------------------------------


@tool()
def get_setup_status() -> dict:
    """Qué falta para dejar Radar listo (perfil, carrera, mercado, clave de IA) y el siguiente paso.
    Úsala al iniciar una conversación nueva o cuando el usuario pregunte por dónde empezar."""
    return setup_status()


@tool()
def get_help(topic: str = "inicio") -> dict:
    """Explica cómo usar Radar. Apóyate solo en este texto al explicar funciones; no inventes otras.
    Temas: inicio, hoy, seguimiento, perfil, carrera, pesos, agente, mapa, actualizar,
    acceso-remoto, privacidad."""
    return {"topic": topic, "text": read_help(topic), "available_topics": help_topics()}


# --- Perfil y carrera --------------------------------------------------------------------------


@tool()
def get_user_profile() -> dict:
    """Devuelve el perfil separado de las estadísticas del mercado."""
    return {"profile": get_profile()}


@tool(write=True)
def update_profile(
    name: str,
    areas: list[str],
    locations: list[str],
    skills: dict[str, str],
    education: str | None = None,
    work_modes: list[str] | None = None,
) -> dict:
    """Crea o actualiza el perfil real. `skills` mapea skill -> none|basic|intermediate|advanced.
    Solo con lo que el usuario afirmó; nunca inventes niveles."""
    valid = {"none", "basic", "intermediate", "advanced"}
    bad = {k: v for k, v in skills.items() if v not in valid}
    if bad:
        raise ValueError(f"Niveles inválidos: {bad}")
    return {"profile_id": save_profile(name, education, areas, locations, work_modes or [], skills)}


@tool()
def get_career_timeline(limit: int = 50) -> dict:
    """Devuelve la evolución del perfil y los eventos profesionales registrados."""
    return {"events": career_timeline(limit)}


@tool(write=True)
def record_career_event(
    event_type: str,
    title: str,
    description: str | None = None,
    started_on: str | None = None,
    ended_on: str | None = None,
) -> dict:
    """Registra explícitamente un curso, proyecto, empleo, logro o meta profesional."""
    return {"event_id": add_career_event(None, event_type, title, description, started_on, ended_on)}


@tool()
def list_career_tracks() -> dict:
    """Carreras disponibles y la carrera activa (define áreas, competencias y pesos del score)."""
    active = get_setting("career") or "industrial_engineering"
    return {
        "active": active,
        "tracks": [{"id": p.id, "name": p.name, "areas": p.all_areas} for p in list_packs()],
    }


@tool(write=True)
def set_career_track(career_id: str) -> dict:
    """Cambia la carrera activa. Afecta a las ofertas que se ingesten y clasifiquen desde ahora."""
    try:
        pack = load_pack(career_id)
    except CareerPackError as exc:
        raise ValueError(str(exc)) from exc
    set_setting("career", pack.id)
    return {"active": pack.id, "name": pack.name}


@tool(write=True)
def create_career_pack(
    name: str,
    areas: dict[str, list[str]],
    skills: list[str] | None = None,
) -> dict:
    """Crea una carrera propia y la activa. `areas` mapea cada área de trabajo a sus palabras clave
    (por ejemplo {"Tributación": ["sunat", "igv"]}); `skills` son las competencias que se buscarán en
    las ofertas. Úsala solo con datos que el usuario dio o aprobó."""
    try:
        pack = save_custom_pack(name, areas, skills)
    except CareerPackError as exc:
        raise ValueError(str(exc)) from exc
    set_setting("career", pack.id)
    return {"active": pack.id, "name": pack.name, "areas": pack.all_areas}


# --- Seguimiento -------------------------------------------------------------------------------


@tool(write=True)
def favorite_job(job_id: str, favorite: bool = True) -> dict:
    """Marca o desmarca una oferta con estrella (★)."""
    (set_job_favorite if favorite else remove_job_favorite)(job_id)
    return {"job_id": job_id, "is_favorite": favorite}


@tool(write=True)
def track_job_application(job_id: str, status: str = "saved", notes: str | None = None) -> dict:
    """Registra o actualiza el seguimiento de una oferta y conserva cada cambio de estado.
    Estados: saved, applied, interview, offer, rejected, ignored. No postula por el usuario."""
    return {"application_id": track_application(job_id, status, notes)}


@tool()
def list_job_applications(limit: int = 50) -> dict:
    """Lista postulaciones registradas con su estado y enlace original."""
    return {"applications": applications(limit)}


# --- CVs objetivo ------------------------------------------------------------------------------


@tool(chat=False)
def get_target_context(job_ids: list[str]) -> dict:
    """Contexto para redactar CVs objetivo hipotéticos: ofertas (requisitos, skills, descripción,
    distancia desde el distrito real) y el perfil real. Máximo 10 ofertas."""
    context = cv_targets.get_target_context(job_ids)
    profile = context.get("real_profile") or {}
    for job in context["jobs"]:
        if "error" not in job:
            base = cv_baseline.baseline(job["job_id"], profile)
            job["baseline"] = base
            job["readiness"] = cv_baseline.readiness(base, job.get("description") or "")
    return context


@tool()
def list_targets() -> dict:
    """Objetivos actuales (ofertas con estrella) ordenados por cercanía al perfil real, con su brecha
    base calculada por código. La selección la hace el usuario desde la interfaz."""
    return {"targets": cv_baseline.ranked_selection()}


@tool(write=True, chat=False)
def save_target_profile(job_id: str, profile: dict) -> dict:
    """Guarda un CV objetivo HIPOTÉTICO (nunca el CV real ni enviable). `profile` lleva `sections`
    (summary, experience, tools, education, certifications) con ítems {text, origin, quote?, reason?,
    key?, label?, status?} y `gaps` [{item, kind, action, estimate_days?, evidence_to_produce?}].
    origin: explicito (cita), inferido (con reason) o tipico. status: cubierto (con reason citando el
    perfil real), parcial o falta. kind: dias, semanas o no_cerrable_rapido. `key` agrupa el mismo requisito entre puestos en la matriz y `label` es su nombre corto. Devuelve errores si el
    esquema no valida; el estado de los requisitos que Radar ya calculó (`baseline`, con su `key`) no
    se puede reasignar: prevalece el del código; la empresa, el título y la distancia los calcula Radar."""
    return cv_targets.save_target(job_id, profile)


@tool()
def get_target_matrix() -> dict:
    """Matriz de brechas entre los CVs objetivo guardados (requisitos con `key` por puesto)."""
    return cv_targets.build_matrix(cv_targets.load_targets())


@tool()
def resolve_nearest_districts(reference: str, limit: int = 3) -> dict:
    """Distritos más cercanos a una zona mencionada en una oferta, con km aproximados."""
    return {"districts": cv_targets.districts_near(reference, limit)}
