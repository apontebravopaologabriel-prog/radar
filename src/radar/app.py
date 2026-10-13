"""`radar app`: abre Radar como aplicación de escritorio (Linux, Windows, macOS).

Inicia la API en un hilo (con el planificador interno de capturas), espera a que responda y abre la interfaz:
en una ventana propia si `pywebview` está instalado (usa WebView2 en Windows) y, si no, en el navegador
predeterminado. Si Radar ya está corriendo en ese puerto, solo abre la ventana.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn

from radar.security import restrict_umask

HOST = "127.0.0.1"
DEFAULT_PORT = 8100
START_TIMEOUT_SECONDS = 30


def port_in_use(port: int, host: str = HOST) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def is_radar(port: int, host: str = HOST) -> bool:
    try:
        with urlopen(f"http://{host}:{port}/api/health", timeout=2) as response:
            return response.status == 200 and b'"status"' in response.read()
    except (URLError, OSError, ValueError):
        return False


def wait_until_ready(port: int, timeout: float = START_TIMEOUT_SECONDS) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_radar(port):
            return True
        time.sleep(0.2)
    return False


def open_window(url: str) -> bool:
    """Abre la interfaz. Devuelve True si fue una ventana propia que bloquea hasta cerrarse (pywebview)."""
    try:
        import webview  # type: ignore[import-not-found]
    except ImportError:
        webbrowser.open(url)
        return False
    webview.create_window("Radar", url, width=1360, height=900, min_size=(900, 600))
    webview.start()
    return True


def smoke(port: int) -> int:
    """Arranca la API en un puerto libre, comprueba salud, interfaz y MCP, y sale. Lo usa la CI del instalador."""
    import json

    from radar.mcp.server import mcp

    free = _free_port()
    server = uvicorn.Server(uvicorn.Config("radar.api:app", host=HOST, port=free, log_level="warning"))
    threading.Thread(target=server.run, daemon=True, name="radar-smoke").start()
    try:
        if not wait_until_ready(free, 40):
            print("FAIL: la API no respondió")
            return 1
        with urlopen(f"http://{HOST}:{free}/radar", timeout=5) as page:
            html_ok = page.status == 200 and b"<html" in page.read(2000).lower()
        tools_ok = len(mcp._tool_manager.list_tools()) > 10
        print(json.dumps({"api": True, "frontend": html_ok, "mcp_tools": tools_ok, "port": free}))
        return 0 if html_ok and tools_ok else 1
    finally:
        server.should_exit = True


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return sock.getsockname()[1]


def main() -> None:
    restrict_umask()
    port = int(os.getenv("RADAR_API_PORT", str(DEFAULT_PORT)))
    if "--smoke" in sys.argv:
        raise SystemExit(smoke(port))
    url = f"http://{HOST}:{port}/radar"
    server: uvicorn.Server | None = None
    if port_in_use(port):
        if not is_radar(port):
            raise SystemExit(f"El puerto {port} está ocupado por otro programa. Define RADAR_API_PORT con un puerto libre.")
    else:
        server = uvicorn.Server(uvicorn.Config("radar.api:app", host=HOST, port=port, log_level="warning"))
        threading.Thread(target=server.run, daemon=True, name="radar-api").start()
        if not wait_until_ready(port):
            raise SystemExit("Radar no pudo iniciar la API. Revisa el registro en la carpeta de estado.")
    try:
        blocked = open_window(url)
        if not blocked and server is not None:
            print(f"Radar corre en {url}. Pulsa Ctrl+C para cerrar.")
            while True:
                time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        if server is not None:
            server.should_exit = True


if __name__ == "__main__":
    main()
