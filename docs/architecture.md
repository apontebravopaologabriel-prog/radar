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
Browser (/radar)                    |
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

0. Triggered by `radar refresh` (`capture.py`: configured markets, reference-pack default, download timeouts), by the in-app
   "update now" (`refresh.py`), by `radar ingest`, or by CSV/JSON import.
1. A source adapter (`sources/jobspy.py` for Indeed and LinkedIn, `sources/computrabajo.py` using native public HTTP (optional legacy MCP), or `importers.py` for CSV/JSON) returns raw offers.
2. Stable portal URL/ID resolves existing identity first. `normalize.py` supplies a company/title/location
   fallback fingerprint; distinct source publications can receive a disambiguated identity anchor.
3. `classify.py` assigns up to three areas, seniority and skills using the active career pack;
   `taxonomy.py` assigns relevance (`core`, `adjacent`, `out_of_focus`).
4. `enrichment.py` and `salary.py` extract sector, work mode, hours, schedule and salary, keeping the
   evidence and leaving `NULL` when nothing reliable is found.
5. `freshness.py` filters connector search results by `published_at` before ingestion. Undated, future
   and out-of-range results are counted as discarded. Already stored history is never removed by this filter.
   Visible offer windows use Lima calendar days. Queries convert timestamps with a zone to Lima and keep
   the recorded day for values without a zone.
6. `scoring.py` computes the deterministic personal score from the pack weights. Saving the profile
   recalculates all scores. Version `v2.0-evidence` uses the full description, factual CV education/experience
   and declared skill levels. `requirements.py` also serves CV gaps. Unknown inputs produce an interval rather
   than fixed education/juniority bonuses; supported points are not a hiring probability. The additive JSON
   `job_scores.assessment` stores quotes, status, bounds, coverage, weights and input revisions. Computation runs
   outside write transactions; bounded writes guard offer content and profile revisions. Readers suppress stale
   scores when CV/profile or offer content changed. Scores still belong only to the reference career.
7. Every appearance is stored in `job_observations`; offers no source has seen for 45 days are deactivated
   (`expire_stale`), never deleted.

## Frontend

- `/radar`: Next.js static export. `RadarClient.tsx` holds filters, offer list, selection and views;
  `MapView.tsx` renders MapLibre (districts choropleth, clusters, radar radii); `LeafletMapView.tsx` is the
  automatic fallback when WebGL2 is missing. Detection happens before MapLibre is created.
- The mobile PWA (`/m`) was archived in `legacy/mobile/`; it is no longer built or served.
- `/ajustes`: settings page (career, profile, agent, access, data).
- Map controls use opaque graphite surfaces. The district selector replaces the permanent ranking.
  Filters show market, search, area and period first, with advanced criteria collapsed. Loading is shown
  inside the tray while data is requested. The agent uses a floating window when pinning would leave
  less than 640 px for the map; CV Studio retains its requested pinned layout.
- Theme: graphite dark (`#212121` work area, `#171717` navigation, `#2f2f2f` controls and cards).
- Performance: list endpoints use an index on `job_sources(job_id, last_seen_at)`, selective gzip (not for
  `/api/chat`), `slim` listings without descriptions (fetched on open via `/api/jobs/{id}/description`),
  an offer list window sized from its viewport with four extra rows per edge, and MapLibre loaded on demand.
  Fixed-height cards preserve the scroll range using top and bottom spacers; keyboard selection scrolls into view.
  District selection changes the highlight and list without rebuilding the market map sources.
  The generated offer contract distinguishes the `slim` row, which carries `has_description`, from the
  full row, which carries a nullable `description`. The by-ID lookup returns a slim row even outside the current filters.
- Offer tray views: active, favorites (`/api/jobs/favorites`) and archive
  (`/api/jobs/hidden`); `GET /api/jobs/{id}` returns one offer (used when the chat opens an offer that is not in the
  current lists). Tracking: `GET/PUT/DELETE /api/applications[/{job_id}]` (`DELETE` removes only your tracking record).
  `ProcessesView.tsx` puts actionable responses first, followed by `ApplicationsView.tsx` with eight recent submissions and searchable history. Both use one page scroll and share one application list. While visible, the page refreshes tracking roughly every second to pick up writes from external MCP clients. Responses, interviews and offers update the application and linked process in the same transaction. The pin records an interview. Returning a linked process to submissions sets its application status to applied and preserves the process data for future follow-up. The summary opens the earliest dated active commitment. Archived counts and lists the last seven Lima calendar days without deleting records. Search older archives through a paginated endpoint. The tracking snapshot uses daily counts from the full application history for its activity chart. Its application timestamps come from status events. Process closures keep their archive timestamp across edits, with a last-update fallback for legacy closures. Selecting a row shows the saved description and the same offer facts as the map, with the title linking to the original listing. The chat opens offers through the `radar:open-job` window event
  (`Markdown.tsx` -> `RadarClient.tsx`).
  The map's `✓ Postulé` action records an application and removes its offer from active map listings without leaving the map. The personal screen tracks Postulé, Respondieron, Entrevista, Oferta and Cerradas; a process with a linked offer updates the same application status. Favorites represent interest before applying; archive is a separate reversible exclusion and needs no reason, and it wins over the star (a hidden favorite stays out of the active listings, the ★ branch and the `Comparing ★` selection). Desktop, mobile and the local agent command use the shared `applications-api.ts` client and types
  generated from the tracking operations in FastAPI. Onboarding, Settings and the local `/refresh` command
  use `refresh-api.ts` for the in-app market refresh. Its generated status includes the current search,
  completed and created counts, timestamps and errors. With the Python environment active, run
  `npm run api:generate` from `frontend/` after changing the contract. `npm run api:check` verifies it in CI.
