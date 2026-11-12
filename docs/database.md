# Data model

The active database is SQLite. The full schema, including the area and skill catalog, lives in
[`src/radar/db/schema_sqlite.sql`](../src/radar/db/schema_sqlite.sql) and is applied whole when a new `.db`
is created. `_ensure_runtime_schema()` in [`src/radar/db/database.py`](../src/radar/db/database.py)
re-applies indexes and catalog additively (`ON CONFLICT DO NOTHING`) once per process, so older databases
catch up automatically.

Rules for schema changes: edit `schema_sqlite.sql` (and `_ensure_runtime_schema()` if existing databases need
it). Never delete the `.db` and never add files to `legacy/postgres/migrations/` (historical PostgreSQL,
never executed).

## Tables

| Table | Purpose |
| --- | --- |
| `sources` | Sources and connector type |
| `companies` | Normalized companies (`normalized_name`) |
| `jobs` | Canonical offer independent of source: work mode, sector, salary, schedule, relevance, application status |
| `job_sources` | One row per source appearance: URL, external id, `raw_payload` |
| `industrial_areas` | Area catalog (the name predates multi-career; it holds areas for every pack) |
| `job_areas` | Primary/secondary area per offer, evidence, confidence (max 3, one primary) |
| `skills`, `job_skills` | Normalized skill catalog and per-offer skills with importance, type and evidence |
| `job_requirements` | Education, experience, languages and other requirements |
| `ingestion_runs` | Audit of ingestion runs |
| `user_profile`, `user_skills` | Profile and skill levels, separate from the market |
| `profile_versions` | Immutable profile snapshots (one per explicit update) |
| `job_scores` | Match engine output |
| `job_observations` | Time series: each capture of an offer per source |
| `market_snapshots` | Dated market totals, areas and skills |
| `applications`, `application_events` | Personal pipeline and every status transition |
| `career_events` | Employment, studies, projects, courses, achievements, goals |
| `job_user_status` | Visible/hidden state, optional reason (`closed`, `not_interested`, `applied`, `duplicate`, `other`), note |
| `job_user_favorites` | Starred offers with save date (independent from hidden state) |
| `app_settings` | Settings such as the chosen career and `classification_rules_hash` |
| `agent_usage` | Token usage per month |
| `conversations` | Saved chat conversations |
| `agent_pending_proposals` | Server-verified pending write-tool proposals awaiting user confirmation |
| `agent_memories` (+ FTS tables) | Durable agent memory with text search |

There is no `user_id`: one installation is one user. `application_status` (does the source still accept
applications) is different from `applications` (the user's own pipeline).

Not in SQLite (files next to the database, outside Git): `cv_master.json` (real profile), `targets/*.json`
(hypothetical target CVs), `photo.jpg`, `cvs/` (generated CVs), `careers/` (custom packs), `secrets.json`,
`backups/`, `reclassify-*.json`. See [cv.md](cv.md).

## Persistence flow

1. An offer is fetched.
2. The company is created or reused by `normalized_name`.
3. `canonical_fingerprint` is computed from normalized company, title and location.
4. If the fingerprint exists, the canonical offer is updated.
5. URL, external id and raw response go to `job_sources`.
6. New offers are classified and linked to areas and skills; re-ingesting rewrites areas and relevance.
7. Each appearance goes to `job_observations`; the offer is marked active or inactive, never deleted.
8. `capture_market_history` stores dated totals, areas and skills.

`sector`, `sector_confidence`, `hours_per_week` and `schedule_text` are enriched at ingestion. `radar
repair-data` recomputes them (plus work mode and salary) for older rows.

## Duplicates and quality

- Exact duplicates are caught by a unique fingerprint; one offer can hold several URLs in `job_sources`.
- Same company and title with different location are reported, not merged.
- `duplicate_status` lets one canonical offer stand while candidates or merged records are separated.
- Normal queries return only canonical, active, non-hidden offers.
- `radar audit-data` produces a reproducible report: repeated groups, per-source links, area integrity,
  commercial titles inside target areas.
- `NULL` means unavailable data; a missing salary is not zero. Offers with no salary are still stored.

## Classification

Deterministic, with textual evidence. Each area accumulates a score:

| Signal | Points |
| --- | --- |
| Match in the title | 3 (short derivatives allowed: "almacenero" matches "almacen", except acronyms under 6 letters, which must be exact) |
| Strong mention in the description | 0.8 each, max 3 |
| Generic `weak_terms` of the pack (`sql`, `erp`, `proyectos`, ...) | 0.25 each |

Below the minimum score (1.5) the offer is `Otras`, unless explicit contextual duty/title evidence meets
the threshold through the pack's evidence gate. Titles in `excluded_title_signals` without an area
signal in the title are also `Otras`. `Ventas / Comercial` is explicit: commercial signals in the title beat
generic description words (`operaciones`, `planning`, `procesos`), and a stray mention in the description is
not enough (at least three are needed). `job_areas` keeps up to three areas, primary marked.

Relevance tier (`relevance_tier`, `relevance_score`, `relevance_evidence`): `core`, `adjacent` or
`out_of_focus`, from the pack's area lists. It prioritizes the view and audits classification; salary is
never an entry criterion.

Maintenance: `audit_classification` compares stored areas with what today's rules would assign;
`reclassify_jobs` first creates a consistent SQLite backup under `backups/`, then rebuilds canonical
areas/skills/relevance and installed market projections in bounded, content-guarded batches. The
rules fingerprint is stored in `app_settings.classification_rules_hash`; when rules change, the agent prompt
warns that an audit is due.

## Market and user

`ingestion_runs.query` retains search text; `context` stores requested source, location, limits and
market IDs. Download failures and timeouts create terminal run records without job writes. A batch
savepoint rolls back job/source changes on failure while preserving run diagnostics. Legacy context is
`{}`. Stable source identity precedes title/location fingerprints; historical conflicts require explicit
audit rather than automatic destructive merging.

- Market metrics come from `jobs`, `job_areas` and `job_skills`. User data never alters market statistics.
- Every explicit profile update creates a `profile_versions` row.
- Hiding an offer excludes it from normal queries; the reason is optional and restoring sets it back to `visible`.
  Neither touches `jobs`. Hiding always wins over the star: hidden offers are not listed as favorites either.
  Databases created before the reason became optional rebuild `job_user_status` on open (SQLite cannot drop a CHECK).
- `GET /api/skills/overview` computes demand from offers filtered by age, area, seniority and work mode,
  grouping `job_skills`, and crosses it with `user_skills`. It never invents a level the user did not declare.

### Evidence scoring revisions

`job_scores.assessment` is an additive JSON column (default `{}`), also applied by runtime schema migration.
It stores the scoring version, six requirement assessments, skill levels, quotes, declared skill gaps,
supported lower/upper bounds, coverage, effective weights, market and profile/content hashes. Old rows
remain readable but are stale. Factual profile edits refresh active canonical scores; no offer, application,
favorite or CV fact is rewritten by score recomputation. Back up existing databases before bulk recalculation.

## Processes (schema version 4)

The additive `processes` table owns company/title, optional job_id and source_application_id, optional URL, stage, next_step, due_date (local ISO date), notes and timestamps. Job/source uniqueness makes migration idempotent. Interview/offer applications are copied only during the version-4 upgrade; application rows/events remain intact. Closing retains inbox exclusions. Existing databases receive a pre-schema-upgrade backup. No fake jobs or automatic stars are created.
