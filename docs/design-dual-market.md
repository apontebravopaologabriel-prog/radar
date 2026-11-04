# Dual-market exploration: Industrial Engineering and Systems/Software

Status: proposed implementation plan, 2026-10-31. This document does not describe shipped behavior.

## Product outcome

A person can explore both markets, capture offers for either or both, and keep a separate search profile
for each. Switching markets must not overwrite classifications, preferences, scores, or capture state.
The installation continues to represent one person, with one factual career history and master CV.

An offer is a canonical record, not property of the search that discovered it. A BI offer may belong to
both markets with different area mappings and explanations. Discovery provenance and professional
relevance are separate facts. Academic eligibility is reported only when supported by posting text.

## Evidence from the current implementation

- `careers/` already supplies two data-driven packs and custom packs.
- `api_agent.set_career()` and `tools.set_career_track()` only change a global setting.
- `jobs.relevance_*` and `job_areas` contain one classification per offer, without a market key.
- `user_profile` is effectively a singleton; its target roles currently contain desired areas.
- `job_scores` is keyed by job and person, rather than search profile and market.
- Existing-offer ingestion updates descriptions and areas but does not rebuild job skills.
- Classification maintenance does not rebuild skills; its fingerprint omits skills and some relevance inputs.
- Manual refresh and scheduled capture use different query plans and separate run locks.
- The scheduler has a global `refresh_last_at`, including after unsuccessful captures.
- The frontend has Industrial-specific labels; the generated skill includes tools omitted from MCP.

## Scope and terminology

Use the existing pack IDs as market IDs: `industrial_engineering` and `sistemas_software`.
Preserve custom-pack compatibility; limit the validated product experience to the two built-in markets.

| Concept | Ownership | Example |
| --- | --- | --- |
| Person and factual skills | Shared | Education, experience, SQL level, photo, contact |
| Market pack | Market | Areas, role families, aliases, contextual rules, framework mapping |
| Search profile | Person + market | Preferred roles, areas, seniority, city, modality, exclusions, weights |
| Offer | Shared canonical record | Title, employer, description, source URLs, observations |
| Classification | Offer + market | Relevance, up to three areas, detected skills, evidence, rules hash |
| Personal fit | Offer + search profile | Score, dimension coverage, explanation, missing evidence |
| Application and favorite | Shared by offer | Applied status and favorite state across both views |

Create one initial search profile per market. Design identifiers to allow more later, without building
a general persona-management system in this release. Names such as "Industrial — analytics" are search
directions, not alternative identities or invented academic qualifications.

## Knowledge frameworks and visible areas

Retain Industrial's 14 ISEBoK area mappings. Restore broad professional coverage: production, quality,
maintenance, ergonomics, and other branches are not globally excluded because the author prefers office work.
Move current personal title priorities and exclusions into the migrated Industrial search profile.

For Systems, use ACM/AIS IS2020 as the organizing reference, complemented by SWEBOK V4 for software
engineering detail. Use CS2023 selectively for computing specializations. These are competency/curriculum
references, not occupational eligibility rules or official certifications of Radar's taxonomy.

Proposed visible Systems families:

| Stable area key | Visible label | Typical roles |
| --- | --- | --- |
| software | Software development | Backend, frontend, full stack, mobile |
| systems-analysis | Systems analysis and enterprise solutions | Functional analyst, ERP/SAP, integrations |
| data-bi | Data management and business intelligence | BI analyst, DBA, data engineer |
| ai | Artificial intelligence and data science | Data scientist, ML engineer |
| infrastructure | Infrastructure, networking and cloud | Network administrator, cloud engineer |
| delivery | DevOps, SRE and platform operations | DevOps engineer, SRE |
| security | Cybersecurity | SOC analyst, security specialist |
| quality | Software quality and testing | QA analyst, automation tester |
| product | Digital product and interaction | Product owner, UX/UI |
| governance | IT governance, projects and services | IT project manager, IT service manager |
| support | IT support and workplace technology | Help desk, application support |

This is a Radar adaptation to be validated with postings. Do not label every Systems area core by default
without reviewing evidence, and do not confuse ISEBoK's system design domain with the entire Systems/IT market.
Framework mappings are references per area; interface labels remain readable Spanish.

Each pack gains schema/version metadata, stable area/role keys, framework references, representative titles,
positive and negative contextual signals, and query families. Skill identities are global and normalized;
market detections retain their own evidence. Generic terms such as SQL or Excel alone cannot establish relevance.
Use whole-word or explicitly tested phrase matching rather than unrestricted substring checks.

## Data design

Keep canonical jobs, source appearances, observations, applications, favorites, real skills, and master CV shared.
Add market-scoped structures rather than duplicating databases or jobs:

- `career_areas`: market ID + stable area key + label + framework mappings. Names need not be globally unique.
- `search_profiles`: person ID, market ID, name, desired roles/areas, seniority, locations, modalities,
  exclusions, scoring preferences, version, timestamps.
