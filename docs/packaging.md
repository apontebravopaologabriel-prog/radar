# Packaging and releases (Windows)

Goal of v1.0: a person with no Python, Node or LibreOffice downloads `Radar-Setup-<version>.exe`, installs it, sees
the app in minutes and can connect an AI client to the bundled MCP server.

## What is built

`packaging/radar.spec` (PyInstaller, one folder) produces `dist/Radar/` with three programs sharing one set of libraries:

| Program | Entry | Purpose |
| --- | --- | --- |
| `Radar(.exe)` | `radar.app:main` (no console) | Desktop app: API + scheduler + window (`pywebview`/WebView2, or the default browser) |
| `radar-mcp(.exe)` | `radar.mcp.server:main` | MCP server over stdio for AI clients |
| `radar-cli(.exe)` | `radar.cli:main` | `radar` commands (ingest, refresh, backup, career, mcp) |

The frontend export is bundled as `frontend_out` (found through `radar.paths.frontend_dir()`), package data (`help.md`,
`soul.md`, career packs, SQL schema) through `collect_data_files("radar")`. `packaging/radar.iss` (Inno Setup) wraps the folder
in an installer: per-user install (no admin), Start Menu entry, optional desktop icon and "start with Windows",
license page, and an uninstaller that **keeps** the user's data (`%LOCALAPPDATA%\radar`).

User data locations come from `radar.paths` (`platformdirs`): database, CV files, secrets fallback in
`%LOCALAPPDATA%\radar`, logs in the state folder. Provider keys go to Windows Credential Manager.

## Build locally

```bash
cd frontend && npm ci && npm run build && cd ..   # build copies the MapLibre worker to out/maplibre (needed by the map)
pip install -e '.[desktop,jobspy]'
pyinstaller packaging/radar.spec --noconfirm        # -> dist/Radar/
RADAR_DB_PATH=/tmp/radar-smoke/radar.db dist/Radar/Radar --smoke
iscc /DAppVersion=1.0.0 packaging\radar.iss          # Windows only -> dist-installer\
```

`--smoke` starts the packaged API on a free port and checks health, the frontend and that the MCP registry loads; it
exits 0 on success. The Linux build of the same spec was verified (about 178 MB, mostly NumPy/pandas pulled by JobSpy).

## Release workflow

`.github/workflows/release.yml` runs on tags `v*` (or manually) on `windows-latest`: builds the frontend, installs
dependencies, runs the tests, builds the executables, runs `Radar.exe --smoke`, builds the installer, signs it when
`WINDOWS_CERT_PFX_BASE64` and `WINDOWS_CERT_PASSWORD` repository secrets exist, writes `SHA256SUMS.txt` and attaches
everything to the GitHub release. Bump `radar.__version__`, `pyproject.toml` and `frontend/package.json` together, then
tag.

## Not verified yet (needs a Windows machine)

- The Windows build itself (the workflow is the first real run), WebView2 behavior, the credential store, the
  installer wizard, SmartScreen reputation of an unsigned build.
- Native PDF fonts on Windows (Calibri/Arial are searched in `C:\Windows\Fonts`).
- `npx` on Windows for the Computrabajo adapter: it requires Node.js; replacing it with a native Python adapter is the
  main pending piece of the plan (see [roadmap.md](roadmap.md#remaining-for-v10-ordered)).
