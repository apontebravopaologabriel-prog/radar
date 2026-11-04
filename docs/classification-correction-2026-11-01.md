# Contextual classification correction — 2026-11-01

Implemented classifier version: `2026-11-01.1`. This is the first correction batch from the
[ingestion/classification plan](design-market-ingestion-classification.md).

## Changed behavior

- Systems areas require a qualifying role title or contextual duties. Tool names in requirements,
  explicit employer introductions and benefits cannot establish occupational membership.
- Separate maritime containers from software deployment; building infrastructure from IT/cloud;
  physical-security vulnerabilities from cybersecurity; curriculum development from software;
  transport scheduling from programming; AWS welding standards from cloud work; integrated quality
  management systems from IT systems.
- Functional ERP requires functional work or a role title; entering transactions alone does not qualify.
  BI work retains related-market coverage without treating every report or spreadsheet as software.
- Primary occupation anchors relevance. Secondary areas and personal target titles cannot promote
  unrelated jobs to core. Legacy Industrial area aliases belong to their own pack.
- Industrial retains production supervision and planning roles. Reviewed clinical laboratory and
  hands-on maintenance declarations no longer become engineering roles from incidental keywords.
- Desktop defaults to all areas, core and adjacent roles, with the existing seven-day age filter.
  Opening, switching or clearing a market resets optional filters. Outside-market rows require an
  explicit advanced selection; they are retained in the database.
- New ingestion and backfill share the same rules. Engine and complete-pack hashes invalidate stale
  results. Reclassification backs up first and updates canonical areas/skills/relevance and installed
  market projections in guarded batches, preserving original inputs and personal state.

## Verification and preview

333 Python tests pass, including the added diagnostic, English-language, bridge, negative-role,
version-invalidation, full-market-scope and backup/personal-state regressions. The frontend's 12 tests,
lint and static production build pass. Existing Python dependency deprecation warnings remain.
All tests now default to a temporary database to protect real local data.

A read-only preview used the pre-change backup and current rules on 5,018 active, canonical, non-hidden
offers within a 30-day publication lookback ending 2026-11-01. This is broader than the UI's age filter.

| Systems transition | Offers |
| --- | ---: |
| Core to outside | 166 |
| Adjacent to outside | 204 |
| Core to adjacent | 115 |
| Outside to core | 69 |
| Outside to adjacent | 64 |
| Adjacent to core | 10 |

These are mechanical classification transitions, not 370 independently labelled errors or a measured
accuracy percentage. Representative original false positives and positive controls were reviewed.
The local preview is under the gitignored `backups/classification-preview-final-20261101.json`;
the deployment result is recorded separately in `backups/classification-applied-20261101.json`.

Production retained 8,341 offers and rebuilt 16,682 market projections. The closing Industrial check
also rejects 183 offers with explicit physical-trade titles, including air-conditioning, refrigeration
and mechanical-maintenance technicians. Personal state and original offer inputs were preserved;
SQLite integrity checks passed. These title exclusions do not exclude IT support technicians from Systems.

## Remaining scope

The section parser is deterministic and cannot resolve every free-form description. Degree mentions
still do not guarantee that an employer accepts a person's qualifications. Full structured academic
eligibility, a manually labelled held-out corpus and unified scheduled/manual capture coordination
remain separate phases of the design plan. This correction does not claim those phases are complete.
