"""Herramientas de perfil, memoria, carreras y seguimiento de postulaciones."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from radar import profile_edit
from radar.agent.history import search_conversations
from radar.agent.memory import save_memory, search_memories
from radar.careers import CareerPackError, list_packs, load_pack, save_custom_pack
from radar.db.queries import (
    applications,
    career_timeline,
    get_job,
    get_profile,
    remove_job_favorite,
    set_job_favorite,
    set_job_user_status,
)
from radar.db.repository import (
    add_career_event,
    save_profile,
    track_application,
    untrack_application,
)
from radar.settings import get_setting, set_setting
from radar.tools_registry import tool


@tool()
def get_user_profile() -> dict:
    """Devuelve el perfil separado de las estadísticas del mercado."""
    return {"profile": get_profile()}


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
