# Roadmap and status

Updated 2026-10-14. Single source of status; completed designs are not kept as separate plans. The code is
**v1.0.2**, released by the author's decision **before** several of the gates below were met (no Windows VM validation, no
peer pilot, no schema migrations, no native Computrabajo adapter, no CV import, no code signing). Those items stay open and
are the plan for **1.0.x**; [KNOWN-ISSUES.md](../KNOWN-ISSUES.md) says so to users.

## Direction

- **v1.0 is a CV-first Windows release built around one real user (the author), then validated with 3–5 peers.** The
  hero feature is the CV: your own Word template, your photo, your exact experience, traceable line by line. Everything
  else in 1.0 exists so that someone who is not the author can install it and reach that CV.
- **Careers are not the 1.0 axis.** Ship three packs (Industrial Engineering, Systems/Software and one that looks
  nothing like them) to prove the engine is general; more careers wait for 1.5.
- **Mobile (`/m`) is frozen** and ships as experimental.
- **Local-first, one installation, one person.** Hosted multi-user is not planned.
- **Radar is the "career brain", not a mail or calendar client.** Persistent connectors (mail, calendar) belong in an
  agent runtime next to Radar (OpenClaw, Hermes, Claude Desktop...) that talks to Radar over MCP. Reading mail changes the
  current promise of not touching personal sessions, so it must be an explicit, separate, off-by-default decision.
- Non-goals: automatic applications, messages sent on the user's behalf, automating personal portal sessions,
  exporting a hypothetical CV, inventing experience or competency levels, bypassing CAPTCHAs.

## Priority order (what matters most for the author, highest first)

Ranked by value to a Lima student who sends CVs, then by what blocks everyone else. Effort: S = days, M = 1–2 weeks,
L = several weeks (one person, part time). The CV items are detailed in [design-cv-studio.md](design-cv-studio.md).

**Now: v1.0 core**

| # | Item | Why it ranks here | Effort |
| --- | --- | --- | --- |
| 1 | ~~CV Studio spike~~ **done:** `pypdfium2` renders a page in ~70 ms and has a 3.9 MB Windows wheel; the hit map comes from the PDF writer | Retired the one technical unknown | done |
| 2 | ~~Application packages~~ **done:** folder per application, professional filename, offer snapshot, archived versions, open folder, copy path, mark as sent. Postulaciones view **done** in 1.0.0 (tray tab ✓ and full view, undo) | Fixes "I lose track of PDFs per job" | mostly done |
| 3 | ~~CV document model + templates~~ **done** (two templates, photo, PDF exact, Word approximate). Pending: a template rebuilt from your current CV (needs your PDF or a screenshot) | The foundation of the editor and of "no Word in the loop" | mostly done |
| 4 | ~~CV Studio UI~~ **done** inside the CVs view (tab `Estudio`) | The "editor inside Radar" experience | done |
| 5 | ~~Agent panel in the Studio~~ **done:** suggestions, fact guard, accept/reject, four tools, pinned panel. Pending: real-provider evaluation of edit requests | Edit by asking, without ever inventing a fact | done |
| 6 | Installer validated in a Windows VM (`dockur/windows`) + first-run wizard with automatic first capture | Nothing else matters if a second person cannot get to a populated map | S–M |
| 7 | Schema versioning and migrations | A public database that cannot upgrade is a broken release | S |
| 8 | Native Computrabajo adapter | Removes the Node.js requirement on Windows | M |
| 9 | CV import from Word/PDF with line-by-line confirmation | Your master exists; peers need this before the pilot | M |

**Next: v1.0 hygiene (cheap, protects the release)**

| # | Item | Effort |
| --- | --- | --- |
| 10 | ~~`docs/data-sources.md` and the privacy statement~~ **done** in 1.0.0 (the installer still needs to show the privacy statement) | done |
| 11 | ~~`npm audit` high findings~~ (clean in 1.0.1), code signing, ~~CHANGELOG~~, `radar doctor`, ~~`KNOWN-ISSUES.md`~~ (changelog and known issues done) | S–M |
| 12 | Third career pack, picked with peers; all packs pass validation on 10+ labeled titles | M |
| 13 | Incremental classification (repair-data from ~2 min to seconds) and the compaction retention eval | M |
| 14 | Split `RadarClient.tsx` enough to stop being a risk; backup/restore and export in the UI | M |
| 15 | **Peer pilot gate:** 3–5 people, four weeks, publish only if some use it unprompted | calendar time |

