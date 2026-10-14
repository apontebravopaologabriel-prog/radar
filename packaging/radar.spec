# PyInstaller: genera la carpeta `dist/Radar/` con tres programas que comparten librerías:
#   Radar(.exe)      ventana de escritorio (sin consola)          -> radar.app:main
#   radar-mcp(.exe)  servidor MCP por stdio para clientes de IA   -> radar.mcp.server:main
#   radar-cli(.exe)  línea de comandos (ingesta, copias, carreras) -> radar.cli:main
# Requisitos previos: `cd frontend && npm ci && npm run build` (crea frontend/out) y `pip install -e '.[desktop,jobspy]'`.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
FRONTEND = ROOT / "frontend" / "out"
if not FRONTEND.is_dir():
    raise SystemExit("Falta frontend/out: ejecuta `npm run build` en frontend/ antes de empaquetar.")

datas = collect_data_files("radar") + [(str(FRONTEND), "frontend_out")]
hidden = (
    collect_submodules("uvicorn")
    + collect_submodules("mcp", filter=lambda name: not name.startswith("mcp.cli"))
    + collect_submodules("keyring.backends")
    + ["webview", "jobspy", "fpdf", "pypdfium2", "pypdfium2_raw", "radar.api", "radar.mcp.server"]
)
excludes = ["tkinter", "matplotlib", "pytest", "ruff"]


def program(entry, name, console):
    script = ROOT / "packaging" / f"entry_{entry}.py"
    analysis = Analysis([str(script)], pathex=[str(ROOT / "src")], datas=datas, hiddenimports=hidden, excludes=excludes)
    pyz = PYZ(analysis.pure)
    exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name=name, console=console,
              icon=str(ROOT / "packaging" / "radar.ico") if (ROOT / "packaging" / "radar.ico").exists() else None)
    return analysis, exe


desktop_a, desktop_e = program("desktop", "Radar", False)
mcp_a, mcp_e = program("mcp", "radar-mcp", True)
cli_a, cli_e = program("cli", "radar-cli", True)

COLLECT(
    desktop_e, desktop_a.binaries, desktop_a.datas,
    mcp_e, mcp_a.binaries, mcp_a.datas,
    cli_e, cli_a.binaries, cli_a.datas,
    name="Radar",
)
