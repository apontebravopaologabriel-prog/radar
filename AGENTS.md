# Radar: guide for coding agents

## Context

Radar is a local Career Intelligence app for exploring job offers in Peru (Lima is the main market, plus other
cities). SQLite (a local file, no server) is the source of truth; FastAPI exposes the API; Next.js builds the
static frontend that FastAPI serves at `/radar`. UI strings, help text and the agent persona are in Spanish;
code, comments for new code and docs are in English.

Read before changing behavior, in this order:

1. `README.md` (install and use)
2. `docs/architecture.md` (boundaries and responsibilities)
3. `docs/operations.md` (launcher, ingestion, verification)
4. `docs/troubleshooting.md` (when the problem is at runtime)

## Code map

Backend (`src/radar/`):

- `api.py`: HTTP endpoints, static frontend mount. `api_cv.py` (`/api/cv/*`, read-only), `api_me.py` (profile, photo), `api_agent.py` (chat, mobile API, settings), `auth.py` (access token), `feed.py` (Today feed), `settings.py` (settings, `secrets.json`).
- `db/`: connection, repository, queries, read-only analytics. Schema: `db/schema_sqlite.sql`.
- `careers/`: career packs (`packs/*.json`) plus the loader. `classify.py` and `taxonomy.py` are engines that read the active pack; no career-specific rules in Python.
- `classify.py`, `normalize.py`, `scoring.py`, `enrichment.py`, `salary.py`, `freshness.py`, `liveness.py`: the deterministic pipeline.
- `sources/`: portal adapters (`jobspy.py`, `computrabajo.py`). `pipeline.py` and `importers.py` run them; `refresh.py` is the in-app market refresh.
- `geolocation.py`: Lima/Callao districts, cities, departments. Resolution order: city (whole word) → Lima district → department → Lima. A bare "Perú" does not locate. Add cities in `_CITIES`.
- `tools.py`: the single tool registry (MCP and chat). Each tool declares `write` and `chat`. `TOOL_GROUPS` defines on-demand groups (`cv`, `perfil`, `sistema`).
- `agent/`: OpenAI-compatible provider, agent loop, memory (`memory.py`), conversation search (`history.py`), persona (`soul.md`, ISE BoK framework). Reference: `docs/agent.md`.
- `mcp/server.py`: stdio MCP server over the registry. `mcp_config.py` + `api_mcp.py`: "Connect an AI client" (snippets and confirmed install for Claude Desktop, Cursor, Gemini CLI).
- `capture.py` (`radar refresh`): the scheduled market capture, cross-platform and driven by the active pack. `scheduler.py`: in-process scheduler used where there is no systemd timer. `refresh.py`: the in-app "update now" run (same ingestion, in-process).
- `app.py` (`radar-app`): desktop entry (API + window + scheduler, `--smoke`). `paths.py`: OS-specific data/state/frontend folders. `security.py`: Host/Origin guard, headers, file permissions. `settings.py`: settings and secrets (OS credential store on Windows).
- `insights.py`: read-only queries behind open questions (job card, fit, demand, breakdowns, salaries, SQL). `skill_export.py` generates `docs/skills/radar/SKILL.md`.
- `cv_targets.py`, `cv_baseline.py`, `cv_plan.py`, `cv_build.py` (deterministic selection), `cv_doc.py` (per-offer document, operations, suggestions), `cv_facts.py` (fact guard), `cv_render.py` (templates, PDF, hit map, page images), `cv_packages.py` (folder per application), `cv_docx.py`, `cv_pdf.py`, `cv_edit.py`, `cv_photo.py`, `profile_edit.py`: CV and profile logic. See `docs/cv.md`.
- `maintenance.py`, `system.py`: classification audit/reclassification, system status, systemd timer. Closed action lists, confirmation, backup first; they never delete offers.
- `help.md` + `help.py`: curated product help; the agent explains the product only from it (`get_help`). Update it when a visible feature changes.

Frontend (`frontend/`):

- `components/RadarClient.tsx`: state, filters, offers, popups, map tools. `MapView.tsx` (MapLibre), `LeafletMapView.tsx` (fallback without WebGL2), `AnalysisView.tsx`, `CvView.tsx` (+ `lib/cv-types.ts`, `lib/cv-api.ts`, `components/cv.css`).
- `components/agent/`: shared chat (`useAgentChat`, `AgentChatPanel`) and the desktop window (`AgentDock`, mounted in `app/radar/page.tsx`). Two modes: floating window and panel pinned right (`--agent-dock-w`, container `.radar-stage`). It exists only when the agent is enabled; do not reintroduce a permanent button when it is off (only the link to `/ajustes` remains). `commands.ts` holds the `/` commands (`local` ones use the API and spend no tokens; add one = one entry in `COMMANDS`). `Markdown.tsx` is the safe renderer (no raw HTML, only http/https/mailto links). `RadarMark.tsx` is the agent symbol.
- `components/CvStudio.tsx` (+ `cv-studio.css`, `lib/cv-studio-api.ts`): the Studio tab; it asks the agent dock to pin itself (`radar:agent-layout` event) and publishes `cvStudio` in the agent context.
- `components/mobile/` and `app/m/`: the PWA at `/m`. `public/` holds manifest and service worker.
- `app/globals.css` (layout, graphite theme, popups, scrolls), `lib/api.ts` (HTTP client).
- `frontend/out/`: static export served by FastAPI. Built by `npm run build`, **not versioned** (gitignored); the launcher builds it if missing. Never edit it by hand.