**Then: v1.1–v1.2 (high personal value, after the release)**

| # | Item | Effort |
| --- | --- | --- |
| 16 | Commute stage 0: "Cómo llegar" link and your own door-to-door times; mobility profile (walk, bike, own vehicle, public transport) and fares you enter | S–M |
| 17 | Pipeline on desktop, reminders, `record_application_event`, `.ics` export, notifications | M |
| 18 | Saved searches and shareable view links; honest labels for estimates and stale sources | S–M |
| 19 | Cover-letter drafts and interview preparation (always marked draft); CV learning loop (which version got replies) | M |
| 20 | Commute feasibility spike, then a district matrix and a "≤ N minutes" filter | M–L |
| 21 | Persisted coordinates, public ATS sources, company enrichment | L |

**Later: v1.3+ (valuable, not urgent)**

Class-timetable compatibility and net value after transport (needs 16 and 20), reachable-area isochrones, market reports and
salary brief, connected agent with mail/calendar through OpenClaw/Hermes (spike first), local HTTP MCP transport, agent
evaluation in CI and sub-agents, pack gallery, UI i18n, source plugins, auto-update, national map, a second distribution path
(Pinokio).

**Deliberately not planned:** automatic applications, sending messages, scraping consumer transit apps, a 3D globe, hosted
multi-user, reading mail inside Radar, embedding another office suite's editor.

## Layers: what exists, what to improve, what to add

| Layer | Today | Improve now (before 1.0) | Add later |
| --- | --- | --- | --- |
| **Sources** | JobSpy (Indeed, LinkedIn) in-process; Computrabajo through Node (`npx`); CSV import | Native Python Computrabajo adapter; JobSpy as opt-in "advanced sources"; per-source health in the UI | Public ATS and official APIs (Greenhouse, Lever, Ashby...), source plugin interface |
| **Ingestion and classification** | Keyword packs, deterministic, with evidence; fingerprint dedupe; classify 18 ms/offer after the regex fix | Incremental classification (a content hash, so only new or changed offers are reprocessed); share of `Otras` per pack in CI | Offline LLM-assisted pack authoring (the LLM proposes terms, the rules decide), fuzzy cross-portal dedupe |
| **Scoring** | Six traceable weights, editable, breakdown shown | None needed for 1.0 | Suggest weights from your ★ and hidden offers (suggest only, never silent) |
| **Storage** | SQLite, additive runtime schema, no `user_id`, coordinates inferred per request | **Versioned migrations** (`schema_version` + runner: public users will hold databases that must upgrade), backup/restore UI, data export (JSON/CSV) | Persisted coordinates and precision, full-text search over offers, rename `industrial_areas` |
| **API and security** | Access key, Host/Origin guard, headers, private files, credential store, audit job | Fix `npm audit` high findings (Next.js, MapLibre, PostCSS); nonce-based CSP | Per-device sessions and token rotation, rate limits on chat |
| **Interface** | Desktop map, Analysis, CVs, settings; `RadarClient.tsx` is 887 lines; Spanish only | First-run wizard with automatic first capture; honest empty states; split `RadarClient` | i18n (Spanish/English), accessibility pass, saved searches, command palette |
| **Agent** | Optional chat, modes, memory, confirmed writes, auto-compaction | Retention eval for compaction; "restore full history" | Eval suite in CI with a simulated provider, sub-agent delegation, model routing, interview prep and cover-letter drafts (marked as drafts) |
| **MCP and integrations** | stdio server, one-click client setup, 58 tools | `record_application_event` (confirmed write) so an external agent can update the pipeline | Local streamable-HTTP transport with token; pairing guide for OpenClaw/Hermes; `.ics` export of interviews (a calendar with no integration); event hooks |
| **CVs** | Gap by code, plan, generic one-column DOCX + native PDF, no photo, no import | See v1.0: import, own template, photo, trace, versions, sent-CV log | Cover-letter draft, per-offer keyword coverage report, A/B of CV versions by outcome |
| **Distribution and operations** | Windows build and smoke test pass in CI; installer builds as an artifact; weekly capture verified on real data | Installer tested in a Windows VM (dockur/windows), code signing, CHANGELOG, privacy statement, crash log folder | Auto-update, optional tray/background mode |

