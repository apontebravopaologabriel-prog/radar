# Evidence-based ingestion and career market classification

Status: proposed implementation plan, 2026-11-01. No behavior or production data is changed by this
document. It refines the capture/classification portions of [dual-market exploration](design-dual-market.md)
using the [classification audit](classification-audit-2026-10-31.md) and additional saved descriptions.

## Product decisions

- Keep one canonical offer and independent market projections. Switching the visible market never
  moves, copies or deletes an offer and never changes a running capture's targets.
- The user clarified that “Todas” means **all areas of the selected market**, not combining markets.
  Industrial and Systems both open without an area or personal-role restriction, showing the last
  seven calendar dates in Lima. Remember the market; reset optional filters on market changes.
- “All areas” must retain market membership. It must not expose every out-of-focus record merely
  because every saved offer has a projection for every market.
- Require occupational evidence to qualify an offer. Keep academic requirements, technical
  specialization and personal fit as separate explanations.
- Preserve shared roles and plausible career transitions, including uncertainty about accepted degrees.
  An advanced software role remains a Systems opportunity even when it is unsuitable for this person.
- Keep the minimal Mercado selector and collapsed filters. Add concise evidence to offer detail rather
  than adding permanent controls to the map.

## Current flow, verified in source

| Stage | Current behavior | Consequence |
| --- | --- | --- |
| Scheduled search | `capture.run_capture()` uses `active_pack().market_queries` for Lima and `.queries` elsewhere | Viewing another market does not ensure its jobs are being searched. |
| Manual search | `refresh.start_refresh()` unions `.queries` from requested market IDs | Manual and scheduled coverage differ; query ownership is discarded after union. |
| Place search | `start_place_refresh()` uses the active pack and takes the first queries/steps | It can target the wrong market and favor the beginning of an ordered plan. |
| Source extraction | JobSpy requests descriptions; Computrabajo enriches cards and appends employer context into the same description | Detail failures produce partial input; employer prose can dominate classification. |
| Pre-storage filter | `pipeline.run_ingestion()` calls `filter_recent_jobs()` | Only publication freshness is screened here; no occupational gate exists. Undated, future and old results are discarded before this storage path. |
| File import | CLI imports can call ingestion without the same freshness gate | Search ingestion and file imports have different admission paths. |
| Canonical ingestion | Repository normalizes, fingerprints, enriches and classifies with the active pack; it records a run with query `batch` | Discovery source/query/market provenance is insufficient for evaluating search quality. |
| Market projections | `project_job()` independently classifies every ingested offer under installed packs | Correct storage boundary, but both projections inherit weak textual evidence rules. |
| Duplicate refresh | Canonical description is replaced by the latest incoming description | A partial result can replace richer text. This is a code-path risk, not a proven count of damaged records. |
| Presentation | Desktop starts with `area=""`, `max_age_days="7"`, `relevance_tier="core"` | All areas are already selected, but adjacent roles remain hidden. Clearing relevance entirely would expose all stored projections, including outside careers. |
| Existing maintenance | `classification_audit()` compares canonical fields with current active-pack rules | Rule drift is not a labelled accuracy evaluation, and this audit does not fully represent independent market projections. |

The capture window is intentionally different from the visible window: scheduled capture defaults to
10 days to overlap weekly runs; manual ingestion defaults to 14. Keep overlap rather than shortening all
capture paths to seven. Define visible dates centrally: current `age <= 7` / SQL `-7 days` includes eight
calendar dates. The proposed visible seven-day range is today plus the previous six dates in Lima.
API, counters and UI must use the same range; capture lookback keeps its separate meaning.

Capture and manual refresh also have separate coordination. `_run_with_timeout()` abandons daemon
threads without cancelling them; a timed-out step can continue into ingestion. The scheduler updates
`refresh_last_at` even when a run fails. These issues affect confidence in freshness and market coverage.

## Additional description review

On 2026-11-01 a read-only query inspected 12 diagnostically selected descriptions across functional
analysis, support, technical trades, automation, development and BI. The database then contained 8,341
canonical records, 38 with missing or fewer than 200 trimmed description characters. Character count is
only an input-quality indicator; long employer boilerplate does not make a description adequate.
This is not a random sample or an accuracy estimate.