`packaging/` (PyInstaller spec, Inno Setup script) and `.github/workflows/release.yml` build the Windows installer; see `docs/packaging.md`. `legacy/postgres/` is a historical artifact (old PostgreSQL migrations, compose file, migration script). It is never executed; do not add files there.

## Desktop interface contracts

- The main screen is `/radar`, centered on Lima/Callao and the `Districts` view by default.
- The map fills the background. Controls are floating tools: Filters, Radar, Analysis and CVs. Do not reintroduce a top bar, a bottom bar or map zoom controls.
- Monochrome design: black, graphite, grays. No green accents without an explicit product decision.
- Auto-refresh queries Indeed and LinkedIn through JobSpy and Computrabajo through its MCP adapter; each portal runs isolated so one failure does not stop the refresh.
- Districts shows compact labels `District · count`; avoid overlapping circles.
- Radar requires a selected district and offers 2, 5 and 10 km radii. Its selector may open upward and the panel floats bottom-right.
- Analysis and CVs replace the map with a full-screen view (no side panel). CVs leaves the left margin free for the toolbar, marks every target CV `HIPOTÉTICO — no enviar` and offers no export. Targets are the ★ offers: do not create another selection mechanism.
- Offers appear in a floating tray, resizable from the top handle, with internal scroll. Cards keep a compact height even with few offers. The tray also exposes compact icons to toggle favorites and hidden offers.
- Per signal, the source (`Indeed`, `LinkedIn`, …) appears next to the area on hover or focus; the title is the direct link to the original offer and must not open the detail by accident.
- The company may show a discreet `⌖` icon that opens an external Google Maps search (company + location). Do not turn it into an API integration or auto-draw sites on the map.
- The filter panel has portal and competency selectors; both reuse the API filters and stay in sync with the map.
- In the detail, hide is only an eye icon next to the close `X`. The reason appears in a separate popup to the left of the detail; do not turn it back into an inline form.
- Descriptions render with the local Markdown renderer. Never use `dangerouslySetInnerHTML` with external content.

## Mobile contracts (`/m`)

- A separate interface from the map: the desktop floating-bar rules do not apply.
- Gray and black terminal look: monospaced, dark only, no color accents (deliberate exception: the agent chat uses the accent palette of `mobile.css`, Claude Code style), `>` on titles and `[SECTION]` labels, 44 px touch targets.
- The mobile map uses Leaflet with OpenStreetMap tiles (CARTO now requires a key) and one point per place; no polygons or per-offer layers.
- The service worker never caches `/api/chat`, `/api/agent` or `/api/auth`.

## Tools and agent contracts

- Every new tool is registered in `tools.py`; if it writes, `write=True` (it appears as a confirmation card). Add it to the table in `docs/agent.md`, regenerate the skill (`radar skill export --out docs/skills`) and cover it in `tests/test_tools.py`.
- Each chat tool costs tokens on every message: set `chat=False` for MCP-only tools, keep descriptions short, and put heavy rarely-used tools in a `TOOL_GROUPS` group.
- Do not expose to the chat any tool that sends messages, applies to jobs or runs free-form SQL against writable data.

## Change workflow

1. Check `git status`; keep existing changes that are not part of the task.
2. Edit source; never edit `frontend/out`.
3. For visual changes run `cd frontend && npm run build`.
4. Run `git diff --check`, `pytest`, `ruff check` (and `npm test`, `npm run lint` for the frontend).
5. Review the diff.
6. Document behavior changes in the matching doc (`README.md` or `docs/`), and in `help.md` if user-visible.

## Verification commands

```bash
cd /home/paolo/Projects/Radar
.venv/bin/pytest
.venv/bin/ruff check
git diff --check

cd frontend
npm run lint && npm test && npm run build
```

The build must exit 0 without new warnings. If Autoprefixer flags alignment values, prefer `flex-start`/`flex-end`.
CI (`.github/workflows/ci.yml`) runs Python 3.11, 3.12 and 3.14 on Linux, 3.12 on Windows, the frontend job and an informational dependency audit. Do not use POSIX-only APIs without an `os.name` guard: the code must run on Windows.

## Limits and safety

- Do not automate applications, messages or personal portal sessions.
- Never delete historical offers or modify `jobs` to hide personal state; use the status/favorites tables and endpoints.
- Keep coordinate inference approximate and never present it as an exact location.
- Target CVs are hypothetical: never present or export them as a real CV. The real profile, target CVs and photo live outside the repo (`~/.local/share/radar/`); never version them.
- Never use an LLM to silently decide scores, competency levels or offer validity.
- Schema changes go in `src/radar/db/schema_sqlite.sql` (and in `_ensure_runtime_schema()` if they must apply to existing databases); never delete the `.db` file and never add a `.sql` under `legacy/postgres/migrations/`. See `docs/database.md`.