## Done since v0.8

| Area | What landed |
| --- | --- |
| Focus feature | **Automatic context summarization** with a structured summary, verbatim tail and preference candidates ([design](design-auto-compaction.md)) |
| Security | Host/Origin guard, security headers, private files, pinned Computrabajo, desktop login, OS credential store, audit job, Dependabot, Pillow 12.3 (35 known vulnerabilities in 11.x) |
| Portability | `radar.paths`, `radar refresh` in Python (no bash), pack-driven queries, in-process scheduler, `radar-app`, Windows in CI, native PDF writer |
| Windows | Frozen app builds on `windows-latest` and passes the smoke test; installer script builds; release workflow |
| Careers | Systems/Software pack replaces Accounting; `radar career validate/list`; classification regression samples |
| MCP | "Conectar IA" (Settings, `radar mcp config/install`) for Claude Desktop, Cursor, Gemini CLI, Claude Code command |
| Performance | Classification 103 → ~18 ms per offer (compiled-pattern cache), `repair-data` 278 → 116 s and writes only what changed |
| Reliability | Local maintenance is never abandoned by a timeout (it left the database locked); capture log is unbuffered |
| UI | Rail and agent/settings buttons share geometry and hide together |
| Docs | English, no redundancy, versions, design docs, Spanish user guide |

## v1.0: your CV, installable (the plan)

Acceptance: you install it on Windows and, for a real offer, tailor your CV in the Studio with the agent beside it, export the PDF into
its own application folder and find it again later, **without opening Word, GenOffice or any other program**. A peer can do the same
without help.

**A. CV Studio (hero), all inside Radar** (design: [design-cv-studio.md](design-cv-studio.md))
1. **Application packages:** one folder per application (`2026-10-14 Empresa - Puesto`) with the CV, a cover-letter draft, a snapshot of
   the posting and a manifest; a professional upload filename (`CV Nombre - Puesto.pdf`); a Postulaciones view; "open folder",
   "copy path", "open posting"; **Radar never submits an application for you**.
2. **CV document with revisions** and Radar-native templates defined as data (one rebuilt from your current CV), with/without
   photo; **PDF is the exact and primary export**, Word is approximate and secondary.
3. **Editor inside Radar:** page canvas (the real PDF rendered), outline with include/omit/reorder and line trace, hand editing,
   undo/redo.
4. **Agent panel on the right:** ask for changes; each one arrives as a before/after suggestion to accept or reject. A
   **fact guard** written in code blocks any rewording that adds a number, date, organization or tool not in your master.
5. **Import** from Word/PDF into `cv_master.json` with line-by-line confirmation (Radar only reads the file).
6. **Versions per role** and a **sent-CV log** tied to the pipeline.
No GenOffice, LibreOffice or Word is required; they are optional external tools only.

**B. Make it installable by others**
7. First-run wizard (career, city, profile, CV import) followed by an automatic first capture with progress.
8. Native Computrabajo adapter; JobSpy behind an "advanced sources" switch.
9. Schema versioning and migrations; backup/restore and export in the UI.
10. Third career pack chosen with your peers; all packs pass `radar career validate` and 10+ labeled titles.

**C. Release hygiene**
- `docs/data-sources.md`: every source with its terms, rate limits and attribution, plus third-party notices (the legal side of a public release).
- `radar doctor` (environment and data checks without printing secrets) and a `KNOWN-ISSUES.md`.
11. Installer validated in a Windows VM; code-signing certificate; `CHANGELOG.md`; privacy statement in the installer.
12. `npm audit` high findings fixed; `RadarClient` split enough to stop being a risk; compaction retention eval.
13. **Peer pilot gate:** 3–5 people use it weekly for four weeks. Publish only if at least some of them star offers or
    generate a CV without being asked.

## v1.1: follow-up and pipeline

