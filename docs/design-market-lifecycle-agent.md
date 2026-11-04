# Market evidence, vacancy lifecycle and agent context

Status: phases 1 and 3 delivered, 2026-11-01; later phases remain proposed. This extends the
[classification plan](design-market-ingestion-classification.md)
after the [first correction batch](classification-correction-2026-11-01.md).

Implementation update: the first release implements opportunity selection and market-scoped agent reads
(phases 1 and 3), including geographic context, explicit scope metadata and honest score limitations.
Source-level liveness evidence, stronger description review and versioned history (2, 4, 5) remain planned.
Validation: 345 Python tests, 12 frontend tests, lint and production build passed. Local API and agent
tools agreed on the seven-day active selections (684 Industrial, 186 Systems at verification time),
including skill totals. Unknown availability remained eligible and closed detail remained accessible.
The 8,341 original offers and personal state were verified unchanged. No live LLM calls were used.

## Verified baseline

Read-only SQLite counts on 2026-11-01: 8,341 offers; publication status is unknown for 7,464, open for
832 and closed for 45. These are stored states, not independent confirmations of current availability.
One closed offer still satisfies Industrial's active/canonical/non-hidden core-or-adjacent selection
with the existing seven-day filter. There are 103,040 observations across 8,336 job IDs.

Source findings:

- `db/queries.list_jobs()` filters activity and publication dates without excluding closed/expired
  publication states. `recommendations()` excludes them; the no-profile Today feed uses `list_jobs()`.
- `liveness.check_application_status()` checks one source URL per offer and treats successful HTTP
  responses without a closure phrase as open. Generic landing/login pages can therefore look open.
- `expire_stale_jobs()` deactivates jobs unseen by any source for 45 days. This is absence of recent
  discovery, not a confirmed closure, and source failures/partial coverage can affect it.
- Ingestion reactivates rediscovered offers but can retain an older closed publication status when the
  incoming result says unknown. Rediscovery and verified reopening need separate transitions.
- Classification permits a qualifying title independently of duties. Description conflicts and
  incomplete input are not yet a first-class review state. Academic eligibility is not structured.
- Desktop sends `filters.market_id` to the agent, and the loop includes it in the prompt. Search,
  breakdown, salary, nearby and detail tools still largely query global/canonical data. The static
  persona supplies Industrial ISEBoK labels, not the selected Systems taxonomy.
- Read tools run through `ThreadPoolExecutor`; market inheritance must be explicitly carried into each
  submitted call. Prompt instructions or a mutable global market cannot guarantee isolation.
- Observations retain a content hash and limited metadata. Canonical descriptions can be overwritten.
  Current snapshots aggregate legacy areas/skills without independent market/rule-version identity.

## Decisions

1. Keep historical offers. Automatically remove confirmed closures from actionable results, not from
   the database or personal applications. Lifecycle archive is separate from user-hidden state.
2. Retain unknown-status offers in ordinary market exploration with a discreet unverified label.
   Provide verified-open-only as an optional filter; making it mandatory would hide most saved offers.
3. Use one agent with knowledge of both markets, a single factual person profile and an explicit
   selected query context. Cross-market comparison is deliberate and uses comparable periods.
4. Prefer supported duties over titles when they conflict. Preserve uncertainty and review paths;
   never silently delegate validity, scores or qualifications to an LLM.
5. Preserve content and classification revisions prospectively. Do not invent missing historical
   descriptions or market states from current data.

## Phase 1 — One opportunity-selection policy

Introduce a shared query context: market ID, core/related scope, date range, lifecycle scope, optional
search profile and geographic/skill filters. Default desktop remains all areas of the selected market
with seven visible calendar dates in Lima; align date boundaries rather than keeping independent SQL
interpretations. Capture lookback remains separately configured for overlapping runs.

Define opportunity selection as active canonical jobs in the chosen market/date range with publication
status open or unknown, excluding user-hidden state where appropriate. Closed and expired publication
states are excluded. Apply the same predicates to map, list, skills, nearby, feed and recommendations.
Personal applied-state exclusions are explicit context flags, not hidden differences between counters.

Historical queries and saved/application detail remain accessible with an explicit historical scope.
Show publication closure without rewriting the user's application progress or hiding favorites.
Return resolved context, timestamp and scope with query results so counts are interpretable.

Acceptance: the known closed Industrial case disappears from opportunity results; unknown offers remain
available; map/list/skills agree for identical filters; a saved closed job and its application stay readable.

## Phase 2 — Reliable publication lifecycle

Keep separate dimensions for publication status, last observed time, visibility age, user state and
occupational classification. Seven days old is not closed. Unseen for 45 days means stale discovery.

Add source-level status observations: source URL/identity, checked time, outcome, evidence code and
supported content revision. Reduce them to an offer-level state deterministically:

| Evidence | Outcome |
| --- | --- |
| Matching vacancy with explicit positive availability evidence | Source verified open |
| Matching vacancy explicitly closed/expired, or its URL removed | Source closed/expired evidence |
| Login/generic redirect, blocked request, timeout, missing identity | Unknown; retain previous evidence and its age |
| At least one sufficiently fresh verified-open source | Offer open; expose source disagreements |
| All relevant known sources freshly confirmed closed | Offer closed |
| Mixed closure and missing/unknown/stale source evidence | Offer unknown or stale, not confidently closed |

A 200 response alone cannot establish availability. A surviving search card alone cannot establish
reopening; require fresh detail evidence. Reopening creates an event instead of erasing the previous
closure. Record a closure detection time, not an invented exact employer closure date.

