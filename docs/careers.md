# Career packs

A career pack is a JSON file with everything career-specific: areas, classification rules, skills and score
weights. The engines (`careers/__init__.py`, `classify.py`, `taxonomy.py`, `scoring.py`) are generic, so
adding a career means adding a JSON file, not Python.

## Where packs live

| Location | Use |
| --- | --- |
| `src/radar/careers/packs/*.json` | Built-in packs (versioned). Today: `industrial_engineering` (default) and `sistemas_software` |
| `<database folder>/careers/*.json` | Packs created by the user (onboarding form, `create_career_pack` tool, or by hand). Not versioned |

The active career is chosen in this order: the setting stored in the database (Settings or
`set_career_track`), then `RADAR_CAREER`, then `industrial_engineering`. Each person works with one career at
a time on their own local database.

## Format

```jsonc
{
  "id": "sistemas_software",                  // required; equals the file name
  "name": "Contabilidad y Finanzas",          // required
  "country": "PE", "language": "es",
  "areas": {                                  // required
    "core": ["Contabilidad", "Auditoría"],
    "adjacent": ["Data / BI"],
    "out_of_focus": ["Ventas / Comercial", "Otras"]
  },
  "area_slugs": { "Contabilidad": "contabilidad" },
  "area_rules": {                             // required; keys must exist in `areas`
    "Contabilidad": ["contabilidad", "contador", "niif"]   // accent-free, lowercase terms
  },
  "out_of_focus_rules": { "Ventas / Comercial": ["vendedor", "ejecutivo comercial"] },
  "skills": {                                 // required
    "Excel": { "aliases": ["excel"], "category": "herramienta", "type": "technical" }
    // type: technical | domain | methodology | language | soft
  },
  "excluded_title_signals": ["auxiliar de limpieza"],  // titles that are never this career
  "education_only": ["contador publico"],              // terms that describe a degree, not an area
  "context_terms": ["contabilidad", "tributacion"],    // whole phrases that mark context
  "weak_terms": ["proyectos", "sql"],                  // generic terms; score 0.25 instead of 0.8
  "target_titles": ["analista de control de gestion"], // target label only if primary area is already core
  "operational_titles": ["operario", "almacenero"],    // title contains it: out of focus (checked before target_titles)
  "adjacent_title_signals": ["ingenieria industrial"], // title contains it: at least adjacent
  "scoring": {                                // required; exactly these 6 keys, summing to 1
    "area": 0.30, "skills": 0.25, "seniority": 0.15,
    "education": 0.10, "location": 0.10, "preference": 0.10
  },
  "queries": ["practicante contable"],        // short searches: in-app refresh and extra cities
  "market_queries": ["desarrollador Python"]  // broad searches for the weekly capture of Lima (defaults to queries)
}
```

Validation (`parse_pack`): missing required keys, `scoring` keys other than the six, weights not summing to 1,
or rules for undeclared areas raise `CareerPackError`. A broken user pack is skipped, never breaks the app.
Custom packs created from the UI are limited to 20 areas, 60 skills and 12 keywords per area.

## How the engines use a pack