| Local ID | Observed duties and requirements | Expected treatment |
| --- | --- | --- |
| `4e2c6bc6-0abd-4a15-a4d3-c1b06a5cc706` | Analista Funcional SAP: implementation, logistics modules and process improvement; explicitly accepts Systems, Software, Informatics and Industrial | Strong shared functional role, with explicit academic alternatives. Preserve in both markets. |
| `a63b1478-53ba-4966-b470-8424d803beca` | Analista Funcional TI: Oracle/PLSQL, controls, SQL and automation; accepts Systems, Informatics, Software or related degrees | Systems role with transferable process skills. Industrial acceptance is possible but not explicit. Do not label it academically confirmed. |
| `152e7b01-7d43-4fca-b53a-64b84ce8d498` | Analista Administrativo / Power BI / Automatización: builds digital tools, dashboards and automated controls; accepts Industrial and Informatics | Genuine bridge, supported by duties rather than tool names alone. |
| `56b6a8c6-8002-4267-85b3-6acf999ac600` | Administración de Ventas / SAP / Power BI: commercial reconciliations and accounting entries; explicitly accepts Industrial | Industrial business/control opportunity. Using SAP does not make it functional IT; BI mentions require checking whether the work builds analytical solutions. Current Industrial exclusion and Systems core need review. |
| `9640eb02-f7a9-4e3d-8157-532d20b223f2` | Full-stack/backend senior: .NET, microservices, Kafka, APIs, Docker, Kubernetes and CI/CD | Strong Systems software role with advanced specialization. Do not promote it to Industrial because it improves business processes. |
| `75380e66-fb1c-4eea-98bb-1e37e8844340` | ATM installation support: operational coordination plus specific ATM knowledge; asks for technical IT education | IT support/operations with a specific qualification requirement, not automatically an Industrial bridge because it tracks projects and inventory. |
| `16dff89c-65c0-4d69-bff7-85f10d9df8f8` | Air-conditioning technician: installation, electrical repair, refrigeration qualification | Trade maintenance; keep physical domain distinct from software and engineering planning. |
| `7b1e3765-de7f-486e-98f1-87be84833181` | Cleaning technical rooms in a data center | Cleaning remains the occupation even in a highly technical workplace. Preserve this correct negative case. |
| `34001d50-ad73-4122-928a-d9167219dcfe` | Subgerente de Soporte Comercial: process management and digital-agent implementation; accepts Industrial and Systems among alternatives | Candidate shared management role. A commercial title should not veto substantial process/digital responsibilities; seniority is a separate personal-fit issue. |

Combine these with the previous audit's maritime-container, physical-infrastructure, clinical laboratory,
maintenance-planning, trade-maintenance and production-supervision cases. Develop fixtures from brief
paraphrases; do not commit entire postings or personal data.

## Proposed pipeline

```text
explicit capture context -> balanced queries -> source cards and details
  -> validate and retain source observations -> select best supported canonical text
  -> parse role / requirements / employer context once
  -> classify independently for each installed market
  -> explain shared roles, academic evidence and specialization
  -> write versioned projections -> apply selected market + visible date range
```

### 1. Capture planning and admission

Use one planner/coordinator for scheduled, manual, place, CLI and agent capture. Freeze requested market
IDs, pack versions, query families, portals, location, date window and budget at run start. A user's
selected map market and a capture's requested markets are independent inputs. Scheduled capture should
default to both enabled built-in markets once their capture preferences are configured.

Define query families in pack JSON: functional ERP, BI/analytics, process automation, logistics/planning,
production/quality, software, infrastructure, security and support as appropriate. Prefer role phrases
over isolated tools. Query text helps discovery but never grants market membership.

Deduplicate identical portal/query/location steps while preserving every originating market and family.
Allocate the bounded search budget by round-robin across families and markets. Report skipped or
budget-limited steps. Measure meaningful classified yield, duplicate rate, missing-detail rate and
coverage; do not optimize only for the largest number of new jobs.

Admission validates URL, usable content and publication evidence. Missing dates or incomplete details
get explicit reasons and can be retained for bounded detail retries; do not invent dates or assert core
membership. Freshness determines visible eligibility independently of historical retention. An observed
old existing offer updates its observation without deleting history or turning it into a new posting.
Define consistent admission outcomes for file import and connector ingestion.

Fetch each needed detail at most once per source offer/run. Keep portal timeouts, rate limits and source
isolation. Workers fetch only; a coordinator validates an active run token before writing results so
cancelled or timed-out workers cannot write late. Persist run/step outcomes and distinguish attempted,
successful, partial and failed market refreshes. Use a cross-process coordinator for CLI/systemd and API,
with short SQLite transactions and recoverable leases rather than holding DB writes during networking.

### 2. Preserve and structure evidence

