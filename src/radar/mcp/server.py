from __future__ import annotations

import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from radar.tools import REGISTRY

load_dotenv()
mcp = FastMCP("radar")

# Las herramientas viven en radar.tools y son las mismas que usa el agente de chat de la app.
for _tool in REGISTRY.values():
    mcp.tool(name=_tool.name, description=_tool.description)(_tool.fn)


def main() -> None:
    mcp.run(transport=os.getenv("RADAR_MCP_TRANSPORT", "stdio"))