Prioritize checks for currently visible, saved and soon-to-apply offers, then stale verification. Keep
bounded per-portal budgets, backoff and existing URL/network guards. Do network I/O outside transactions.
Track successful source/family coverage so failed captures do not count as evidence of disappearance.

Acceptance: 403/429 and landing pages never become confirmed closures/openings; one closed source cannot
override another fresh open source; duplicate capture cannot silently reopen a closed offer; repeated
checks are idempotent and retain evidence history. Use fixtures, not live portal sessions, for tests.

## Phase 3 — Agent queries that match the visible market

Extend existing read tools and their underlying queries with market, period and lifecycle scope. Include
search, offer details, breakdowns, skills, salaries, nearby, comparisons, feed, recommendations and fit.
Mark any remaining legacy fit score explicitly as reference-career scope until market-aware scoring
is implemented. A new market label cannot turn a legacy score into a Systems score.

At turn start validate and freeze the UI query context. Resolve defaults server-side before dispatch;
pass the immutable context explicitly to each parallel call. Do not rely on implicit thread context
propagation or a global variable. Include resolved scope in repeated-call signatures and cache keys.
Two simultaneous chats or an intervening UI market switch must not change an in-flight query.

The model may request an explicit alternate market for a comparison. Execute both queries with the same
dates and lifecycle policy; expose shared job IDs, and count each job once in a combined union. MCP calls
without UI context use an explicit argument or labelled reference-career default. Maintain backward
compatibility without pretending that an unscoped result represents the selected map.

Replace the static all-Industrial area instruction with a short neutral persona and validated pack
metadata for the selected market. Load the second market's area definitions only when needed. Preserve
one factual education/experience profile; changing views never creates a Systems degree or new skill.
Separate persistent search preferences per market from ephemeral navigation and shared personal memory.

Update raw SQL guidance to use independent projections. Arbitrary read-only SQL remains explicitly
unscoped unless its scope is demonstrable; do not automatically rewrite arbitrary SQL or let the agent
present an unscoped query as a count of the visible map. Treat posting text as untrusted evidence.

Write confirmation cards retain the context shown in their preview; approval after navigation does not
retarget an action. Existing write/read-only/plan-mode boundaries remain in force.

Acceptance: scripted agent tests cover Industrial, Systems, shared roles, comparison deduplication,
mid-turn market switches, parallel independent chats, MCP without UI, stale chat history and conflicting
posting instructions. Tool counts match API counts for equivalent context without spending live LLM tokens.
Update `docs/agent.md`, help and the generated skill when implementing tool signature changes.

## Phase 4 — Duties, academic evidence and review

Keep title-based retrieval broad. For well-formed descriptions, determine the principal occupation
from duties and detect title/function conflicts before admitting a core result. For short or absent
descriptions use a labelled provisional state rather than silently treating a title as verified duties.

Extend current parsed evidence with section certainty, role signals, incompatible occupation signals,
academic alternatives/degree level and mandatory/desirable wording. Preserve original source spans.
Do not infer that a degree is accepted from employer marketing, skill names or “related degrees”.

Separate primary occupation, shared/transition duties, academic compatibility, specialization and
personal fit. A technical IT role belongs to Systems even if this person lacks its experience; using
an ERP in accounting is different from implementing it. Keep conflicting evidence in the explanation.

Add a small review queue with proposed classification and supporting/opposing spans. Reviewing a case
produces a versioned correction and a paraphrased regression fixture; it is not a global keyword ban.
Measure precision, recall and uncertainty separately with the held-out corpus proposed in the earlier
plan. Rule drift, total offers and passing unit tests do not establish classifier accuracy.

## Phase 5 — Historical evidence that supports trends

Add immutable source content revisions only when relevant content changes, plus dated status events and
market classification revisions. Link each observation to its selected content revision and classifier/
pack version. Protect existing richer detail against partial incoming cards and retain provenance.

Store market-specific monthly/weekly snapshots with source coverage, unique canonical offers, skill
counts, salary sample sizes and missing-data rates. Separate new postings from repeated sightings and
republications. Estimate publication duration as an observation interval, not exact hiring time.

Keep two explicitly different analyses: what Radar classified at the time, and historical texts
reclassified using today's rules. Never attribute classifier upgrades or expanded portal coverage to
real demand growth. Do not backfill unknown historical descriptions from the current canonical text.
Existing aggregates can remain labelled legacy snapshots.

No automatic job deletion. If storage becomes a measured problem, first deduplicate unchanged payloads
and compress/export old bulky content with verification. Keep jobs, personal state and history indices.
Do not impose arbitrary destructive retention while the current use case benefits from history.

## Rollout and verification

Implement phases 1 and 3 first as the smallest useful release: coherent opportunity results and an agent
that queries the selected market. Then strengthen source verification (2), description evidence (4) and
longitudinal analysis (5). Preserve honest unknown states until verification is trustworthy.

Each implementation phase needs an isolated migration/test fixture, read-only impact preview, backup
before production writes and rollback for derived data without overwriting later user actions. Schema
changes belong in `schema_sqlite.sql` and the existing-database runtime migration path. Keep network and
classification work outside write transactions and use content/version guards for bounded commits.

Run Python tests, Ruff, diff checks and frontend lint/tests/build when implementation changes the UI.
Check API counts and selected real cases after rollout. Keep the minimal Mercado control; put lifecycle
and classification explanations in detail and optional filters rather than expanding the permanent menu.

The original planning turn changed documentation only. Opportunity selection and agent reads are now
deployed; the remaining lifecycle-verification, description-review and history phases are not deployed.
