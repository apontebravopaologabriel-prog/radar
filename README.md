# Radar

Version 1.0.2 ([changelog](CHANGELOG.md), [known issues](KNOWN-ISSUES.md)). Local-first career intelligence for the Peruvian job market (Lima first, then the rest of the country).
Radar collects job offers, normalizes and classifies them, scores them against your profile with traceable
rules, and shows them on a map. An optional chat agent and an optional MCP server query the same data.


```text
search -> normalize -> classify -> deduplicate -> observe -> store -> score -> evolve
```

- **Source of truth:** a local SQLite file. No server, no cloud.
- **Backend:** FastAPI (`radar-api`, port 8100). **Frontend:** Next.js static export served by FastAPI.
- **Careers are data:** taxonomy, skills and score weights live in `src/radar/careers/packs/*.json`
  (see [docs/careers.md](docs/careers.md)). Main packs: Industrial Engineering and Systems/Software; Mechanical Engineering is experimental.
- **Hard limits:** no automatic applications, no messages sent, no personal portal sessions, the LLM never
  decides a score, a competency level or whether an offer is still open.

## Features

| Area | What it does |
| --- | --- |
| Desktop `/radar` | Map views `Districts` and `Radar` (2/5/10 km), filters, offer tray, favorites (★), hidden offers, `Analysis` (read-only SQL with charts) and `Mi CV` (import, profile and offer-specific preparation) |
| Processes | Optional follow-up after a recruiter response: contact, assessment, interview, offer or closed. Company and role suffice; next step and local date are optional. Previous applications remain in secondary history |
| Mobile PWA `/m` | `Today` feed, `Map`, `Pipeline` (saved → applied → interview → offer), `Agent`, `Settings`, offline last feed |
| Chat agent (optional, off by default) | Floating window (`Ctrl+J`) or pinned panel; uses your own LLM API key; every write needs your approval; offers in its answers link to the map detail. See [docs/agent.md](docs/agent.md) |
| MCP server (optional) | Exposes the same tool registry to external agents. See [docs/mcp.md](docs/mcp.md) |
| My CV | Drop a local PDF/DOCX, review and reuse your information. Prepare a CV from an offer, preview and download; detailed Studio editing is optional. My CV keeps prepared files and starred-offer comparisons. See [docs/cv.md](docs/cv.md) |
| Refresh & Import | Scheduled or in-app market pull across Computrabajo, Bumeran, Empleos Perú, and Indeed/LinkedIn (JobSpy). Single-URL instant import from the UI (`+ Agregar por link`) or agent (`/importar`). See [docs/operations.md](docs/operations.md) and [docs/data-sources.md](docs/data-sources.md) |

On desktop, **Filters → Market** switches Industrial/Systems without overwriting classifications.
The market is saved automatically; both markets open with all areas, core and related roles from the
last seven days. Extra criteria are collapsed under **Filter offers**. Systems classification requires
digital role evidence; using a tool alone does not establish an IT occupation.
**Settings → Search** contains capture controls for either market or both. See [career markets](docs/careers.md).

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
Desktop window without the installer: `radar-app`. FastAPI serves the built frontend at `http://127.0.0.1:8100/radar`.
For frontend development, run `radar-api`, then `cd frontend && npm run dev` and open `http://localhost:3000/radar`.
Desktop launcher: `scripts/radar-launch.sh` (see operations).

First data:

```bash
radar profile --name "Ana" --area "Procesos" --location Lima --skill Excel=advanced --skill SQL=intermediate
radar ingest --source computrabajo --query "practicante de procesos" --location Lima --limit 10
```

On first launch, choose a market and optionally import a local PDF/DOCX CV, review the extracted fields and confirm.
Setup can be resumed from Settings. Tools mentioned in a CV receive no invented proficiency level.
The desktop defaults to Lima/Callao, all market areas and seven days. See [docs/careers.md](docs/careers.md).

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
| [docs/cv.md](docs/cv.md) | My CV, local import, optional detailed editing and saved-offer comparisons |
| [docs/security.md](docs/security.md) | Threat model, controls, compliance |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Symptom → fix |
| [docs/data-sources.md](docs/data-sources.md) | Portal adapters, data privacy, and third-party notices |
| [SECURITY.md](SECURITY.md) | Security policy and vulnerability disclosure |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution guide, setup, and testing |
| [docs/roadmap.md](docs/roadmap.md) | Versions v0.8 → v1.5 (single source of status) |
| [docs/design-auto-compaction.md](docs/design-auto-compaction.md) | Design of the v0.9 focus feature: automatic context summarization |
| [docs/design-cv-studio.md](docs/design-cv-studio.md) | Design of the v1.0 hero feature: CV editor with agent panel, export and application folders |

`docs/skills/radar/SKILL.md` is generated (`radar skill export --out docs/skills`); never edit it by hand.

## Disclaimer & Legal Notice

Radar is a local-first personal career intelligence tool built for individual educational and analytical purposes.

- **No affiliation:** Radar is an independent open-source project and is not affiliated, associated, authorized, endorsed by, or in any way officially connected with LinkedIn, Indeed, Computrabajo, Bumeran, or any of their subsidiaries or affiliates.
- **Fair use and platform terms:** Users are solely responsible for ensuring their use of public connectors complies with the terms of service, robots.txt directives, and rate limits of third-party platforms.
- **Safety by design:** Radar does not automate job applications, does not bypass authentication barriers, does not store login credentials for job boards, and does not perform high-frequency scraping. All data gathered remains strictly on the user's local machine in an SQLite database.
- **No warranty:** The software is provided "as is", without warranty of any kind, as expressed in the [MIT License](LICENSE).