- `job_market_classifications`: job ID + market ID, relevance, evidence, pack/rules hash, content hash,
  classifier version, computation time. One current result per pair.
- `job_market_areas`: classification reference + area key, primary flag, evidence, confidence.
- `job_market_skills`: classification reference + global skill ID, requirement type and textual evidence.
  This lets a pack change its skill vocabulary without deleting another market's detections.
- `job_search_scores`: job ID + search-profile ID, classification revision, person-skills revision,
  search-profile revision, algorithm version, dimensions, coverage, explanation, computation time.
- `capture_runs` and run steps: requested markets, frozen query/rule context, source/query/location,
  per-source outcomes, observed/new/updated counts, failures and timestamps.
- Per-market capture schedule/status and market IDs on new market snapshots.

Enforce foreign keys, uniqueness of current classification and primary area, and profile/market agreement.
Include every classification input in the appropriate hash: skills, aliases, education/context signals,
area rules, title rules, and engine version. A changed posting invalidates both market projections.
Do not serve an old score as current after its profile, classification, or source content changes.

## Capture and classification flow

1. The request chooses Industrial, Systems, or both, independently of the market currently on screen.
2. Build an immutable run context. Changing the UI or profile cannot retarget a running capture.
3. One coordinator is shared by scheduled, manual, CLI and agent captures. Queue conflicting runs;
   deduplicate identical source/query/location/window requests within a run.
4. Share connectors by portal. Reuse their existing rate limits and independent failure handling.
5. Normalize and merge into one canonical offer. Preserve useful existing content when a result card
   supplies fewer fields. Record all discovery provenance and observations.
6. Classify changed offers under both built-in packs, even if only one market initiated the discovery.
   For unchanged offers, reuse projections only when content and rules hashes match.
7. Write each projection's areas, skills and relevance together in a transaction. Refresh affected scores.
8. Publish run outcomes and freshness by market and portal. Keep last attempted, last successful and
   partial-success states distinct; an all-failed attempt is not a successful market update.

Use query families for broad market exploration and profile-specific searches for focused discovery.
Distribute limited budgets fairly across areas, cities and portals; expose skipped steps. Do not silently
truncate the end of an ordered plan. Network operations need bounded timeouts; abandoned worker threads
must not write late results after cancellation or bypass the capture coordinator.

## Queries, profiles, and scoring

All market views resolve an explicit context: market ID, optional search-profile ID, and filters.
Apply it consistently to listings, map counts, nearby results, skills, salaries, feed, recommendations,
gap analysis, snapshots, audits and reclassification. Validate that the profile belongs to the market.
Advanced read-only SQL must state its scope; do not claim arbitrary SQL is automatically market-filtered.

Keep market demand separate from personal preferences. "Entire market" displays classified offers with
no personal-fit filter. "My search" applies the selected profile. Favorites remain the existing CV targets;
role preferences are not a second offer-selection mechanism.

The scoring correction required for this release:

- Compare declared skills with explicit requirements; differentiate levels only where the requirement
  supports a level. Otherwise show skill presence and unknown depth rather than inventing proficiency.
- Compare seniority with the selected search profile rather than always rewarding junior titles.
- Replace constant education scores with explicit evidence/unknown handling. Exploration of Systems
  does not imply that the person has a Systems degree.
- Show observed dimension coverage. Scores are deterministic preference indices, not hiring probabilities.
- Preserve old scores as legacy where useful; recompute new results under an explicit algorithm version.

Offer filters may distinguish career-related work from postings explicitly accepting a named degree.
An inferred occupational relationship cannot be presented as confirmed academic eligibility.

## Interface, agent and CV contracts

Put the market and search-profile selector in the existing floating Filters tool and in Settings. Show
the current market in the offer tray/Analysis context. Preserve the desktop map, rail and floating controls.
Remember filters, district and profile per market. Switching market is a read/context operation; it does
not scrape, rewrite the real profile, or run a destructive reclassification.

The refresh action offers "Industrial", "Systems", and "Both", with per-market/per-portal progress.
Pending classification is shown as pending, not out of focus or zero demand. Cancel/ignore stale frontend
requests and key caches by market, profile and filters so late Industrial responses cannot replace Systems.
Mobile receives equivalent context and cache isolation without adding new mobile product features.

Add an Analysis comparison with Industrial total, Systems total, shared offers, and unique union total.
Explain that these describe the captured sample, not the entire Peruvian labor market. Use the same date,
location and source filters for comparisons. An overlap offer counts once in the union and once in each
market's denominator; percentages from the two markets must not be added.

Pass market and search-profile IDs through API clients, agent context and relevant registry tools. Resolve
the context once per agent turn; tool results echo it. Legacy clients may use a documented default market,
but new internal calls pass explicit context. Validate profile/market combinations at the backend.
The generated skill and MCP tool set must agree. Writes retain existing approval/read-only contracts.

