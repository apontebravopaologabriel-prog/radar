"""Herramientas de ayuda, estado del sistema, mantenimiento, captura y pesos del score."""

from __future__ import annotations

from radar import maintenance, system
from radar.db.queries import get_profile
from radar.feed import setup_status
from radar.help import help_topics, read_help
from radar.refresh import refresh_status, start_place_refresh
from radar.tools_registry import tool


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


@tool()
def audit_classification(sample: int = 12) -> dict:
    """Solo lectura: verifica si las áreas y la relevancia guardadas coinciden con las reglas vigentes.
    Devuelve el % de desfase, las transiciones más comunes y ejemplos. Úsala cuando los conteos por área
    o distrito parezcan raros o la persona pida revisar la calidad de los datos."""
    from radar.query_context import CURRENT_QUERY

    return maintenance.classification_audit(sample, CURRENT_QUERY.get().values()["market_id"])


@tool(write=True)
def reclassify_jobs() -> dict:
    """Reclasifica todas las ofertas guardadas con las reglas vigentes (áreas y relevancia). No borra
    ofertas y guarda una copia reversible. Proponla solo tras audit_classification si hay desfase."""
    return maintenance.reclassify_jobs()


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