Store original source observations and choose canonical content deterministically. Prefer verified
detail over a result card; never replace known role requirements with empty text after a failed fetch.
Record which observation supplied each selected section. A confirmed newer complete detail can replace
older detail; merging must not silently combine contradictory requirements into a fictitious posting.

Parse headings, bullets and unheaded spans into role/title, purpose, duties, requirements, benefits and
employer context. Use explicit source fields when available. Preserve original offsets and section
certainty. Repeated text and employer introductions cannot accumulate occupational votes.

Extract structured academic alternatives: degree family, original alias, technical/university level,
student/graduate/bachelor/licensed requirement, mandatory/desirable wording and scope of “related”.
Support grouped alternatives and negation. Similarity is not acceptance: “Systems or related” cannot be
rewritten to “Industrial accepted”. Store conflicting or ambiguous evidence as such.

### 3. Require contextual occupational evidence

Extend packs with optional structured rules while keeping old custom packs readable. A generic engine
interprets required signal groups, alternative phrases, responsibility verbs and local conflicts. Keep
career-specific aliases and decisions in JSON. Use word/phrase boundaries and local clause context;
do not globally ban a mixed role because it contains one conflicting term.

Starting rules to validate against labelled descriptions:

| Interpretation | Positive evidence required | Insufficient or conflicting evidence |
| --- | --- | --- |
| Software containers | Container deployment/orchestration duties with Docker, Kubernetes or equivalent tested context | Maritime containers in employer prose |
| IT infrastructure | Network/server/cloud administration or engineering responsibilities | Building repair, plumbing and civil construction alone |
| Functional ERP | Requirements, configuration, modules, testing, integration or implementation duties | Entering transactions or consulting reports as a system user |
| BI / automation bridge | Building models, pipelines, dashboards or automated controls connected to business processes | Merely listing Excel, SQL or Power BI |
| Industrial maintenance management | Planning, reliability, budget, asset management, failure analysis or availability responsibilities | Lubrication and repair execution alone |
| Industrial production | Planning, supervision, productivity and process responsibility | Blanket exclusion of production titles is removed |
| Clinical / other exclusive occupation | Determine the principal occupation and its mandatory professional requirement | Incidental quality, stock handling or software use cannot promote it to Industrial |

Primary duties anchor the occupation. Secondary areas, accepted degrees or tools cannot independently
promote a conflicting main role to core. If evidence is insufficient, return uncertainty instead of a high
rule weight. Remove personal target-title overrides from market truth; migrate them to search profiles.

### 4. Explain market relationship, transitions and technical specialization

Keep existing core/adjacent/out-of-focus tiers for compatibility; add structured relationship evidence.
Define default market membership explicitly rather than inferring it from the existence of a projection.

- **Primary occupational match:** clear work in this market.
- **Validated shared role:** duties substantively match both markets. Shared SAP or process automation
  can qualify; preserve an independent result and reason per market.
- **Related transition:** transferable duties exist but occupational evidence is weaker. Academic
  acceptance may be unconfirmed. Do not label this an established shared role.
- **Outside / insufficient evidence:** preserve the record; keep it out of ordinary market results and
  available to explicit audit/review queries.

Academic evidence is a separate field: explicitly accepted market degree, related degrees only,
unspecified degree, explicit other-degree requirement, or ambiguous/conflicting. Personal qualification
then compares these facts with the person's actual education; market membership never guarantees fit.

Represent technical specialization on separate axes: software implementation depth, physical trade
execution and occupation-specific domain requirements, each with evidence and an unknown state.
Do not confuse a technical diploma with advanced software specialization. Seniority and required years
are separate again. A senior developer stays in Systems; an IT support technician is not excluded by the
word “technical”; a cleaning worker does not become IT because the workplace is a data center.

Offer detail can show short Spanish reasons such as “Puente: procesos + implementación SAP”,
“Industrial aceptada explícitamente”, “Solo indica Sistemas o afines” and “Especialización: backend
avanzado”. Do not present rule weights as probabilities or guaranteed employer acceptance.

### 5. Data and API changes

Prefer an incremental schema extension over duplicating jobs or databases:

- Add versioned parsed evidence per job/content revision: sections, academic alternatives, duty signals,
  input quality and selected-source provenance. Parse once and reuse across packs.
- Extend `job_market_classifications` with structured relationship, academic evidence, specialization,
  decision reasons and engine/evidence-schema versions. Existing areas/skills JSON remains usable.
- Add durable capture runs/steps/observations with query family, all originating markets and source
  quality. `job_observations` currently stores metadata without complete historical descriptions;
  preserving classification input revisions needs an explicit source-content snapshot design.
