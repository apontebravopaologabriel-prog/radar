# Known issues in 1.0.2

Honest list of what is not done or not verified. The release plan in [docs/roadmap.md](docs/roadmap.md) had more gates
than this version meets; they are listed here so nobody finds out the hard way.

## Not verified
- **The Windows installer has not been tested in a clean Windows VM.** CI builds it and runs a smoke test, but a first
  install, upgrade and uninstall on a machine without Python or Node were not exercised by a person.
- **No peer pilot.** Radar has been used by its author only; demand beyond one user is unproven.
- **The installer is unsigned** (no code-signing certificate), so Windows SmartScreen will warn.

## Missing from the 1.0 plan
- Schema upgrades rely on additive runtime migrations tracked via `PRAGMA user_version` (`SCHEMA_VERSION` in `src/radar/db/database.py`); there is no downgrade path. Back up (`radar` maintenance → backup, or Ajustes → Respaldo local de datos) before major updates.
- Computrabajo now defaults to native Python HTTP (`sources/computrabajo_native.py`), HTML request compatibility was corrected on 2026-11-09 (live HTTP 200 after the original headers returned 403); future HTTP 403/challenges remain explicit source failures; legacy MCP via Node.js (`npx`) remains an opt-in fallback.
- Local CV import from PDF/DOCX (`cv_import.py`) handles standard text layouts conservatively (no OCR for scanned PDFs; complex layouts may require manual review before confirmation).
- First-run setup allows choosing a market, importing a CV and triggering capture, though full interactive validation on a clean Windows VM is still pending.
- Two main career packs ship (Industrial Engineering, Systems/Software), plus Mechanical Engineering as an experimental pack.
- One-click database backup is available in Ajustes (`POST /api/system/backup`), while full restore and bulk data export are still CLI/manual operations.
- The map was verified to build and load with MapLibre 6, but not on every GPU/browser; report a blank map if you see one.

## Behavior to know
- Indeed and LinkedIn are read with a scraper (JobSpy); portal terms may forbid it. See [docs/data-sources.md](docs/data-sources.md).
- Outside Lima, offer location is the city centroid; coordinates are approximate and inferred per request.
- The in-process scheduler only runs while Radar is open.
- The mobile PWA (`/m`) is experimental and frozen; chat job links there open only the portal link.
- The agent can be wrong or be misled by text inside a posting. Writes always ask first; verify figures that matter.
- Profile and the offers the agent reads are sent to the LLM provider you choose.