- **Areas:** `classify.py` scores each area (title match 3, strong description mention 0.8 up to 3, weak term
  0.25). Under 1.5 the offer is `Otras`. See [database.md](database.md#classification).
- **Relevance:** `taxonomy.py` maps the primary area to `core`, `adjacent` or `out_of_focus`.
- **Skills:** alias matching in title and description, with evidence kept per offer.
- **Score:** `scoring.py` combines the six weighted dimensions; the user can change weights
  (`set_score_weights`) and the breakdown is always shown.
- **Rules fingerprint:** changing a pack changes the classification-rules hash, so the agent prompts for an
  audit (`audit_classification`) and a reclassification (`reclassify_jobs`) of stored offers.

### Contextual classification (2026-11-01)

Packs may provide `area_evidence_rules`, keyed by an existing area. Each rule accepts `title_any`
(qualifying title phrases), `title_none` (local title conflicts), and `duty_groups`: each group has
nonempty `actions` and `objects` arrays. A qualifying title or an action followed by a domain object
within 160 characters in a duty clause is required before that area can be assigned. Action stems
are explicit pack data. A group's optional `gap_excludes` phrases reject an action/object association
when the intervening text indicates tool use or an unrelated standard. Contextual evidence can satisfy
the minimum area threshold; unrelated tools
in requirements cannot satisfy this gate. Old custom packs without gates retain keyword scoring.

`classification_text.py` separates recognised duties, requirements, employer and benefits sections.
Explicit employer/benefits blocks do not contribute areas or skills; requirements can supply skills
but cannot satisfy duty groups. Unheaded prose is handled conservatively, with common requirement
prefixes excluded from duty evidence. This is a deterministic parser with incomplete section coverage,
not complete natural-language understanding or an academic eligibility parser.

The Systems pack guards every area, including cloud, DevOps, functional ERP, BI and cybersecurity.
Industrial retains valid production supervision and rejects the reviewed clinical and trade-maintenance
role declarations. `excluded_role_signals` supplies explicit role exclusions; `legacy_area_aliases`
keeps historical labels within their own pack. Primary occupational area determines relevance;
secondary areas and target titles cannot promote an unrelated primary occupation.

Fingerprints include the classifier version and the complete pack. Both ingestion and backfill use
the same functions. `reclassify_jobs` creates a SQLite backup before writes, recomputes canonical
areas/skills/relevance in guarded batches and rebuilds independent projections for installed packs.
It preserves offers, source observations and personal state.

`relevance_tier=market` means core plus adjacent, excluding outside-market records. Desktop uses it
with all areas and `max_age_days=7` when opening or switching markets. Clearing relevance explicitly
includes outside-market records and is not the default. The larger capture lookback is unchanged.
Capture coordination, full academic evidence and measured held-out quality in the design plan remain
follow-up work; these corrections are covered by diagnostic regression cases, not an accuracy claim.

## Adding a career (checklist)

1. Copy the closest pack and change `id`, `name`, areas, rules, skills, `queries` and `market_queries`.
2. Write accent-free lowercase terms; prefer specific phrases over generic words; put generic words in
   `weak_terms`.
3. Validate it: `radar career validate <path-to-json or id>` (errors block use; warnings list areas without slug or
   rules, skills without aliases, missing queries). `radar career list` shows what is loaded.
4. Ingest a sample (`radar ingest --query ... --limit 25`), then review the area distribution with
   `get_market_breakdown(by="area")` and `audit_classification`. Offers piling into `Otras` mean missing
   terms; offers in a wrong area mean terms that are too generic.
5. Add real titles with their expected area to `SAMPLES` in `tests/test_careers.py` (the parametrized regression test
   and the completeness test then cover the new pack automatically).
6. Update `help.md` if the career list shown to users changes.

## Known limitations

- Current relevance is occupational keyword and contextual duty evidence, not proof that the employer accepts a specific degree.
- `industrial_engineering` covers business/process analytics and KPIs under `Información, analítica y sistemas` (mapping historical `"Ingeniería de sistemas"` via `legacy_area_aliases`) while excluding pure IT/software/cloud roles. Conversely, `sistemas_software` requires explicit IT/software role or duty evidence and excludes operational/financial end-user roles that merely use an ERP or spreadsheet.
- The area catalog table is still named `industrial_areas` (it stores areas for every pack); renaming it is cosmetic and
  deferred because it touches many queries.
- Keyword classification degrades on careers with ambiguous vocabulary; measure the share of `Otras` after every new
  pack. Short, generic terms (for example `ui`, `qa`, `sql`) belong in `weak_terms`.
- A user pack can only be created from the form/tool with simplified fields; the full format above needs a JSON file in
  `<database folder>/careers/`.

## Independent Industrial and Systems market exploration

Canonical offers now receive independent deterministic projections in `job_market_classifications` for
all installed packs during ingestion, including replacement of detected skills on re-ingestion. Existing
canonical relevance fields remain for compatibility; they are not the independent projections.

`GET /api/jobs?market_id=industrial_engineering` and `market_id=sistemas_software` read a selected projection,
including its primary area, relevance and skill filter. Missing or rule-stale projections are rebuilt from
saved descriptions. This does not rewrite canonical classifications or personal state. The first scoped
read may take longer while backfilling existing offers.

`GET /api/markets` describes installed markets. `GET/PUT /api/markets/{market_id}/profile` stores independent
search preferences (arrays: areas, roles, locations, work_modes, seniority, excluded_titles). PUT replaces
the preferences object and increments its version. Select them with `profile_mode=saved` on job and skill-overview queries. They filter the market rather than changing the legacy match score.
Manual `POST /api/refresh` accepts `market_ids` for either or both built-in markets; its query list is frozen
when requested. Existing clients retain their previous behavior when market IDs are omitted.

Existing databases receive an SQLite backup in `backups/pre-dual-market-*.db` before the additive schema
change. No offer, application, favorite or real profile is removed by this migration.

On desktop, Filters shows a single Market selector, saved automatically in browser storage. Extra
criteria are collapsed under Filter offers. Switching markets resets optional filters and uses the market's
core and related offers from the last 7 calendar dates in Lima; old per-market filter storage is ignored to avoid restoring restrictive
or hidden saved-search modes. Aborted listing requests cannot replace newly selected results. Loading
and API errors are distinguished from a valid empty result. Favorites/applications/archive stay shared.

Capture controls live in Settings -> Search -> Market, with Industrial, Systems, or both. Search profiles
remain editable in Settings and available through the explicit `profile_mode=saved` API; the minimal map
selector uses unrestricted market exploration rather than implicitly applying a personal saved profile.

Existing-offer backfill serializes rebuilds per database, computes classifications with no open DB
transaction, and commits batches of at most 50 projections under an immediate write transaction. A
content-hash guard prevents overwriting a newer capture. This avoids the read-to-write lock failures
observed when listings/competencies and market capture ran concurrently. Warm markets return without
waiting for an unrelated rebuild. First schema initialization is serialized per database and commits its
catalog before publishing readiness to other request threads.

Market read tools now inherit the UI query context or accept explicit `market_id`; their responses report
resolved scope. Parallel calls are isolated. See [agent scope](agent.md#market-scoped-reads).
Free-form Analysis SQL, legacy match scores and scheduled capture retain their reference behavior.
Cross-market scores are not invented: reference scores and legacy snapshots are labelled accordingly.
Versioned history, source-level availability verification and full market-aware scoring remain planned.

## Focused expansion (2026-11-04)

`ingenieria_mecanica` is an experimental third pack; Industrial and Systems remain the main capture targets.
Mechanical uses contextual evidence gates and excludes reviewed physical trade titles and unrelated IT/tool
mentions. Its regression fixtures are diagnostic, not a measured precision estimate. Reference scores now
read that market's independent projection (`v2.1-evidence`).