- Desktop pipeline (kanban), notes, reminders, "new since last visit", saved searches, desktop notifications.
- `record_application_event` tool and `.ics` export of interviews.
- Interview preparation per offer and cover-letter drafts (always marked draft, never sent).
- Ghost-job signal from the existing link checks.
- Shareable view links (filters, district, selected offer in the URL) and saved searches.
- Honest labels everywhere: estimates marked as estimates, stale or fallback sources flagged in answers and in the UI.
- **Commute, stage 0:** a "Cómo llegar" link in the offer detail (an external directions search from your home or
  university district at a chosen time, in the same spirit as the existing `⌖` link: no API, no stored third-party data) and
  a way to record your real door-to-door minutes per district pair, which becomes your private commute matrix.

## v1.2: data you can trust

- Persist coordinates, district and precision at ingestion; controlled geocoding with cache.
- Public ATS and official API sources; company enrichment (offers with no company data).
- Incremental classification, classification quality gate in CI with labeled samples per pack.
- Server-side pagination, ETag cache and aggregated map points for large databases.
- **Commute, stage 1 (starts with a 1–2 day feasibility spike):** compare three data routes for Lima before building
  anything: open transit data (GTFS from the transport authority or aggregators, if complete enough) with an open router on
  OpenStreetMap; a one-time batch of a commercial routes API (check its terms on storing results and its current price);
  and the user-supplied matrix from stage 0. Then a district-to-district matrix by time of day, a `commute` scoring
  dimension and a "≤ N minutes" filter replacing the straight-line radius as the main proximity signal. Always shown as an
  estimate with a range. Never scrape consumer transit apps (no public API, terms, fragile).
- **Mobility profile:** how you move (walk, bike, own car or motorbike, public transport, or a mix) decides which times are
  shown and which costs apply. Car, bike and walk times can come from OSM routing; the public OSRM servers allow fair interactive
  use only (not a bulk matrix), so use a self-hosted instance or a precomputed matrix, and keep OSM attribution. Routing has no
  live traffic: car times are free-flow until your own recorded times calibrate a peak-hour factor. For buses, the fare per
  mode is a value you enter (and can correct), used to estimate cost per trip and per month; Radar ships no fare table it
  cannot keep current.

## v1.3: market intelligence

- Automatic weekly snapshots and comparative reports; export of a market report per career and city.
- Skill → human competency → evidence → project chain with the gap prioritized by evidence.
- Salary brief for negotiation from your own accumulated history; CV-version outcome analytics.
- **Commute, stage 2:** reachable-in-N-minutes areas on the map (isochrones) instead of circles, several anchors (home and
  university), compatibility of an offer's schedule with your class timetable, and net value (salary minus estimated
  transport cost).

## v1.4: connected agent

- Local streamable-HTTP MCP transport protected by the access token.
- Pairing guide and a small spike with OpenClaw/Hermes (confirm MCP client support and scheduling) so calendar and mail
  connectors live there; Radar receives only confirmed events.
- Agent evaluation suite in CI, sub-agent delegation, model routing, cost estimation in money.

## v1.5: beyond one career and one country

- Pack authoring tools and a public pack gallery; country/locale packs and UI i18n.
- Source plugin interface (sandboxed subprocess); auto-update channel; evaluate Tauri with a Python sidecar.
- A second distribution path through a one-click launcher such as Pinokio (cheap, no code signing, but an AI-hobbyist audience).
- Importable pack bundles with provenance and license manifest (the career-pack gallery).
- National map (country → department → city) with licensed geometries.

## Cross-cutting rules

- Every release: `pytest`, `ruff`, `npm test`, `npm run build`, Windows smoke test, regenerated skill.
- Deterministic scoring and traceable classification never move into an LLM.
- Anything that writes asks the person first; the agent never applies or sends messages on its own.
- A CV line must trace to a real line in `cv_master.json`; rephrasing, if ever added, is marked and needs approval.

## Known limitations

- Outside Lima, location is the city centroid; a bare "Perú" search returns mostly Lima.
- The desktop map is Lima/Callao only; coordinates are inferred per request, not stored.
- The internal scheduler only runs while Radar is open.
- `repair-data` still rescans every description (about two minutes on 6 000 offers) until classification is incremental.
- Proximity is straight-line distance, a weak proxy for Lima commutes (see the commute stages above).
- Keyword classification is weaker for careers with ambiguous vocabulary.
- Demand for Radar beyond its author is unproven; the peer pilot is the test.