The factual CV, contact, education and skills stay shared. CV drafting can emphasize different verified
experience. Application packages capture market/profile IDs and versions. Generating another direction
for the same offer creates a separate draft/version, never silently overwrites an exported application.
Hypothetical target CVs retain their existing warning and export restrictions.

## Migration and recovery

1. Back up the existing database through SQLite's backup API before any migration. Retain personal files.
2. Add schema in `schema_sqlite.sql` and existing-database handling in `_ensure_runtime_schema()`.
   Track this migration's completion so it is resumable and idempotent.
3. Preserve the real profile ID, skills, CV, applications, favorites, hidden records and observations.
4. Migrate current desired areas/title priorities to the old active market's search profile. Keep unmapped
   preferences visible for review; never discard them. Create the second market profile as unconfigured.
5. Rebuild both classifications from saved raw descriptions. Existing global labels are untrusted for
   attribution because the database may contain results from multiple previously active packs.
6. Backfill in resumable batches. Readers must distinguish pending, current and failed projections.
7. Recompute scores and market catalogs. Old snapshots keep legacy/unscoped provenance; do not invent
   historical market splits. Start new scoped snapshots with the migration.
8. Cut over readers and writers together under one controlled schema/application version. Keep old tables
   during transition and validate counts/integrity before declaring completion.
9. Document recovery from a failed migration and restore from a validated pre-change snapshot. A rollback
   after new user activity must preserve/export that activity rather than blindly restore an older file.

## Implementation sequence and reviewable deliverables

| Phase | Deliverable | Completion gate |
| --- | --- | --- |
| 0. Baseline | Isolated DB fixtures, regression examples, scope inventory | Current failures reproduced without personal-data access |
| 1. Pack contract | Stable IDs, framework mappings, general Industrial pack, Systems families | Packs validate; no career-specific Python rules |
| 2. Persistence | Market classifications, search profiles, versioned scores, resumable migration | Existing DB migrates twice safely; recovery tested |
| 3. Capture | Shared planner/coordinator, explicit frozen contexts, two-market classification | Market switch during capture cannot mix results |
| 4. Queries and fit | Scoped repository/API/feed/analytics and corrected scoring | No cross-market leakage; stale scores detected |
| 5. Product integration | Selectors, per-market state, comparison, agent/MCP and CV context | Desktop/mobile/API agree; old clients handled explicitly |
| 6. Pilot | Two real captures, reviewed sample, docs and full verification | Acceptance scenarios and honest capture reports pass |

Phases 2–5 are one coordinated feature: do not ship a selector backed by partially scoped queries.
Keep current source adapters, single-user storage and supported custom packs. Cross-market exploration
does not require a third career, a cloud service, automated applications or an LLM classification engine.

## Validation and acceptance

Build a reviewed corpus of at least 120 examples: 40 Industrial-focused, 40 Systems-focused, 20 shared,
20 irrelevant/ambiguous. Cover descriptions, not just titles, including production, maintenance, ERP,
BI, support, software sales, internships and senior roles. Separate rule-development and held-out sets;
record acceptable multi-area answers and explicit unknowns. Proposed pilot targets: core precision at
least 90% and core recall at least 80% per market, evaluated separately, with abstentions reported.
These are proposed release gates, not measured current performance.

Required end-to-end scenarios:

1. Industrial capture -> Systems switch -> Systems capture -> Industrial return: filters/preferences and
   classifications remain independent; offer/favorite/application identity is preserved.
2. A BI offer belongs to both markets with separate areas and scores but one canonical job ID.
3. An unrelated offer never appears as core merely because it mentions a degree or Excel.
4. A description edit updates skills, relevance and fit in both markets without losing observations.
5. A pack change invalidates only affected projections; a personal-skill change invalidates affected scores.
6. Switching market during an active/failed/partial capture cannot retarget it or mark the other market fresh.
7. Migration interruption/retry and pre-change recovery preserve the documented data invariants.
8. API, desktop, mobile, agent and MCP return the same scoped counts and tool availability.
9. Overlap and union counts remain correct under date/source/place filters; historical unscoped snapshots
   are clearly distinguished from new scoped snapshots.

Run repository checks: pytest, Ruff, frontend lint/tests/build, and `git diff --check`; investigate HTTP-test
hangs separately before claiming full verification. Exercise Windows-compatible migration/capture paths.
Measure the existing listing/feed performance budget against 5,000 canonical offers and two projections.
Do not edit `frontend/out`; document the final behavior in README, careers/database/operations/agent/CV
docs and product help; regenerate the skill through its exporter.

## Reference frameworks

- IISE ISEBoK: https://www.iise.org/Details.aspx?id=43631
- ACM/AIS IS2020: https://www.acm.org/binaries/content/assets/education/curricula-recommendations/is2020.pdf
- IEEE Computer Society SWEBOK V4 topics: https://www.computer.org/education/bodies-of-knowledge/software-engineering/topics
- ACM/IEEE-CS/AAAI CS2023 areas: https://csed.acm.org/knowledge-areas/
