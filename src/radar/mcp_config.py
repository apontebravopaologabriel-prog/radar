"""Conecta clientes de IA externos al servidor MCP de Radar: genera la configuración y, con confirmación, la escribe.

Lista cerrada de clientes (sin rutas libres del cliente): cada uno tiene su archivo de configuración conocido. Antes de
modificar un archivo existente se guarda una copia `.radar-bak`, se conservan los demás servidores y la escritura es atómica.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

SERVER_NAME = "radar"
JSON_CLIENTS = ("claude_desktop", "cursor", "gemini_cli")
LABELS = {
    "claude_desktop": "Claude Desktop",
    "claude_code": "Claude Code",
    "cursor": "Cursor",
    "gemini_cli": "Gemini CLI",
}


def server_command() -> str:
    """Ruta del ejecutable `radar-mcp`: junto al instalador, en el entorno virtual o en el PATH."""
    name = "radar-mcp.exe" if os.name == "nt" else "radar-mcp"
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).parent / name)
    beside = Path(sys.executable).parent / name
    return str(beside) if beside.exists() else (shutil.which("radar-mcp") or name)


def server_entry() -> dict[str, Any]:
    entry: dict[str, Any] = {"command": server_command()}
    if os.getenv("RADAR_DB_PATH"):
        entry["env"] = {"RADAR_DB_PATH": os.environ["RADAR_DB_PATH"]}
    return entry


def config_path(client: str) -> Path:
    home = Path.home()
    if client == "claude_desktop":
        if os.name == "nt":
            return Path(os.getenv("APPDATA", home / "AppData/Roaming")) / "Claude/claude_desktop_config.json"
        if sys.platform == "darwin":
            return home / "Library/Application Support/Claude/claude_desktop_config.json"
        return home / ".config/Claude/claude_desktop_config.json"
    if client == "cursor":
        return home / ".cursor/mcp.json"
    if client == "gemini_cli":
        return home / ".gemini/settings.json"
    raise ValueError(f"Cliente desconocido: {client}")


def describe() -> dict[str, Any]:
    entry = server_entry()
    clients = []
    for client, label in LABELS.items():
        item: dict[str, Any] = {"id": client, "label": label}
        if client in JSON_CLIENTS:
            path = config_path(client)
            item |= {"config_file": str(path), "exists": path.exists(), "can_install": True,
                     "snippet": json.dumps({"mcpServers": {SERVER_NAME: entry}}, indent=2, ensure_ascii=False)}
        else:
            quoted = f'"{entry["command"]}"' if " " in entry["command"] else entry["command"]
            item |= {"can_install": False, "command": f"claude mcp add {SERVER_NAME} -- {quoted}"}
        clients.append(item)
    return {"command": entry["command"], "clients": clients,
            "note": "Reinicia el cliente después de instalar. Radar no abre ningún puerto: el cliente lanza radar-mcp por stdio."}


def install(client: str) -> dict[str, Any]:
    """Añade Radar a la configuración del cliente. Conserva lo demás y deja una copia del archivo anterior."""
    if client not in JSON_CLIENTS:
        raise ValueError(f"No se puede instalar automáticamente en {client}; usa el comando que se muestra.")
    path = config_path(client)
    data: dict[str, Any] = {}
    backup = None
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
        except ValueError as exc:
            raise ValueError(f"{path} no es JSON válido; corrígelo o usa la configuración manual ({exc}).") from exc
        if not isinstance(data, dict):
            raise ValueError(f"{path} tiene un formato inesperado.")
        backup = path.with_name(path.name + ".radar-bak")
        shutil.copy2(path, backup)
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError(f"{path}: 'mcpServers' no es un objeto.")  # noqa: TRY004 - el API lo trata como entrada inválida
    previous = servers.get(SERVER_NAME)
    servers[SERVER_NAME] = server_entry()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".radar-tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)
    return {"client": client, "config_file": str(path), "backup": str(backup) if backup else None,
            "replaced_existing_radar_entry": previous is not None and previous != servers[SERVER_NAME],
            "restart": f"Reinicia {LABELS[client]} para que cargue Radar."}