- Fingerprint selected canonical input + parser version + classifier version + relevant pack data.
  Update legacy maintenance fingerprinting as well. Unify the canonical/scoped engine; document and
  test compatibility paths until all consumers use market-aware projections.
- Introduce an explicit API `market_scope` (full market, core only, related transitions, audit-all).
  Full market includes primary, validated shared and validated related occupational matches; it does
  not include outside/insufficient records. Keep old endpoints compatible, with an explicit mapping.
- Send the same market/date/filter context to map, list, counts and skills. Propagate it deliberately
  to analysis, recommendations, feed and CV-gap consumers; do not show an unscoped personal score as
  market-specific. Favorites/applications stay shared and historical.

Schema migrations belong in `schema_sqlite.sql` and the existing-database runtime migration path.
Compute expensive parsing and classification outside write transactions; guard commits against changed
input and apply bounded batches. Pack changes should schedule a visible rebuild rather than trigger an
unbounded full rebuild on an ordinary list request.

### 6. Default view contract

Industrial and Systems both open with: all areas, full validated market scope, seven visible calendar
dates, no seniority/modality/skill/salary restriction and no saved personal-role exclusions. Selecting
another market or pressing Limpiar restores this context. Only the selected market persists.

Use a plain all-areas label; provide audit-all/outside views as an explicit advanced action. Do not label
the scope “Todas” if it actually combines unrelated careers. Relevant technical roles remain available;
the explanation and optional profile filters express specialization and personal distance.

## Implementation sequence and acceptance gates

| Phase | Deliverable | Acceptance before moving on |
| --- | --- | --- |
| A — Baseline | Deterministic corpus sampling, manual labels, input-quality and current-error report | Distinguish classification accuracy from rule drift and search yield; retain negative and outside cases. |
| B — Evidence | Section parser, canonical-text selection, degree extraction and responsibility signals | Partial refresh cannot erase complete requirements; employer boilerplate and repeated terms cannot create a core area. |
| C — Classifier | Contextual pack rules, separated profile policies, shared-role and specialization explanations | All verified regressions pass, including positive cloud/DevOps, production and maintenance-planning controls. |
| D — Capture | Shared planner, durable provenance, fair budgets, cancellation/write coordination | Manual, scheduled and place capture honor requested markets; no late writes after cancelled steps; failures do not count as market success. |
| E — Views | Explicit full-market API scope and consistent all-areas/seven-day defaults | No outside-market leakage; map/list/skill counts agree; switching markets preserves personal state. |
| F — Migration | Dry-run transitions, backup, bounded rebuild and rollback manifest | Report per-market promotions/demotions/uncertainty, validate corpus, then apply only the reviewed version. |

Baseline proposal: 240 unique canonical offers, sampled across stored tiers, both markets, role families,
sources, short descriptions and ambiguous vocabulary. Label each against both markets and preserve
shared/outside/uncertain categories. Use 180 for rule development and 60 held out, grouping near-identical
employer templates to avoid leakage. Resolve ambiguous human labels rather than force binary truth.
Keep the hand-picked regression cases separate from the held-out quality estimate.

Measure core and bridge precision, recall of clear positives, uncertain coverage, and degree-extraction
quality separately per market. Report denominators and uncertainty; a small perfect subgroup does not
prove production accuracy. Provisional goals are at least 95% core precision and 90% recall on clearly
labelled positives, plus zero failures in the named critical regressions. Treat these as validation goals,
not claims of achieved quality; expand evaluation if subgroup samples are too small.

Include tests for negated/desirable requirements, “related degrees”, missing dates, Lima midnight,
short tool aliases, trade/IT ambiguity, shared degrees, duplicate partial refresh, changing rule versions,
two simultaneous runs, stale-content guards and preservation of favorites/applications. Run the repository's
Python and frontend checks and a real static build before enabling changed UI behavior.

The production dry run uses read-only input and separate proposed projections. Before applying, create
a consistent database backup and record input/rules versions. Recompute both market projections from
the same selected canonical content; invalidate affected fit scores. Verify scoped counts and reviewed
cases after the rebuild. Rollback restores derived revisions without deleting newly captured offers or
overwriting personal state created after the backup. Keep any newly registered write tools behind the
existing confirmation contract; do not silently deploy a production rebuild from a planning task.

## Scope of this planning change

This document is the deliverable for the requested analysis and plan. The existing defaults and classifier
are unchanged. First implementation work should establish the labelled baseline and evidence parser;
changing a few generic words alone would leave the ingestion, shared-role and academic-evidence gaps.
