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
    "Radar manages Paolo's job search in SQLite. "
    "Pass company/role text directly in `job_id` (or `job_ids`) to `track_job_application` with "
    "responded, interview, offer, rejected, or ignored; only call `list_job_applications(compact=true, query=...)` "
    "to disambiguate. Ask confirmation before writes.\n"
    "For interview prep or STAR scripts, call `get_interview_dossier` once and save prep Markdowns in "
    "`/home/paolo/Documents/Work/prep/<company>.md` (`kebab-case`, H1 `# <Company> — <Role Title>`, adapting `prep/narrativa.md`). Rely on Radar scores/evidence and real CV facts."
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
    """Step-by-step guide to review and update Paolo's Radar CV and profile."""
    return (
        "Inspect my current profile with `get_my_cv`, point out missing or stale fields, "
        "and propose `update_profile_fields` or `update_cv` changes only with facts I confirm."
    )


@mcp.prompt()
def analizar_mercado(area: str = "", lugar: str = "") -> str:
    """Market analysis using real Radar data, optionally filtered by area and location."""
    focus = " ".join(x for x in (f"for area {area}" if area else "", f"in {lugar}" if lugar else "") if x)
    return (
        f"Analyze the job market {focus or 'overall'} using `get_market_breakdown`, "
        "`get_place_profile` (if a location is given), `get_skill_demand`, and `get_salary_stats`. "
        "Summarize concisely with numbers and cite the tools used."
    )


@mcp.prompt()
def plan_de_aprendizaje() -> str:
    """Plan to close skill gaps based on market demand and Paolo's CV."""
    return (
        "Build a skill-closure plan using `get_my_cv` and `get_skill_demand`: "
        "which skills raise my fit most, their demand, and the recommended learning order. Be concise."
    )


def main() -> None:
    from radar.security import restrict_umask

    restrict_umask()
    mcp.run(transport=os.getenv("RADAR_MCP_TRANSPORT", "stdio"))
