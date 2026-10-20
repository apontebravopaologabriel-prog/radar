"""Capa única de herramientas de Radar.

El servidor MCP (opcional, para agentes externos) y el agente de chat de la app usan estas mismas
funciones. Cada herramienta declara si escribe: las de escritura exigen confirmación explícita en el
chat y nunca envían mensajes ni postulan.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import create_model

from radar import (
    __version__,
    cv_baseline,
    cv_build,
    cv_doc,
    cv_edit,
    cv_packages,
    cv_plan,
    cv_targets,
    insights,
    maintenance,
    profile_edit,
    system,
)
from radar.agent.history import search_conversations
from radar.agent.memory import save_memory, search_memories
from radar.careers import CareerPackError, list_packs, load_pack, save_custom_pack
from radar.db.queries import (
    applications,
    career_timeline,
    get_job,
    get_profile,
    job_history,
    list_jobs,
    market_history,
    market_summary,
    recommendations,
    remove_job_favorite,
    set_job_favorite,
    set_job_user_status,
)
from radar.db.repository import (
    add_career_event,
    capture_market_snapshot,
    save_profile,
    track_application,
    untrack_application,
)
from radar.feed import nearby, setup_status, skill_impact, today_feed
from radar.freshness import DEFAULT_MAX_AGE_DAYS
from radar.help import help_topics, read_help
from radar.links import google_maps_search_url
from radar.pipeline import run_ingestion
from radar.refresh import refresh_status, start_place_refresh
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


# Grupos que el chat carga bajo demanda con `load_tools`: sus esquemas pesan en cada mensaje y casi nunca
# se usan. Las herramientas fuera de estos grupos (mercado, ofertas, seguimiento, memoria) van siempre.
TOOL_GROUPS: dict[str, tuple[str, tuple[str, ...]]] = {
    "cv": ("ver o editar el CV, brecha y plan de cierre, el estudio de CV por oferta (documento, sugerencias de cambios), preparar la postulación",
           ("get_my_cv", "update_cv", "get_closure_plan", "preview_cv", "build_cv", "close_gap", "cv_doc_get", "cv_doc_propose",
            "prepare_application", "list_application_packages")),
    "perfil": ("editar el perfil, la línea de carrera, las carreras y paquetes de carrera",
               ("update_profile_fields", "record_career_event", "get_career_timeline", "list_career_tracks",
                "set_career_track", "create_career_pack")),
    "sistema": ("estado y mantenimiento del sistema, captura de mercado, auditoría de áreas y pesos del score",
                ("audit_classification", "reclassify_jobs", "refresh_market", "get_refresh_status",
                 "get_system_status", "set_refresh_schedule", "run_maintenance", "set_score_weights")),
}


def group_of(name: str) -> str | None:
    return next((group for group, (_, names) in TOOL_GROUPS.items() if name in names), None)


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
    if source not in {"computrabajo", "jobspy", "bumeran", "empleos"}:
        raise ValueError("source debe ser computrabajo, jobspy, bumeran o empleos")
    return run_ingestion(source, query, location, min(limit, 100), max_age_days)


@tool(chat=False)
def health() -> dict:
    """Indica que Radar está disponible."""
    return {"status": "ok", "version": __version__}


@tool()
def search_saved_jobs(
    limit: int = 20,
    seniority: str | None = None,
    area: str | None = None,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    search: str | None = None,
    sector: str | None = None,
    exclude_sector: str | None = None,
    include_applied: bool = False,
    include_hidden: bool = False,
) -> dict:
    """Ofertas guardadas (título, empresa, lugar, área, sector, salario, `url`, score y extracto). Excluye postuladas
    u ocultas salvo `include_applied` o `include_hidden`. `search` busca en texto; `sector` filtra uno y
    `exclude_sector` excluye varios separados por coma."""
    limit = min(max(limit, 1), 30)
    excluded = [x.strip() for x in (exclude_sector or "").split(",") if x.strip()]
    jobs = list_jobs(
        limit,
        seniority,
        area,
        max_age_days,
        search=search,
        sector=sector,
        exclude_sectors=excluded or None,
        include_applied=include_applied,
        include_hidden=include_hidden,
    )
    slim = []
    for job in jobs:  # sin la descripción completa (≈3 KB por oferta): eso lo da get_job_details
        item = {k: job.get(k) for k in ("id", "title", "company", "location", "seniority", "work_mode", "salary_min",
                                        "salary_max", "salary_currency", "published_at", "primary_area", "sector",
                                        "relevance_tier", "relevance_score", "url", "is_favorite", "user_application")}
        item["snippet"] = (job.get("description_clean") or "")[:110]
        item["google_maps_url"] = google_maps_search_url(job.get("company"), job.get("location"))
        slim.append(item)
    return {"jobs": slim}


@tool(chat=False)
def get_market_summary() -> dict:
    """Devuelve métricas objetivas del mercado almacenado."""
    return market_summary()


@tool(chat=False)
def list_recommended_jobs(
    limit: int = 10,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    include_applied: bool = False,
    include_hidden: bool = False,
) -> dict:
    """Devuelve recomendaciones recientes y verificables con enlace directo. Excluye por defecto postuladas y ocultas."""
    return recommendations(min(max(limit, 1), 20), max_age_days, include_applied=include_applied, include_hidden=include_hidden)


@tool()
def get_today_feed(limit: int = 5) -> dict:
    """Ofertas frescas que encajan con el perfil, con el motivo en una línea. Excluye las ocultas
    o ya gestionadas."""
    return today_feed(limit)


@tool()
def find_jobs_near(
    place: str,
    radius_km: float = 5.0,
    limit: int = 15,
    include_applied: bool = False,
    include_hidden: bool = False,
) -> dict:
    """Ofertas en un radio (km) de un distrito o ciudad por cercanía. Excluye postuladas u ocultas salvo
    `include_applied` o `include_hidden`. En `by_place`, `precision` "district" es distrito real; "city"/"department"
    son ofertas sin distrito específico."""
    return nearby(place, radius_km, limit, include_applied=include_applied, include_hidden=include_hidden)


@tool()
def get_job_details(job_id: str) -> dict:
    """Ficha completa de una oferta: descripción, skills exigidas, salario, ubicación, tu puntaje de
    encaje y tu seguimiento. Los ids salen de search_saved_jobs, get_today_feed o find_jobs_near."""
    return insights.job_details(job_id)


@tool()
def explain_job_fit(job_id: str) -> dict:
    """Desglose del puntaje de encaje de una oferta: aporte de cada dimensión, skills que coinciden y
    las que faltan."""
    return insights.explain_fit(job_id)


@tool()
def compare_jobs(job_ids: list[str]) -> dict:
    """Compara 2 a 4 ofertas: datos clave, encaje, skills comunes y exclusivas de cada una."""
    return insights.compare(job_ids)


@tool()
def get_skill_demand(area: str | None = None, max_age_days: int = 30, limit: int = 15) -> dict:
    """Skills más pedidas por el mercado (nº de ofertas y % del total), con tu nivel en cada una.
    `area` filtra por área primaria."""
    return insights.skill_demand(area, max_age_days, limit)


@tool()
def get_market_breakdown(by: str, max_age_days: int = 14, limit: int = 10, area: str | None = None,
                         place: str | None = None, sector: str | None = None, exclude_sector: str | None = None,
                         search: str | None = None) -> dict:
    """Cuenta ofertas vigentes agrupadas por `by` (area, place, company, work_mode, seniority, sector o source), con
    filtros opcionales: area, place, sector, exclude_sector (varios con coma) y search (texto en título o empresa).
    Con by=place, una fila con `precision` "city" o "department" (p.ej. "Lima") agrupa ofertas sin distrito preciso;
    no la presentes junto a los distritos reales como si fuera uno más."""
    return insights.market_breakdown(by, max_age_days, limit, area, place, sector, exclude_sector, search)


@tool()
def get_place_profile(place: str, max_age_days: int = 30) -> dict:
    """Radiografía de UN distrito o ciudad: nº de ofertas de ese lugar (no del total), áreas, empresas, modalidad,
    seniority, salario mediano y señales de producción. Úsala cuando la persona pregunte por el distrito seleccionado."""
    return insights.place_profile(place, max_age_days)


@tool()
def compare_places(place_a: str, place_b: str, max_age_days: int = 30, focus: str | None = None) -> dict:
    """Compara dos distritos en volumen, áreas, modalidad, seniority, salario mediano y señales de producción.
    `focus` solo resalta un tramo si la persona lo pidió; sin él, la comparación es general."""
    return insights.compare_places(place_a, place_b, max_age_days, focus)


@tool()
def get_salary_stats(area: str | None = None, place: str | None = None, max_age_days: int = 60) -> dict:
    """Mínimo, mediana y máximo de los salarios publicados (solo ofertas que los declaran)."""
    return insights.salary_stats(area, place, max_age_days)


@tool()
def plan_learning(limit: int = 5) -> dict:
    """Skills que más suben tu encaje si las aprendes, con su demanda en el mercado. Base para un plan."""
    return insights.learning_plan(limit)


@tool()
def get_data_schema() -> dict:
    """Tablas y columnas consultables con run_readonly_sql."""
    return insights.data_schema()


@tool()
def run_readonly_sql(sql: str) -> dict:
    """SQL de solo lectura (SELECT/WITH, máx. 50 filas) para lo que las demás herramientas no cubren; úsala como
    último recurso y con pocos intentos. Ofertas vigentes: FROM jobs j LEFT JOIN companies c ON c.id=j.company_id
    WHERE j.is_active=1 AND j.duplicate_status='canonical' AND j.relevance_tier IN ('core','adjacent'). Área: JOIN
    job_areas ja ON ja.job_id=j.id AND ja.is_primary=1 JOIN industrial_areas ia ON ia.id=ja.area_id. Columnas útiles
    de jobs: title, location, sector, work_mode, seniority, salary_min/max, published_at (texto ISO). Si falla, el error
    trae el esquema: no hace falta llamar a get_data_schema."""
    return insights.readonly_sql(sql)


@tool(chat=False)
def get_skill_impact(limit: int = 8) -> dict:
    """Simula qué skill faltante sube más el encaje si se aprende (nivel básico)."""
    return skill_impact(limit)


@tool(chat=False)
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


@tool()
def get_my_cv() -> dict:
    """Tu CV real (cv_master): resumen, experiencia, formación, certificaciones, idiomas, herramientas declaradas y
    brechas de evidencia. Úsala cuando pregunten por tu experiencia, formación, certificaciones o cómo te ves
    frente a un puesto. Es la fuente sobre tu trayectoria; get_user_profile solo trae skills y preferencias."""
    cv = cv_targets.load_profile()
    if cv is None:
        return {"cv": None, "note": "Aún no hay CV cargado (cv_master.json en la carpeta de datos)."}
    return {"cv": {k: v for k, v in cv.items() if not k.startswith("_") and k != "has_photo"}}


@tool(write=True)
def update_cv(section: str, action: str, item: dict | None = None, match: str | None = None) -> dict:
    """Edita tu CV real (lo que ves en CVs). section: certifications {name, issuer, date AAAA-MM}, experience {role,
    company, location, from, to, bullets[]}, education {institution, program, from, to, status, skills[]}, languages
    {name, level, evidence}, projects {name, description, skills[], date, link}, contact {email, phone, linkedin,
    location} (action update), gaps {text}, summary o headline {text}. action: add | update | remove; en update y remove,
    `match` es un texto que identifica el ítem. Solo con lo que la persona dictó: pregunta lo que falte (emisor,
    fecha). Guarda copia previa. Skills y herramientas: update_profile."""
    return cv_edit.update_cv(section, action, item, match)


@tool()
def get_user_memory(query: str = "", limit: int = 8) -> dict:
    """Busca memoria durable aprobada por la persona. No incluye el historial completo del chat."""
    return {"memories": search_memories(query, min(max(limit, 1), 20))}


@tool()
def search_past_conversations(query: str, limit: int = 5) -> dict:
    """Busca en tus conversaciones anteriores con el agente (todas las palabras de `query`) y devuelve título, fecha y
    fragmentos. Úsala cuando digan «como hablamos», «lo de ayer» o pidan retomar algo; no cargues conversaciones enteras."""
    return {"conversations": search_conversations(query, limit)}


@tool(write=True)
def remember_user(topic_key: str, content: str, memory_type: str = "preference") -> dict:
    """Guarda una preferencia, meta o decisión durable después de que la persona la confirme."""
    return {"memory": save_memory(content, topic_key=topic_key, memory_type=memory_type, source="chat")}


@tool()
def get_my_profile() -> dict:
    """Tu perfil completo tal como lo ve la persona en Ajustes: nombre, titular, resumen, distrito de casa, contacto,
    formación, áreas objetivo, lugares, modalidades y skills con su nivel, más qué le falta y por qué importa. Úsala
    antes de editar algo, para partir de lo que hay."""
    return profile_edit.get_full()


@tool(write=True)
def update_profile_fields(
    name: str | None = None,
    headline: str | None = None,
    summary: str | None = None,
    home_district: str | None = None,
    education: str | None = None,
    contact: dict[str, str] | None = None,
    areas: list[str] | None = None,
    areas_add: list[str] | None = None,
    areas_remove: list[str] | None = None,
    locations: list[str] | None = None,
    locations_add: list[str] | None = None,
    locations_remove: list[str] | None = None,
    work_modes: list[str] | None = None,
    skills: dict[str, str] | None = None,
) -> dict:
    """Edita SOLO los campos que pases del perfil (lo que se ve y edita en Ajustes); lo demás no se toca. Pasa
    únicamente lo que la persona pidió cambiar y con lo que ella dijo: nunca inventes datos ni niveles. Escalares:
    name, headline, summary, home_district (distrito de casa), education; un texto vacío borra el campo (no name).
    contact: {email, phone, linkedin, location} (fusiona; vacío quita ese dato). Listas: areas/locations reemplazan
    todo; *_add y *_remove agregan o quitan elementos sueltos (preferidos). work_modes: onsite (presencial), hybrid o
    remote. skills: {skill: none|basic|intermediate|advanced|remove} (solo skills del catálogo de la carrera).
    Devuelve el antes/después y un `undo`. Experiencia, certificados y proyectos van con update_cv."""
    fields = {k: v for k, v in {
        "name": name, "headline": headline, "summary": summary, "home_district": home_district,
        "education": education, "contact": contact, "areas": areas, "areas_add": areas_add,
        "areas_remove": areas_remove, "locations": locations, "locations_add": locations_add,
        "locations_remove": locations_remove, "work_modes": work_modes, "skills": skills,
    }.items() if v is not None}
    if not fields:
        raise ValueError("Indica al menos un campo a cambiar")
    return profile_edit.patch(fields)


_STATUS_PREVIEW_ES = {
    "saved": "Guardada",
    "applied": "Postulé (sale de ofertas activas)",
    "interview": "Entrevista",
    "offer": "Oferta recibida",
    "rejected": "Descartada",
    "ignored": "Oculta (no me interesa)",
    "visible": "Restaurar a activas",
}


def _preview_job_label(job_id: str) -> str:
    if not job_id:
        return "Oferta desconocida"
    row = get_job(str(job_id))
    if not row:
        return f"ID {str(job_id)[:12]}"
    title = row.get("title") or "Sin título"
    company = row.get("company") or "Empresa confidencial"
    loc = row.get("location")
    return f"{title} · {company}" + (f" ({loc})" if loc else "")


def _preview_track(args: dict[str, Any]) -> list[str]:
    job_id = str(args.get("job_id") or "")
    status = str(args.get("status") or "saved")
    notes = str(args.get("notes") or "").strip()
    lines = [
        f"Oferta: {_preview_job_label(job_id)}",
        f"Estado: {_STATUS_PREVIEW_ES.get(status, status)}",
    ]
    if notes:
        lines.append(f"Nota: {notes[:120]}")
    return lines


def _preview_favorite(args: dict[str, Any]) -> list[str]:
    job_id = str(args.get("job_id") or "")
    fav = bool(args.get("favorite", True))
    action = "★ Marcar como favorita" if fav else "☆ Quitar de favoritas"
    return [f"{action}: {_preview_job_label(job_id)}"]


def _preview_import_url(args: dict[str, Any]) -> list[str]:
    from radar.single_import import (
        _extract_portal_offer_info,
        _lookup_existing_in_db,
        _source_name_from_url,
    )

    url = str(args.get("url") or "").strip()
    source = _source_name_from_url(url) if url else "Web"
    raw_id, cand_ids, _, _ = _extract_portal_offer_info(url) if url else (None, [], "", False)
    existing = _lookup_existing_in_db(url, cand_ids) if url else None
    lines = [f"Portal: {source}" + (f" · ID {raw_id[:16]}" if raw_id else "")]
    if existing and existing.get("title"):
        comp = existing.get("company") or "Empresa confidencial"
        lines.append(f"Detectada en Radar: {existing['title']} · {comp}")
    elif args.get("title") or args.get("company"):
        t = args.get("title") or "(título automático)"
        c = args.get("company") or "(empresa automática)"
        lines.append(f"Puesto: {t} · {c}")
    else:
        lines.append(f"Enlace: {url[:90]}{'…' if len(url) > 90 else ''}")
    flags = []
    if args.get("favorite"):
        flags.append("★ Favorita")
    app_st = str(args.get("application_status") or "").strip()
    if app_st:
        flags.append(_STATUS_PREVIEW_ES.get(app_st, app_st))
    if flags:
        lines.append("Seguimiento: " + " · ".join(flags))
    return lines


PREVIEWS: dict[str, Callable[[dict[str, Any]], list[str]]] = {
    "update_profile_fields": lambda args: profile_edit.preview(args),
    "track_job_application": _preview_track,
    "favorite_job": _preview_favorite,
    "import_job_url": _preview_import_url,
    "remember_user": lambda args: [f"[{args.get('topic_key', 'memoria')}] {str(args.get('content', ''))[:140]}"],
}


@tool(write=True, chat=False)
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
    """Registra en la línea de tiempo una meta, nota, entrevista o logro. Certificaciones, empleos y estudios que deban
    verse en tu CV se guardan con update_cv, no aquí."""
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
    """Registra o actualiza el estado de una oferta (al marcar applied/ignored sale de activas).
    Estados: saved, applied, interview, offer, rejected, ignored (oculta), visible (restaura). No postula."""
    if status == "visible":
        untrack_application(job_id)
        set_job_user_status(job_id, "visible")
        return {"job_id": job_id, "status": "visible"}
    if status == "ignored":
        set_job_user_status(job_id, "hidden", "not_interested", notes)
    return {"application_id": track_application(job_id, status, notes), "status": status}


@tool()
def list_job_applications(limit: int = 50) -> dict:
    """Lista postulaciones registradas con su estado y enlace original."""
    return {"applications": applications(limit)}


@tool(write=True)
def import_job_url(
    url: str,
    title: str = "",
    company: str = "",
    location: str = "",
    description: str = "",
    favorite: bool = False,
    application_status: str = "",
) -> dict:
    """Importa una oferta por su URL (Computrabajo, LinkedIn, Bumeran, Empleos Perú u otra web) y calcula su encaje."""
    from radar.single_import import fetch_and_ingest_single_job

    return fetch_and_ingest_single_job(
        url,
        title=title or None,
        company=company or None,
        location=location or None,
        description=description or None,
        favorite=favorite,
        application_status=application_status or None,
    )


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


@tool(chat=False)
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
def get_closure_plan(limit: int = 10) -> dict:
    """Plan para cerrar brechas entre tus objetivos (ofertas con estrella): qué skills cerrar primero, cuántos
    puntos de cercanía sube cada una en cada puesto, en cuántos objetivos aparece y qué % del mercado reciente
    la pide. Incluye lo estructural (años de experiencia, grado), que un curso no cierra, y lo cerrado
    recientemente. Úsala cuando pregunten qué aprender o demostrar primero."""
    return cv_plan.closure_plan(limit)


@tool()
def preview_cv(job_id: str) -> dict:
    """Vista previa del CV descargable para una oferta, sin escribir archivos: qué se incluye de tu CV real, qué
    se omite y por qué, el idioma detectado, el presupuesto de páginas y la cobertura de skills de la oferta
    (demostradas en el cuerpo, solo listadas, ausentes). Nada se inventa: solo elige y ordena lo que ya tienes."""
    return cv_build.select(job_id)


@tool(write=True)
def build_cv(job_id: str, formats: list[str] | None = None) -> dict:
    """Genera el CV para una oferta como DOCX y PDF (formats: docx, pdf) en la carpeta de datos de Radar, sin
    sobrescribir nada. Plantilla sobria de una columna a prueba de ATS. Devuelve rutas, chequeo del PDF (páginas,
    texto extraíble) y la selección. Úsala cuando la persona pida su CV para una oferta; antes conviene
    preview_cv y avisarle de las skills ausentes."""
    return cv_build.build(job_id, formats)


def _clip(text: str, limit: int = 160) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


@tool()
def cv_doc_get(job_id: str) -> dict:
    """Estado del CV de una oferta en el Estudio, tal como lo ve la persona: líneas incluidas (con `id`, texto y de qué cargo
    salen), líneas omitidas y por qué, plantilla, foto, páginas frente al presupuesto, cobertura de skills, avisos y
    sugerencias pendientes. Úsala SIEMPRE antes de proponer cambios: los `id` son los de este resultado."""
    state = cv_doc.state(job_id)
    selection = state["selection"]
    lines: list[dict] = [{"id": "summary", "kind": "perfil", "text": _clip(selection["summary"])},
                         {"id": "headline", "kind": "titular", "text": selection["header"]["headline"]}]
    for role in selection["experience"]:
        lines.append({"id": role["id"], "kind": "cargo", "text": role["title"]})
        lines += [{"id": b["id"], "kind": "viñeta", "text": _clip(b["text"]), "edited": b.get("edited")} for b in role["bullets"]]
    for project in selection["projects"]:
        lines.append({"id": project["id"], "kind": "proyecto", "text": project["title"]})
        lines += [{"id": b["id"], "kind": "viñeta de proyecto", "text": _clip(b["text"])} for b in project["bullets"]]
    lines += [{"id": c["id"], "kind": "certificado", "text": c["title"]} for c in selection["certifications"]]
    lines += [{"id": e["id"], "kind": "formación", "text": e["title"]} for e in selection["education"]]
    return {
        "job": selection["job"], "language": selection["language"], "template": state["document"]["template"],
        "photo": state["document"]["photo"], "pages": state["render"]["pages"], "pages_budget": state["document"]["pages_budget"],
        "over_budget": state["render"]["over_budget"], "lines": lines,
        "omitted": [{"id": o["id"], "text": _clip(o["text"], 100), "reason": o["reason"]} for o in selection["omitted"]],
        "coverage": selection["coverage"], "warnings": state["warnings"], "pending_suggestions": len(state["suggestions"]),
        "templates": state["templates"],
    }


@tool()
def cv_doc_propose(job_id: str, ops: list[dict], note: str = "") -> dict:
    """Propone cambios al CV de una oferta; NO cambian nada hasta que la persona los acepte en el Estudio (antes/después).
    `ops`: lista de operaciones sobre ids de `cv_doc_get`: {"op":"omit","id"}, {"op":"include","id"} (de las omitidas),
    {"op":"move","id","to":índice}, {"op":"edit","id","text"} (reformular una línea) y {"op":"option","name":"template"|"photo"|"pages",
    "value"}. REGLAS: al reformular usa SOLO hechos que ya están en esa línea o en su cargo: un número, empresa, herramienta o
    logro nuevo se marca en rojo y no se puede aceptar. No inventes. Para añadir un dato verdadero, la persona lo agrega a su CV
    maestro (update_cv). `note` explica el porqué en una frase."""
    return cv_doc.propose(job_id, ops, note)


@tool(write=True)
def prepare_application(job_id: str, formats: list[str] | None = None) -> dict:
    """Prepara la postulación: exporta el CV vigente del Estudio (formats: pdf, docx) a la carpeta de esa oferta, junto con una
    copia de la oferta y el registro de lo que se generó. NO envía nada ni postula: la persona sube el archivo en el portal y
    luego lo marca como enviado. Avisa si el CV excede las páginas o tiene advertencias."""
    return cv_packages.export(job_id, formats)


@tool()
def list_application_packages(limit: int = 20) -> dict:
    """Postulaciones preparadas: oferta, carpeta, archivos, estado (preparada o enviada) y fechas. Responde «¿qué CV mandé a
    tal empresa?» y «¿qué tengo preparado?»."""
    return {"packages": [{"job_id": p["job_id"], "title": p["title"], "company": p["company"], "status": p["status"],
                          "exported_at": p["exported_at"], "applied_at": p["applied_at"], "folder": p["folder"],
                          "files": [f["name"] for f in p["files"]]} for p in cv_packages.list_packages(limit)]}


@tool(write=True)
def close_gap(skill: str, kind: str, name: str, issuer: str | None = None, date: str | None = None,
              description: str | None = None, link: str | None = None) -> dict:
    """Registra evidencia REAL que cierra una brecha (la persona la aportó; no inventes nada). skill: la brecha
    (ej. «SQL»). kind: certificado (name debe mencionar la skill; issuer, date AAAA-MM) o proyecto (name y
    description de lo que hizo, mín. 15 caracteres; link opcional). Lo guarda en el CV, quita la nota de brecha
    equivalente, lo anota en la línea de tiempo y devuelve la cercanía de cada objetivo antes y después."""
    return cv_plan.close_gap(skill, kind, name, issuer, date, description, link)


@tool(chat=False)
def get_target_matrix() -> dict:
    """Matriz de brechas entre los CVs objetivo guardados (requisitos con `key` por puesto)."""
    return cv_targets.build_matrix(cv_targets.load_targets())


@tool(chat=False)
def resolve_nearest_districts(reference: str, limit: int = 3) -> dict:
    """Distritos más cercanos a una zona mencionada en una oferta, con km aproximados."""
    return {"districts": cv_targets.districts_near(reference, limit)}


# --- Mantenimiento de datos -------------------------------------------------------------------------


@tool()
def audit_classification(sample: int = 12) -> dict:
    """Solo lectura: verifica si las áreas y la relevancia guardadas coinciden con las reglas vigentes.
    Devuelve el % de desfase, las transiciones más comunes y ejemplos. Úsala cuando los conteos por área
    o distrito parezcan raros o la persona pida revisar la calidad de los datos."""
    return maintenance.classification_audit(sample)


@tool(write=True)
def reclassify_jobs() -> dict:
    """Reclasifica todas las ofertas guardadas con las reglas vigentes (áreas y relevancia). No borra
    ofertas y guarda una copia reversible. Proponla solo tras audit_classification si hay desfase."""
    return maintenance.reclassify_jobs()


# --- Captura de ofertas ------------------------------------------------------------------------------


@tool(write=True)
def refresh_market(place: str, limit: int = 25) -> dict:
    """Busca ofertas nuevas enfocadas en un distrito o ciudad (Indeed/LinkedIn y Computrabajo) y las guarda. Corre en
    segundo plano varios minutos; las fuentes buscan por ciudad, así que el distrito sesga el resultado, no lo limita.
    Luego usa get_refresh_status."""
    return start_place_refresh(place, limit)


@tool()
def get_refresh_status() -> dict:
    """Avance de la captura de ofertas en curso o de la última: pasos hechos, ofertas nuevas y errores."""
    return refresh_status()


# --- Sistema y configuración ---------------------------------------------------------------------------


@tool()
def get_system_status() -> dict:
    """Estado del sistema: BD (tamaño, integridad, respaldos), ofertas por tier, última captura, temporizador de
    captura automática, si las reglas de clasificación están desactualizadas y el estado del agente (sin claves).
    Úsala antes de proponer mantenimiento o cuando pregunten cuándo corre la captura."""
    return system.system_status()


@tool(write=True)
def set_refresh_schedule(days: int, on_boot: bool | None = None) -> dict:
    """Cambia cada cuántos días corre la captura automática (1-30; 0 la desactiva). `on_boot` añade o quita el
    disparo 5 min después de cada arranque del equipo."""
    return system.set_schedule(days, on_boot)


@tool(write=True)
def run_maintenance(task: str, days: int = 45, limit: int = 40) -> dict:
    """Mantenimiento de la BD. task: backup (copia consistente, guarda las últimas 5), repair_data (completa modalidad,
    sector, salario y horario), expire_stale (desactiva ofertas no vistas en `days` días, sin borrarlas),
    check_applications (visita hasta `limit` enlaces y detecta cerradas) o market_snapshot. Haz backup antes de
    tareas que cambian datos si no hay uno reciente."""
    return system.run_maintenance(task, days, limit)


@tool(write=True)
def set_score_weights(weights: dict[str, float]) -> dict:
    """Ajusta los pesos del puntaje de encaje (claves: area, skills, seniority, education, location, preference; cada
    valor 0-1; se normalizan) y recalcula los puntajes. Cambia lo que ves como recomendado."""
    from radar.careers import WEIGHT_KEYS
    from radar.db.repository import recompute_scores
    from radar.settings import set_json_setting

    if set(weights) - set(WEIGHT_KEYS) or any(v < 0 or v > 1 for v in weights.values()):
        raise ValueError(f"Pesos inválidos; claves permitidas: {', '.join(WEIGHT_KEYS)}, valores entre 0 y 1")
    set_json_setting("score_weights", weights)
    profile = get_profile()
    return {"weights": weights, "recomputed": recompute_scores(profile["id"]) if profile else 0}
