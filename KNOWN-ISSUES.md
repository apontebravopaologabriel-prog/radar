# Known issues in 1.0.1

Honest list of what is not done or not verified. The release plan in [docs/roadmap.md](docs/roadmap.md) had more gates
than this version meets; they are listed here so nobody finds out the hard way.

## Not verified
- **The Windows installer has not been tested in a clean Windows VM.** CI builds it and runs a smoke test, but a first
  install, upgrade and uninstall on a machine without Python or Node were not exercised by a person.
- **No peer pilot.** Radar has been used by its author only; demand beyond one user is unproven.
- **The installer is unsigned** (no code-signing certificate), so Windows SmartScreen will warn.

## Missing from the 1.0 plan
- No schema versioning or migrations: the database upgrades only through additive runtime changes. Back up
  (`radar` maintenance → backup) before updating.
- Computrabajo still needs Node.js (`npx`); there is no native adapter yet.
- No CV import from Word/PDF: `cv_master.json` is filled by hand or through the agent.
- No first-run wizard with an automatic first capture.
- Only two career packs ship (Industrial Engineering, Systems/Software), not three.
- Backup, restore and data export are not in the UI.
- The map was verified to build and load with MapLibre 6, but not on every GPU/browser; report a blank map if you see one.

## Behavior to know
- Indeed and LinkedIn are read with a scraper (JobSpy); portal terms may forbid it. See [docs/data-sources.md](docs/data-sources.md).
- Outside Lima, offer location is the city centroid; coordinates are approximate and inferred per request.
- The in-process scheduler only runs while Radar is open.
- The mobile PWA (`/m`) is experimental and frozen; chat job links there open only the portal link.
- The agent can be wrong or be misled by text inside a posting. Writes always ask first; verify figures that matter.
- Profile and the offers the agent reads are sent to the LLM provider you choose.
