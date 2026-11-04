# Project review and recommended direction — 2026-11-02

Follow-up: the capture/identity correction is deployed. Stable source identity precedes mutable titles,
empty fields retain known metadata, failed batches roll back, download deadlines cannot ingest late,
and search runs preserve query/market/rules context. Scheduled capture is configured for both built-in
markets on the author's installation. Scheduler failure handling separates attempts from successes.
Validation: 357 Python tests, 12 frontend tests, lint/build and a real-data-copy identity check passed.
All 8,385 production offers and personal state were preserved. The gitignored review artifact
`backups/source-identity-review-20261102.json` retains 51 inactive orphan candidates and 39 ambiguous
source-identity groups for explicit review; they were not automatically merged or deleted.
The next evidence-scoring correction is documented in [scoring-evidence-2026-11-02.md](scoring-evidence-2026-11-02.md);
the weaknesses below describe the original review snapshot. Versioned historical content and the broader cross-process capture coordinator remain follow-up work.

## Recommendation

Concentrate Radar on a complete, trustworthy decision loop for Industrial professionals moving toward
data, business systems and automation: discover suitable live opportunities, distinguish qualification
from interest, produce a truthful application and learn from outcomes. Retain the map as exploration,
the CV Studio as an action surface and the agent as an explanation layer over the same evidence.

Pause career-pack expansion and major new interfaces until source coverage, offer identity and fit
are demonstrably reliable. This is a product hypothesis based on the author's workflow, not validated
commercial demand. Local-first, one factual person profile and explicit human approval remain strengths.

## Scope and evidence

Reviewed README, architecture, roadmap, known issues, CI/release configuration, capture, scheduler,
ingestion, deduplication, scoring, CV evidence guard and agent confirmation code. Performed a read-only
SQLite audit and a deterministic score-control experiment. No production behavior or data changed.
This is not a fresh dependency/security audit, Windows validation, performance benchmark or external
market/competitor study. Previous local test success does not establish classifier precision or demand.

Snapshot of canonical offers on 2026-11-02:

| Indicator | Observed |
| --- | ---: |
| Offers | 8,385 |
| Active | 7,969 |
| Missing/short description, fewer than 200 trimmed characters | 38 |
| Neither salary bound published/stored | 5,271 |
| Missing location text | 83 |
| Publication state unknown / open / closed | 7,516 / 823 / 46 |
| Jobs without a `job_sources` appearance | 51 |
| Such jobs with an observed URL linked to another job | 51 |
| Active jobs without a source appearance | 0 |
| Ingestion runs with only the query identity `batch` | 5,883 |
| Historical observations | 104,995 |
| Distinct content hashes in those observations | 9,440 |

Source appearance counts overlap and do not measure independent vacancies. The latest stored sightings
were Nov 2 for Computrabajo/Indeed/LinkedIn, and Oct 31 for Bumeran/Empleos Peru. This is evidence of uneven
freshness in this installation, not proof that a portal was unavailable. Two appearances use source `t`;
review these as possible old test residue without automatically deleting offers or personal state.

## Ranked weaknesses

### 1. Fit communicates more certainty than its inputs support

`scoring.py` assigns education a constant 70. Every saved `education_score` was 70 in this snapshot.
Skill matching counts presence: basic and advanced both count as a full detected match. A controlled
SQL-only case produced skill score 100 and total 84.5 for both basic and advanced SQL. The `LEVELS`
numeric mapping is used only to test whether a declared skill is above zero.

Seniority rewards a fixed list of junior titles, rather than comparing actual requirements with the
person's experience. Missing skills produce a neutral 50; absence of evidence is not measured coverage.
The larger danger is misplaced confidence in a high score, not failure to execute the weighted formula.
CV proximity has stronger evidence logic than the map score, so two fit systems can imply different things.

Next: extract explicit academic alternatives, required years, mandatory versus desirable conditions and
skill-level evidence. Separate occupational match, personal preferences, proven eligibility and data
coverage. Show satisfied / missing / uncertain requirements and a small set of explained priorities;
do not interpret a weighted score as a probability of admission or hiring. Reuse the good CV evidence
logic where appropriate instead of building another independent qualification engine.

Gate: paired tests must distinguish basic from demonstrated advanced requirements when the posting
states a level, real experience from missing experience, and compatible from conflicting mandatory
degrees. Unspecified levels/degrees remain unknown. Validate ordering against independently reviewed
offers; do not just tune weights until the author's preferred result is first.

### 2. Capture coverage and failure handling are not trustworthy enough

Scheduled capture and manual refresh still use different plans and coordination. Scheduled capture
uses the reference pack; place refresh also uses it and truncates an ordered plan. Being able to read
Systems does not prove equivalent discovery coverage for Systems. `ingestion_runs.query='batch'` loses
the query/market/family needed to evaluate coverage and useful yield.

`_run_with_timeout()` abandons a daemon thread without stopping its eventual ingestion writes. Separate
capture locks cannot prevent all overlap. `scheduler._capture()` marks `refresh_last_at` in `finally`,
including failures. Its local callback named `log` also shadows the module logger; the exception path
calls `.exception()` on that callback (or an unbound local if setup failed). This error-path issue is
confirmed by source inspection; it was not deliberately triggered against the live scheduler.

Next: one durable run/step coordinator, frozen requested markets and query families, fair budgets,
source coverage and explicit success/partial/failure states. Fetch workers must not write after their
run is cancelled. Compute and network outside DB write transactions; commit guarded bounded batches.
Fix the scheduler exception handler and separate last attempted from last successful capture.

