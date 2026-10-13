# Roadmap and status

Updated 2026-10-13. Single source of status; completed designs are not kept as separate plans. The code is
**v0.9.0** (v0.8.0 was the base; the table below lists what landed after it).

## Direction

- **v1.0 is the first public release:** a Windows installer anyone can download, with the MCP server included so
  people can try Radar from external AI clients (Claude Desktop, Claude Code, Cursor, Gemini CLI).
- **Until 1.0 the work is improving and polishing what exists, plus several careers** (the tool must be useful beyond
  Industrial Engineering at launch). New product surface waits for 1.1+.
- **Mobile (`/m`) is frozen** and ships as experimental; it gets no new work before 1.0.
- Stays personal and local-first: one installation, one person, one database. Hosted multi-user is not planned.
- Non-goals: automatic applications, messages to companies, automating personal portal sessions, exporting a
  hypothetical CV, inventing competency levels without evidence, bypassing CAPTCHAs.

## Done since v0.8

| Area | What landed |
| --- | --- |
| Focus feature | **Automatic context summarization**: auto-compaction at a configurable % of the context window with a structured summary, verbatim tail, preference candidates, optional cheaper model ([design](design-auto-compaction.md)) |
| Security | Host/Origin guard (DNS rebinding), security headers, `umask 077` + `600/700` permissions, pinned Computrabajo version, desktop login screen, OS credential store for keys on Windows, pip/npm audit job, Dependabot |
| Portability | `radar.paths` (platformdirs), `radar refresh` (in-process capture replacing the bash script), pack-driven queries, in-process scheduler (no systemd needed), `radar-app` desktop entry, Windows in CI, native PDF writer (no LibreOffice) |
| Careers | Systems/Software pack (51 skills, 13 areas) replaces Accounting; `radar career validate/list`; classification regression samples per pack |
| MCP | "Conectar IA" (Settings, `radar mcp config/install`) for Claude Desktop, Cursor, Gemini CLI, Claude Code command |
| Packaging | PyInstaller spec (verified on Linux), Inno Setup script, release workflow with smoke test and optional signing, LICENSE, Spanish user guide |
| Docs | Rewritten in English without redundancy; versions and design docs |

## Remaining for v1.0 (ordered)

1. **First Windows build** through the release workflow and fixes it reveals ([packaging.md](packaging.md#not-verified-yet-needs-a-windows-machine)).
2. **Native Computrabajo adapter in Python** (no Node/`npx` on the user's machine); JobSpy (Indeed/LinkedIn) as an
   opt-in "advanced sources" switch because of portal terms.
3. **More careers** (the v1 promise): Administration, Marketing, Health (nursing) and Law as built-in packs, each passing
   `radar career validate` and 10+ sample titles; a pack picker with a preview of what a career classifies.
4. **First-run experience:** wizard (career, city, profile) → automatic first capture with progress → map never empty.
5. **Auto-compaction retention eval** in `scripts/agent_eval.py` and a "restore full history" action.
6. **Agent/UI polish:** split `RadarClient.tsx` (887 lines), frontend tests for the CVs view and filters, remove green
   accents, tidy `globals.css`; performance budget re-measured with 5 000 offers ([architecture.md](architecture.md#performance-budget)).
7. **Data quality:** companies without data (~140 offers), doubtful area classifications, share of `Otras` per pack.
8. **Release hygiene:** code-signing certificate, `CHANGELOG.md`, privacy statement shipped in the installer,
   README with screenshots and download link, bump to 1.0.0.

## v1.1: data you can trust

- Persist coordinates, district and precision at ingestion; controlled geocoding with cache.
- More sources through official APIs and public ATS feeds (Greenhouse, Lever, Ashby; aggregator APIs where terms allow).
- Classification quality gate in CI with per-pack accuracy on labeled samples.
- Server-side pagination, ETag cache and aggregated map points for large databases.

## v1.2: market intelligence

- Automatic weekly snapshots and comparative reports (what changed in demand, salaries, skills, companies).
- The chain skill → human competency → evidence → project, with the gap prioritized by evidence.
- Export of a market report (Markdown/PDF) per career and city.

## v1.3: the desktop workflow

- Pipeline (kanban) on desktop, notes and reminders per offer, saved searches, "new since last visit".
- Desktop notifications for matching new offers; compare offers side by side; command palette.
- TypeScript types generated from the OpenAPI schema.

## v1.4: agent maturity

- Agent evaluation suite in CI with a simulated provider (tool choice, injection resistance, compaction retention) plus
  the real-provider script before releases.
- Sub-agent delegation for heavy read-only analysis with a fresh context, model routing (cheap model for summaries and
  classification), cost estimation in money.
- Richer MCP surface (more resources and prompts); `docs/skills/radar/SKILL.md` stays generated.
- Onboarding by CV upload with line-by-line confirmation.

## v1.5: beyond one country

- Pack authoring tools and a public pack gallery; country/locale packs (geography, currencies, portals) and UI i18n.
- Source plugin interface (documented, sandboxed subprocess) so new portals ship outside the core.
- Auto-update channel; evaluate Tauri with a Python sidecar if an updater is wanted.
- National map (country → department → city) with licensed geometries.
- Optional: hosted multi-user, only if there is real demand.

## Cross-cutting rules

- Every release: `pytest`, `ruff`, `npm test`, `npm run build`, Windows smoke test, regenerated skill.
- Deterministic scoring and traceable classification never move into an LLM.
- Anything that writes asks the person first; the agent never applies or sends messages.

## Known limitations

- Outside Lima, location is the city centroid; a bare "Perú" search returns mostly Lima.
- The desktop map is Lima/Callao only; coordinates are inferred per request, not stored.
- The internal scheduler only runs while Radar is open.
- Keyword classification is weaker for careers with ambiguous vocabulary.
- The mobile UI was verified with screenshots and builds, not automated interaction tests.
