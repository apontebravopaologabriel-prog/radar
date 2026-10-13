# Architecture

## Purpose

Radar turns real job offers into market signals, required competencies, personal gaps and development
actions:

```text
market -> demand -> competency -> evidence -> project -> progress
```

Radar answers "what does the market ask, and what should I learn, practice or prove". It is not a global
dashboard and does not replace the user's notes, knowledge base, project tracker or chat memory.

## Components

```text
Optional external agent (Claude Code, Antigravity, Hermes, ...)
  | MCP stdio
Radar MCP server (FastMCP) ---------+
                                    |   shared registry: src/radar/tools.py
Browser (/radar, /m)                |
  | HTTP                            |
Radar API (FastAPI, :8100) -- chat agent loop (optional) -+
  |  security guard (Host/Origin, headers) · in-process scheduler (capture.py)
  |
Python core: pipeline (sources -> normalize -> classify -> dedupe -> enrich -> score)
  |
SQLite (source of truth)  +  local files next to it (cv_master.json, targets/, photo.jpg, secrets.json)
```

- The web UI talks only to the HTTP API, never to MCP or SQLite directly.
- The MCP server and the in-app chat use the same tool registry, so they cannot diverge.
- Connectors are not the source of truth: SQLite is. Python coordinates sources, normalizes, classifies,
  computes fingerprints and persists.

## Pipeline

0. Triggered by `radar refresh` (`capture.py`: the active pack's queries, each step isolated with a timeout), by the in-app
   "update now" (`refresh.py`), by `radar ingest`, or by CSV/JSON import.
1. A source adapter (`sources/jobspy.py` for Indeed and LinkedIn, `sources/computrabajo.py` over MCP stdio,
   or `importers.py` for CSV/JSON) returns raw offers.
2. `normalize.py` cleans text and builds the fingerprint (company + title + location, normalized).
3. `classify.py` assigns up to three areas, seniority and skills using the active career pack;
   `taxonomy.py` assigns relevance (`core`, `adjacent`, `out_of_focus`).
4. `enrichment.py` and `salary.py` extract sector, work mode, hours, schedule and salary, keeping the
   evidence and leaving `NULL` when nothing reliable is found.
5. `freshness.py` filters by `published_at`; offers without a date, in the future or too old are kept as
   history but never recommended.
6. `scoring.py` computes the deterministic personal score from the pack weights. Saving the profile
   recalculates all scores.
7. Every appearance is stored in `job_observations`; offers no source has seen for 45 days are deactivated
   (`expire_stale`), never deleted.

## Frontend

- `/radar`: Next.js static export. `RadarClient.tsx` holds filters, offer list, selection and views;
  `MapView.tsx` renders MapLibre (districts choropleth, clusters, radar radii); `LeafletMapView.tsx` is the
  automatic fallback when WebGL2 is missing. Detection happens before MapLibre is created.
- `/m`: separate mobile PWA (`components/mobile/`).
- `/ajustes`: settings page (career, profile, agent, access, data).
- Theme: graphite dark (`#212121` work area, `#171717` navigation, `#2f2f2f` controls and cards).
- Performance: list endpoints use an index on `job_sources(job_id, last_seen_at)`, selective gzip (not for
  `/api/chat`), `slim` listings without descriptions (fetched on open via `/api/jobs/{id}/description`),
  a sliding-window offer list, and MapLibre loaded on demand.

### Performance budget

| Metric | Target |
| --- | --- |
| API listings and feed | < 150 ms with 5 000 offers |
| `/radar` initial transfer | < 1 MB compressed |
| `/radar` DOM nodes | < 8 000 |
| Window drag/resize | ≤ 1 relayout per gesture, no long tasks |
| `/m` first useful paint | < 1 s on 4G |

Measure with `node scripts/perf/measure.mjs <load|idle|drag|pinresize|scroll|detail>` (Chromium over CDP;
needs the API on `127.0.0.1:8101`).

## Chat agent (summary; full reference in [agent.md](agent.md))

- Runs in the server, never in the browser. OpenAI-compatible provider; keeps DeepSeek `reasoning_content`
  across tool calls. Off by default; when off, `/api/chat*` returns 403 `agent_disabled`.
- Each turn has at most 8 steps; the last one removes tools to force a closing answer. Tool results are
  trimmed per item; older turns keep only an excerpt.
- Write tools are never executed inside the loop. They come back as `pending` and the user approves them at
  `/api/chat/confirm`. In plan and read-only modes the server does not offer them at all.
- The system prompt is: operational rules (`SYSTEM_PROMPT` in `agent/loop.py`) + persona (`agent/soul.md`) +
  user name and CV headline + memory notes + optional stale-classification notice + plan-mode block.
- The UI sends an explicit screen context each turn (view, map mode, district, radius, filters, open offer,
  counts) as navigation data, never as instructions. The user chooses how much is sent (off, selection, full).

## Design decisions

- The score is rule-based and traceable; the LLM never decides it.
- `description_raw` and `raw_payload` are always kept.
- Duplicates are detected by fingerprint and never deleted automatically; same company and title with a
  different location are reported for review.
- Offers are never deleted. Personal state lives in separate tables (`job_user_status`, `job_user_favorites`).
- Coordinates are inferred from district or city and the precision level is returned; they are not stored.
- LinkedIn runs only through public JobSpy search (no login); Computrabajo cookies are not used.
- The API limits CORS to localhost origins (`RADAR_API_ALLOW_ORIGINS`).
- `Districts` uses Lima/Callao boundaries, color by filtered count, selection synced with ranking and list.
- Analysis sends SQL to `/api/analytics/query`, which accepts only read-only queries; `/api/analytics/schema`
  describes the tables.
- CVs reads `/api/cv/*`. Targets are the favorites; data files live next to the database, outside Git and
  outside SQLite.

## Boundaries with other systems

Radar owns offers, companies, sources, demand, the job profile, skills, career events and offer history.
Other personal systems (a knowledge base, a project tracker, an episodic memory) keep their own stores;
Radar must not duplicate them and may read them in the future only through read-only projections.

Concepts that must stay distinct:

- **Market skill:** a term detected in an offer (SQL, Excel).
- **Human competency:** what the person must understand, decide, execute and verify.
- **AI assistance:** tasks an agent can speed up under supervision.
- **Evidence:** project, file, result or feedback that demonstrates the competency.

Progress is never inferred from skill frequency, finished courses or AI output; only practice and verifiable
evidence raise a level.

## Professional memory

Three related timelines:

- `job_observations`: each capture of an offer per source.
- `profile_versions`: each explicit profile update with skills, goals and preferences at that time.
- `career_events` and `application_events`: employment, training, projects, interviews, achievements,
  status changes.

Old offers become inactive or expired, never removed, so months and years can be compared. Vector search is
deferred until volume and semantic queries justify it.