Gate: a failed portal never looks like a successful market update; timed-out/cancelled steps cannot
write late; both markets receive their planned coverage; each run retains its actual query identity.

### 3. Offer identity and history need stronger invariants

Fingerprinting company/title/location can merge distinct reposts and split the same URL when titles
or location strings change. In ingestion, a new fingerprint can create a job, while source-URL conflict
updates only the old appearance timestamp/payload. The observed 51 inactive orphan jobs have their
observed URLs attached to another job, consistent with this path. This does not prove every historical
duplicate has the same cause; classify cases before repairing them.

Next: resolve stable portal identity/source URL before fingerprint-based fallback. Track appearances,
republications and content revisions explicitly. Add invariants preventing new canonical jobs without
a source appearance and observations associated with conflicting source identities. Preview existing
conflicts, preserve all old IDs and personal tracking, and record explicit canonical links rather than
deleting jobs or silently merging application histories.

Canonical descriptions are still overwritten on duplicate refresh, and observation snapshots lack full
old text. A partial card can replace richer detail; old text cannot be reconstructed from a content hash.
Retain changed input revisions prospectively and preserve the best supported source sections.

Gate: changed titles on the same source offer, repeated URLs, changed locations, partial details and
genuine republications all have regression cases. Historical metrics distinguish repeated sightings
from new opportunities and classifier changes from actual changes in postings.

### 4. Availability and classification quality remain largely unmeasured

The recent correction and scoped-agent tests are valuable regressions. They are not a held-out estimate
of occupational or academic classification quality. Most offers have unknown availability. HTTP success
without a closure phrase is still treated as open by the liveness checker, and one source URL stands in
for an offer that may have several sources. Missing salary is normal publishing behavior; do not fill it
with invented values or imply salary statistics describe every vacancy.

Next: a labelled, stratified corpus and per-error-family precision/recall/uncertainty report; a small
review queue with original spans; source-level verification with explicit evidence and freshness.
Keep unknown states and historical offers. Prioritize checks for visible/saved/soon-to-apply offers.

Gate: tooling distinguishes employer prose, actual duties, ERP use, functional implementation, physical
trades and genuine bridges. No claim of academic acceptance without requirements evidence. Source
blocks and generic landing pages never establish a vacancy's availability.

### 5. Distribution and recovery lag feature breadth

Known issues document no clean Windows VM validation, no peer pilot, unsigned installer, no formal
schema versioning and no restore/export UI. CI/release files build and smoke-test the Windows app, but
that is different from a human installation/upgrade/recovery trial on a clean machine. Source docs
describe SQL/runtime additive changes, not a fully versioned migration chain.

Next: a reproducible release candidate, numbered migrations, verified restore including the factual
CV/photo/targets outside SQLite, and a clean-machine setup trial. Test with 3–5 intended peers before
changing the product promise or expanding promotion. A small peer trial does not prove market fit,
but it can reveal installation and workflow failures that author-only use misses.

Gate: a peer can install, configure capture, review relevant offers and produce one truthful application
without the author operating the machine. Backup restoration is tested against actual application state.

### 6. Maintenance and product direction are fragmenting

The roadmap is dated Oct 14 and emphasizes a CV-first Windows release, while recent work emphasizes
dual-market intelligence. It also says scoring needs no improvement, contradicted by the score control.
Numerous source/doc changes remain uncommitted in this workspace; they need a reviewable release baseline.
`RadarClient.tsx` exceeds 1,000 lines and `tools.py` 900, increasing coupling, but size alone is not a bug.

Next: update a single roadmap/status ledger after deciding the next release outcome. Consolidate the
existing design/audit documents as dated references. Extract coherent UI state/data hooks and tool
families while fixing the workflows they own; avoid a whole-project rewrite or new infrastructure
without a measured problem. Keep SQLite and the generic pack boundary.

The agent now has scoped reads; remaining gaps include legacy score provenance and historical scope.
Review confirmed-write contracts so the approved name/arguments/version are bound to a server-held
proposal; the current confirmation endpoint accepts a client-supplied tool name and arguments. This
is a contract-hardening recommendation, not a demonstrated external exploit or complete security audit.

## Recommended next release

Outcome: an Industrial candidate exploring functional systems, BI and process automation can trust a
short list and understand eligibility, missing evidence and the next action. Mature these two markets
before adding more packs. Continue genuine specialist Systems coverage, but distinguish it from the
author's realistic transition paths and preferences.

1. **Stabilization:** capture failure handling, source identity invariants, query provenance and a
   tagged/reviewed baseline. Preview historical conflicts before any repair.
2. **Decision quality:** requirement extraction, honest coverage, labelled evaluation and an explained
   shortlist. Consolidate map fit versus CV proximity without inventing academic acceptance.
3. **Evidence and recovery:** changed-content revisions, source-level lifecycle, versioned migrations
   and restore validation. Preserve original job IDs, personal state and old observations.
4. **Independent use:** 3–5 peer sessions and one complete discovery-to-application journey. Keep CV
   Studio stable; improve only the steps that actually prevent completion.

Success measures: time to find suitable opportunities, reviewed shortlist relevance, mandatory-condition
errors, stale/closed recommendations, capture coverage, time to a truthful CV/application package, and
unaided completion. Interview/application outcomes are useful longitudinal evidence, not attributable
proof of product impact. Offer totals, tool counts and feature counts are not the primary success metric.

After those gates, consider a compact weekly change brief: new suitable roles, recurring requirements,
what changed in saved targets and one evidence-building action. Build it from versioned facts rather
than generating generic career advice. Broader monetization or hosted multi-user work needs independent
validation and is outside this technical review.