- MapLibre 6 loads its worker as a separate module: `frontend/scripts/copy-maplibre-worker.mjs` (the `prebuild` step)
  copies it to `public/maplibre/`, the API serves it at `/maplibre` and `MapView.tsx` calls `setWorkerUrl`. Without it the
  map stays blank ("Worker failed to load").

Analysis reuses the map filter popover in place. Both views show a reset control beside Filters when the selection differs from the defaults. It preserves the active market and clears the geographic and offer selection. Charts open a popover aligned with the map’s bottom-left offer tray with a scrollable group picker, an upward resize handle and listings loaded on scroll. Offer selection reuses the map’s read-only detail content without changing views. The dashboard ranks tools and technologies by offer count and shows their share of the scoped offers. The competency drill-down groups languages and knowledge separately and can show a donut using total tool mentions. Market catalog overrides affect this presentation only. The drill-down picker includes soft and uncategorized skills. Offers without a district appear as a separate clickable coverage count. Salary columns show all currency and period groups in a responsive grid. Daily publications use a line chart, and work modality uses a donut with an interactive legend. Analysis refreshes for changes to the shared filter values, independently of map refresh events. Generic employer labels are omitted from company metrics while their jobs remain in the offer totals. Skill and
work-mode selections can be applied to the shared scope explicitly. Compare uses a compact picker for up
to four favorites or submissions. Consultas retains read-only SQL over the full database.

### Performance budget

| Metric | Target |
| --- | --- |
| API listings and feed | < 150 ms with 5 000 offers |
| `/radar` initial transfer | < 1 MB compressed |
| `/radar` DOM nodes | < 8 000 |
| Window drag/resize | ≤ 1 relayout per gesture, no long tasks |

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
- Analysis opens a responsive scoped overview backed by `analysis.py` and typed `/api/analytics/overview`.
  It reuses `list_jobs` with active inbox exclusions and selected-market projections, then applies the map's
  district or unrounded Haversine radius. `/api/analytics/offers` provides paginated drill-down with the same scope.
  Charts use native lightweight bars; no physics or window management. Salary groups keep currency and period
  separate; dates use Lima calendar days with zero-filled publication series. Saved browser views store relative
  filters, not snapshots. The optional SQL editor uses `/api/analytics/query` (read-only, full database); its queries
  deliberately do not inherit the map scope. `/api/analytics/schema` describes the tables.
- The Analysis comparison tab selects up to four starred or submitted offers. `/api/cv/targets` supplies deterministic requirements and factual evidence; matrix cells expose the reason and quoted job text on click. The company research action only drafts a question for the optional agent, which can use existing local Radar tools; it does not fetch external company information.
- Mi CV is secondary, accessed through Settings (`/radar?view=cvs`) or Prepare CV in an offer. It opens on factual data unless an offer requested a document. It shares factual editing/import through `/api/me/cv*` and prepares offer-specific documents through
  `/api/cv/*`. Studio is optional detailed editing. Mi CV owns prepared files; comparison lives in Analysis. The factual CV and immutable imported sources (`cv_imports/`) live beside the
  database outside Git; document operations and package indexes live in SQLite. See [cv.md](cv.md).

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

## Local setup and geography (2026-11-04)

`cv_import.py` handles bounded local PDF/DOCX preview and confirmed profile merge; `/api/me/setup*` stores
resumable drafts and explicit completion. Preview does not write factual history. `updates.py` handles fixed
GitHub release checks independently of offer capture. `places_lima.json` supplies shared polygon keys,
aliases and approximate centroids to both API and frontend; the desktop sends `geo_scope=lima_callao`.
See [implementation and verification scope](windows-cv-markets-2026-11-04.md).

Radar map sources use the radius-filtered offers; Districts keeps the full market source. Switching map modes closes filters immediately. Compact cards show the source beside the company; translucent surfaces do not use backdrop blur.

Map tray titles use a single ellipsized line (full title in the detail and native tooltip). Location has no decorative prefix. The detail exposes one compact Prepare CV action, isolated from the My CV page button styles.

## Response-driven processes

`processes.py` exposes typed GET/POST `/api/processes` and PUT `/api/processes/{process_id}`. A process owns company and title; its job reference and URL are optional. The stages are contact, assessment, interview, offer and closed. Next step, local calendar date and notes are optional; there are no reminders or outbound messages. The same form, contact dialog and Processes view serve desktop and mobile. Closing retains the row and its inbox exclusion.

Schema version 4 adds `processes` independently of `applications`. Before an existing database is upgraded a backup is created. Existing interview/offer rows are copied once, retaining their source ID; unique job/source indexes prevent duplicates, and subsequent history edits never overwrite a process. Legacy APIs/tools keep their meaning. Main inbox queries and the Today feed exclude linked processes regardless of stage. Favorites and direct job reads retain access.

Prepared files and starred-offer comparisons live in Mi CV; the detail also exposes prepared files. Package loading errors do not block Processes. No CV export or portal link implicitly records submission or creates a process.

Salary filtering accepts optional min_salary/max_salary in job/map APIs and market skills. Published salary bands overlap the requested band; one-sided values work, and unknown salaries are excluded only when a bound is present. Amounts retain the existing source currency semantics (no conversion). Invalid/reversed ranges return 422 and show a local UI explanation. The query context carries both bounds to agent queries.

Map filter controls are bottom-right; their popup opens above the trigger. Districts/Radar tabs retain independent top-right space. The Radar panel reserves the same bottom trigger clearance. This avoids active-filter badge width colliding with the map-mode tabs.
