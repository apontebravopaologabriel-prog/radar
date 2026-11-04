# Evidence scoring correction — 2026-11-02

The former score assigned every education dimension 70, ignored factual education and dated experience,
and treated basic and advanced declared skills as equivalent. Version `v2.0-evidence` replaces these
bonuses with a conservative, deterministic evidence assessment shared with CV gaps.

## Behavior

- Compare named academic programs and the required minimum academic status. Alternatives within a clause
  are alternatives; mandatory clauses take precedence over desirable ones. Completed studies are no longer
  treated as ongoing by default. A technical title does not automatically establish a university degree.
- Read explicit years/months from role requirements, exclude employer-history statements, count unique
  dated months and clamp future end dates. Explicit specialization needs lexical evidence in roles,
  bullets or listed skills. “Similar positions” without a comparable specialization remains unknown.
- Compare stated tool levels with self-declared levels. Missing declarations remain unknown; explicitly
  declaring no knowledge differs from not declaring it. A generic tool match does not establish the
  advanced proficiency demanded by a posting. Certificates do not silently establish proficiency levels.
- Keep preference dimensions, but give unknown dimensions an interval rather than a neutral bonus.
  The displayed score is the supported lower bound; the upper bound represents unresolved points.
  Coverage is one minus the weighted unresolved interval. These are model points, not calibrated
  probabilities, measured ability or proof that an employer accepts the person.
- Store quotes, per-dimension status, levels, weights, academic/experience flags and input revisions in
  additive `job_scores.assessment`. Recompute outside write transactions and commit guarded 50-job batches.
  Concurrent content changes cannot overwrite a newer offer's score. CV/profile revisions invalidate
  prior recommendations; a saved CV with a failed score refresh reports the refresh failure explicitly.
- CVs and mobile Today display a range. CVs and the agent expose coverage. The learning simulator reuses
  requirement levels and distinguishes acquiring a basic tool from satisfying an advanced requirement.

Scores still use the reference career. Reading the Systems projection does not reinterpret the user's
factual education or invent a second personal score. Historical offers and personal application state
are not deleted or rewritten by scoring.

## Validation and limits

372 Python tests passed, including paired degree and skill-level cases, non-overlapping experience,
insufficient specialization, employer years, shared CV skill levels, score persistence and invalidation,
and a concurrent-content guard with computation outside a write transaction. Frontend lint, 12 tests
and static build passed. The Python run has two existing dependency deprecation warnings.

A real-data copy exercise recalculated 7,969 active canonical offers before applying the change.
Production recalculation updated the same 7,969 rows, with 63.0% mean evidence coverage. Hash comparison
preserved all 8,385 offers, source links, observations, derived areas/skills, profile, skill declarations,
favorites, hidden state, applications, application history and the factual CV file. SQLite integrity
passed. The API was restarted; `/radar`, Today and the learning simulator returned 200, and the agent's
fit explanation reported current evidence. Matching UI defaults returned Industrial 663 and Systems 181
offers for the last seven days. The browser CV view displayed ranges and coverage successfully. Full
production preservation and backup details are recorded in the local, gitignored
`backups/evidence-scoring-20261102.json`. This check establishes preservation and runtime behavior;
it does not establish classifier precision or validate ordering against human recruitment judgments.

The extractor is deliberately conservative: lexical specialization can miss synonyms, complex nested
requirements and alternatives. Unrecognized programs, implicit equivalence and ambiguous education
remain uncertain. “Afines” cannot establish actual employer acceptance. Follow-up should label an
independently reviewed sample of offers in both markets and measure false acceptance and false rejection,
then expand data aliases and grammar based on those cases. Do not tune weights merely to raise scores.
