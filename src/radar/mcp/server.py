from __future__ import annotations

import functools
import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from radar.help import help_topics, read_help
from radar.insights import data_schema
from radar.settings import get_setting
from radar.tools import mcp_tools

load_dotenv()

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
WRITE_TOOL = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)

MCP_INSTRUCTIONS = (
    "Radar es el observatorio de inteligencia laboral e Inbox de triaje de Paolo en SQLite "
    "(~/.local/share/radar/radar.db + cv_master.json), articulado con /home/paolo/Documents/Work/Postulaciones/<Empresa>/ "
    "(War-Room en Markdown para preparación de entrevistas y narrativa STAR).\n\n"
    "PROTOCOLO DE MÁXIMA EFICIENCIA (MÍNIMAS LLAMADAS) PARA AGENTES EXTERNOS (Antigravity, Claude Code):\n"
    "1. PREPARACIÓN DE ENTREVISTAS Y NARRATIVA (1 sola llamada): Usa `get_interview_dossier(query_or_job_id)` cuando "
    "la persona pida preparar una entrevista, guion STAR o análisis de una empresa/puesto. Busca automáticamente "
    "incluso en ofertas ya marcadas como `applied` (postuladas) u ocultas y devuelve en un solo paso la descripción "
    "congelada de la oferta, puntaje/evidencia de encaje (`fit`), brecha determinista (`baseline`) y el `cv_master` real.\n"
    "2. FICHA Y FIT EN 1 LLAMADA: `get_job_details(job_id)` ya incluye el desglose completo de `fit` (dimensiones, "
    "evidencia, coincidencias y brechas). `get_my_cv()` ya incluye tanto `cv_master` como el `profile` de skills y áreas.\n"
    "3. INBOX Y TRIAJE: `search_saved_jobs` y `find_jobs_near` excluyen por defecto ofertas a las que ya postuló "
    "(`applied`) u ocultas (`hidden`). Si buscas una oferta a la que ya postuló, pasa `include_applied=True` o usa "
    "`list_job_applications` / `get_interview_dossier`. Para archivar en el Inbox usa `track_job_application` "
    "(`applied`, `interview`, `ignored`), `favorite_job` o `import_job_url`.\n"
    "4. REGLAS DE INTEGRIDAD: El puntaje de encaje y la brecha (`baseline`) los calcula el código determinista de Radar; "
    "nunca inventes datos en el CV (`update_cv` exige hechos dictados por la persona y `cv_facts` bloquea invenciones). "
    "Antes de ejecutar herramientas de escritura (`readOnlyHint=False`), pide confirmación a la persona."
)

mcp = FastMCP("radar", instructions=MCP_INSTRUCTIONS)


def _read_only() -> bool:
    return get_setting("agent_read_only") == "1"


def _guarded(fn, name: str):
    """Respeta el modo solo lectura también aquí: en el chat de la app lo aplica `execute_tool`,
    pero el servidor MCP llama la función directo y un cliente externo podría ignorar ese ajuste."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if _read_only():
            raise ValueError(f"Modo solo lectura activo en Radar: {name} no puede escribir.")
        return fn(*args, **kwargs)

    return wrapper


# El servidor MCP expone la superficie curada `mcp_tools()` (22 herramientas de alta cohesión),
# omitiendo herramientas acopladas a la UI web, alias duplicados y escrituras sin confirmación.
for _tool in mcp_tools():
    _fn = _guarded(_tool.fn, _tool.name) if _tool.write else _tool.fn
    _annotations = WRITE_TOOL if _tool.write else READ_ONLY
    mcp.tool(name=_tool.name, description=_tool.description, annotations=_annotations)(_fn)


@mcp.resource("radar://help/{topic}")
def help_resource(topic: str) -> str:
    """Ayuda curada de Radar por tema (inicio, hoy, seguimiento, perfil, carrera, mapa, agente...)."""
    return read_help(topic)


@mcp.resource("radar://topics")
def help_index() -> str:
    """Lista de temas de ayuda disponibles."""
    return "\n".join(help_topics())


@mcp.resource("radar://schema")
def schema_resource() -> dict:
    """Tablas y columnas consultables con run_readonly_sql."""
    return data_schema()


@mcp.prompt()
def configurar_radar() -> str:
    """Guía paso a paso para dejar Radar listo (perfil, carrera, mercado)."""
    return (
        "Ayúdame a configurar Radar. Llama a get_setup_status y guíame un paso a la vez: pregunta lo que "
        "falte y propón update_profile solo con lo que yo afirme. Explica el producto con get_help."
    )


@mcp.prompt()
def analizar_mercado(area: str = "", lugar: str = "") -> str:
    """Análisis del mercado actual, opcionalmente por área y lugar."""
    foco = " ".join(x for x in (f"del área {area}" if area else "", f"en {lugar}" if lugar else "") if x)
    return (
        f"Analiza el mercado laboral {foco or 'general'} con datos reales: get_market_breakdown (por área, lugar, sector "
        "y empresa, con filtros), get_place_profile si hay un lugar, get_skill_demand y get_salary_stats. Antes de "
        "concluir, si los conteos por área parecen raros, corre audit_classification. Resume con cifras y cita las herramientas."
    )


@mcp.prompt()
def plan_de_aprendizaje() -> str:
    """Plan para cerrar brechas de skills según el mercado y mi perfil."""
    return (
        "Arma un plan de aprendizaje con plan_learning y get_skill_demand: qué skills me suben más el encaje, "
        "cuánta demanda tienen y en qué orden aprenderlas. Sé concreto y breve."
    )


def main() -> None:
    from radar.security import restrict_umask

    restrict_umask()
    mcp.run(transport=os.getenv("RADAR_MCP_TRANSPORT", "stdio"))
