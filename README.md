# Radar

Version 0.9 in development (road to a Windows 1.0, see the roadmap). Local-first career intelligence for the Peruvian job market (Lima first, then the rest of the country).
Radar collects job offers, normalizes and classifies them, scores them against your profile with traceable
rules, and shows them on a map. An optional chat agent and an optional MCP server query the same data.

<img width="1571" height="1390" alt="Capture" src="https://github.com/user-attachments/assets/e76df213-dea0-447b-87e9-3cd2c92851d1" />

```text
search -> normalize -> classify -> deduplicate -> observe -> store -> score -> evolve
```

- **Source of truth:** a local SQLite file. No server, no cloud.
- **Backend:** FastAPI (`radar-api`, port 8100). **Frontend:** Next.js static export served by FastAPI.
- **Careers are data:** taxonomy, skills and score weights live in `src/radar/careers/packs/*.json`
  (see [docs/careers.md](docs/careers.md)). Packs today: Industrial Engineering and Systems/Software.
- **Hard limits:** no automatic applications, no messages sent, no personal portal sessions, the LLM never
  decides a score, a competency level or whether an offer is still open.

## Features

| Area | What it does |
| --- | --- |
| Desktop `/radar` | Map views `Districts` and `Radar` (2/5/10 km), filters, offer tray, favorites (★), hidden offers, `Analysis` (read-only SQL with charts) and `CVs` (gap analysis) |
| Mobile PWA `/m` | `Today` feed, `Map`, `Pipeline` (saved → applied → interview → offer), `Agent`, `Settings`, offline last feed |
| Chat agent (optional, off by default) | Floating window (`Ctrl+J`) or pinned panel; uses your own LLM API key; every write needs your approval. See [docs/agent.md](docs/agent.md) |
| MCP server (optional) | Exposes the same tool registry to external agents. See [docs/mcp.md](docs/mcp.md) |
| Target CVs and CV Studio | Hypothetical ideal candidate per ★ offer, gap matrix, closure plan; **Studio**: your real CV as pages with the agent beside it, suggestions you accept, PDF/Word export into one folder per application. See [docs/cv.md](docs/cv.md) |
| Refresh | Weekly systemd timer pulls Indeed, LinkedIn (JobSpy) and Computrabajo (MCP adapter). See [docs/operations.md](docs/operations.md) |

## Quick start

```bash
cp .env.example .env
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest
(cd frontend && npm ci && npm run build)   # creates frontend/out (gitignored)
.venv/bin/radar-api                        # http://127.0.0.1:8100/radar  and  /m
```

The database is created on first use at `~/.local/share/radar/radar.db` (override with `RADAR_DB_PATH`).
Windows users download the installer instead ([docs/guia-usuario.md](docs/guia-usuario.md), build in [docs/packaging.md](docs/packaging.md)).
Desktop window without the installer: `radar-app`. Dev mode: run `radar-api`, then `cd frontend && npm run dev` and open `http://localhost:3000/radar`.
Desktop launcher: `scripts/radar-launch.sh` (see operations).

First data:

```bash
radar profile --name "Ana" --area "Procesos" --location Lima --skill Excel=advanced --skill SQL=intermediate
radar ingest --source computrabajo --query "practicante de procesos" --location Lima --limit 10
```

Radar also asks for career, city and skills on first launch (desktop and mobile), so the CLI is optional.

## Documentation

Read in this order when changing behavior:

| Doc | Content |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Rules and code map for coding agents (start here) |
| [docs/architecture.md](docs/architecture.md) | Components, data flow, design decisions, boundaries |
| [docs/database.md](docs/database.md) | SQLite schema, persistence, deduplication, classification |
| [docs/careers.md](docs/careers.md) | Career pack format and how to add a career |
| [docs/operations.md](docs/operations.md) | Install, ingestion, refresh and scheduler, backups, remote access |
| [docs/packaging.md](docs/packaging.md) | Windows installer and release process |
| [docs/guia-usuario.md](docs/guia-usuario.md) | End-user guide (Spanish) |
| [docs/agent.md](docs/agent.md) | Chat agent: modes, tools, memory, UI |
| [docs/mcp.md](docs/mcp.md) | External MCP clients |
| [docs/cv.md](docs/cv.md) | Target CVs, gap analysis, downloadable CV |
| [docs/security.md](docs/security.md) | Threat model, controls, compliance |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Symptom → fix |
| [docs/roadmap.md](docs/roadmap.md) | Versions v0.8 → v1.5 (single source of status) |
| [docs/design-auto-compaction.md](docs/design-auto-compaction.md) | Design of the v0.9 focus feature: automatic context summarization |
| [docs/design-cv-studio.md](docs/design-cv-studio.md) | Design of the v1.0 hero feature: CV editor with agent panel, export and application folders |

`docs/skills/radar/SKILL.md` is generated (`radar skill export --out docs/skills`); never edit it by hand.
