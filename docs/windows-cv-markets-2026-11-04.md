# Windows startup, CV onboarding and focused markets — 2026-11-04

## Implemented scope

Industrial and Systems remain the main markets. Mechanical Engineering is a third, explicitly experimental
pack, with contextual gates for mechanical maintenance/reliability, design/simulation, manufacturing,
thermal systems and mechanical projects. Technical purchasing is adjacent. Tool mentions and a degree
requirement do not make an unrelated job mechanical. The main-market capture option excludes experimental
packs; a user can explicitly capture Mechanical. No other careers were added.

A new local CV setup replaces the long skill questionnaire. The existing first-run popup now offers PDF
or DOCX import, reviewable name/contact/studies/experience, optional manual entry, persistent draft save,
confirmation and immediate selected-career capture. Settings links reopen setup and the optional three-tip
guide. Existing users do not need to repeat setup.

CV preview writes no factual profile. Confirmation validates and merges history, backs up the CV, updates
SQL with a version snapshot and restores the prior file if the SQL transaction fails. Reimport preserves
unmentioned confirmed facts and avoids identical history entries. Detected tools remain unlevelled; no
advanced competence or qualification is inferred. Files are parsed locally without LLM calls or retained
original uploads. The resumable draft includes extracted text and stays in local SQLite until confirmation.

PDF limits: 8 MB, 20 pages and 60,000 extracted characters. DOCX also bounds archive member count and expanded
size and reads document text without executing macros/external relationships. Scans, encrypted/broken PDFs
and legacy DOC are reported, not silently treated as empty profiles. Extraction is conservative: headings,
explicit degrees, delimited/labeled roles and explicit dates work best. Other layouts need user correction;
this is not a claim of Bumeran-equivalent parsing quality or OCR support.

## Windows and sources

Computrabajo now defaults to native Python public HTTP search/detail; a clean installation needs neither
Node nor npm for it. HTTP errors/challenge pages are source failures, not a successfully empty market.
Details preserve card identity, public URL and original publication date. Only public GETs are implemented.
The legacy MCP path remains opt-in through `RADAR_COMPUTRABAJO_TRANSPORT=mcp` or an explicit command; its
reader now uses a portable queue/thread, bounded messages/waits and response-ID correlation.

The initial experiment to bundle Node was abandoned after the dependency audit revealed vulnerable SDK
code embedded in the upstream distribution; changing npm transitive versions would not repair that bundle.
No Node adapter or its npm dependencies are shipped by this change.

A minimal live native query on this host received HTTP 403. That source is unavailable in that observation;
no bypass was attempted. Other sources remain isolated and can continue. Fixture tests establish extraction
and error semantics, not live portal availability or comprehensive source compatibility.

Desktop renderer initialization failure now logs to `desktop.log` and opens the default browser. Uvicorn
uses the configured file logger rather than assuming packaged Windows executables have console streams.
PyInstaller explicitly collects curl_cffi data/binaries for updated JobSpy; frozen smoke testing also opens
and closes its HTTP session without making network requests. Windows native WebView2/installer interaction
and the new frozen Windows build still require execution on a Windows runner/machine.

Application updates are separate from offer capture. The UI checks the fixed official GitHub release API
in the background, with bounded waits and a daily in-memory cache. A newer stable semantic version produces
a dismissible notice linking to the fixed release page. Offline checks do not prevent startup. It does not
silently install executables. The public application version remains 1.0.2 until a separately reviewed release;
a new feature in the working tree does not update anyone's old installer by itself.

## Geography and score consistency

`places_lima.json` is a shared, versioned source for 50 Lima/Callao polygon keys, aliases, approximate
centroids and stable application IDs. The frontend and backend consume the same catalog. Missing aliases,
Mi Perú, Lurigancho/Chosica/Huachipa and Cercado/Lima polygon joins are reconciled. Bare “San Martín, Perú”
resolves at department precision instead of inventing a San Martín de Porres district location.

The desktop explicitly sends `geo_scope=lima_callao`; API job pagination and competency summaries apply
that same scope. The agent inherits it. Unlocated offers and other cities remain in the database and
can be inspected by unscoped APIs. Centroids are approximate, not office addresses or commute times.

Scoring version `v2.1-evidence` reads the reference market's independent area/skill projection. Changing
reference career no longer scores old canonical Industrial categories as though they were Mechanical.
Reference recommendations use that projection's relevance as well. A different exploratory market still
does not invent a new personal score. Old algorithm fingerprints become stale until recomputed.

## Dependencies and checks

The initial Python audit reported vulnerabilities in eight installed packages, including Pillow and an
old JobSpy-imposed markdownify restriction. Pillow 13, JobSpy 1.4.1 and patched dependencies were installed
and compatible minimums updated. Pytest 9 is used. A fresh audit reported no known vulnerabilities, and
`pip check` found no broken requirements. Frontend production npm audit reported none. This is a dated
scanner result, not a guarantee about every future dependency version or the old published executable.
CI audits now include optional JobSpy and run the frontend audit even if the Python audit fails.

Validation includes the Python suite, frontend lint/tests/build, empty-data desktop smoke, actual local MCP
pipe round trips and timeouts, real PDF/DOCX fixtures, upload/confirm API separation, rollback, reimport,
unknown proficiency, location scope before pagination and Mechanical negative/overlap cases. A complete
interactive clean-Windows install/capture/upgrade remains the release gate. No new Windows release was
published from this working tree.

## Local deployment verification

The November 4 deployment created a consistent backup before rebuilding projections and scores. After an
interrupted foreground recalculation, a detached worker recovered the API and completed 8,530 active
canonical scores. Hashes of all 9,158 offers, sources, observations, existing areas/skills, profile, declared
levels, favorites, hidden state and application history matched the pre-deployment backup; the CV file
was unchanged. SQLite integrity passed. Details are in the local gitignored
`backups/cv-windows-markets-20261104.json`. Capture was paused during maintenance and resumed afterward.

397 Python tests, 12 frontend tests, lint/build, `pip check`, desktop smoke and Python/frontend production
audits passed. Two existing TestClient dependency deprecations remain. The new setup was visually reviewed
on an isolated empty database, and its Settings links verified on the actual installation. Live scoped
API reads at verification returned Industrial 714, Systems 364 and Mechanical 8 offers in Lima/Callao in
the last seven days. These counts describe the already collected corpus; they are not equivalent coverage
measurements and Mechanical has not received a dedicated full capture in this validation.
