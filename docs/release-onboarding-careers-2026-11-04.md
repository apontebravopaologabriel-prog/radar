# Windows release readiness, CV onboarding and career expansion — 2026-11-04

## Decision

Ship a focused Lima/Callao beta after fixing first-run capture on Windows, geographic identity and the
CV-assisted setup. Start with the two current markets. Add Accounting/Administration next after reviewing
real offers. Psychology and further engineering specializations need separate validated occupational rules.
Do not turn the current selector into a promise that every degree is supported.

This is an analysis and proposed implementation plan. No installer, runtime behavior, personal profile or
production database was changed in this review. Windows binaries were not executed interactively here.
Local uncommitted changes were preserved; their successful Linux checks do not certify a Windows release.

## Evidence checked

- Read README, architecture, operations, troubleshooting, packaging, careers, installer/spec/workflows,
  desktop startup, onboarding, profile persistence, source transport, market projections and map/location code.
- GitHub release `v1.0.2` was published on October 14, 2026 and includes `Radar-Setup-1.0.2.exe`
  (87,796,259 bytes) plus checksums. It predates the current local market/scoring corrections.
- The October 21 packaging PR build passed frontend export, Python tests, executable build, packaged smoke
  test and installer build. Signing was skipped. The smoke test checks HTTP, HTML, MCP registry and PDF
  rendering; it does not open a real desktop window, install on a clean PC or exercise network capture.
- The October 28 CI Windows/Python 3.12 job passed for commit `2b686b7`. Its informational dependency audit
  failed and did not block overall CI. That is a historical audit result, not a fresh vulnerability assessment.
- No application-update checker, CV document importer or guided map tour exists in current source searches.
  `FirstRun.tsx` already opens setup in a modal, but `Onboarding.tsx` asks manually for name, education,
  locations, modes, areas and every skill level. Its dismissal is stored per browser, not as resumable setup.

Remote evidence:

- [Published release](https://github.com/apontebravopaologabriel-prog/radar/releases/tag/v1.0.2)
- [Successful packaging job](https://github.com/apontebravopaologabriel-prog/radar/actions/runs/39596916630)
- [Windows tests](https://github.com/apontebravopaologabriel-prog/radar/actions/runs/40723911577/job/122941909537)
- [Informational audit failure](https://github.com/apontebravopaologabriel-prog/radar/actions/runs/40723911577/job/122941909452)

## Windows gaps before wider distribution

| Finding | Consequence | Proposed correction |
| --- | --- | --- |
| Computrabajo launches `npx`; installer bundles neither Node nor that MCP adapter | A clean non-developer PC cannot use this source as advertised | Prefer a reviewed native connector; otherwise bundle a pinned runtime/adapter and provide explicit source availability diagnostics |
| `_rpc` registers subprocess stdout with `selectors.DefaultSelector` | Python Windows selectors support sockets, not pipes; the transport is incompatible even with Node installed | Use a portable subprocess reader/queue with bounded waits, or a tested async subprocess transport; correlate response IDs and shut down readers/processes on timeout |
| `open_window` falls back only on import failure | A renderer/WebView2 initialization error can terminate startup without opening the browser | Check WebView2, handle renderer failure and offer browser fallback with a clear boot log |
| Installer does not check WebView2 | Availability is assumed | Detect runtime at install/startup; provide the official Evergreen installation route when missing |
| No new-version check | Installed users will keep the downloaded version until reinstalling manually | Add a nonblocking release notification and explicit installer download action |
| Scheduled capture runs in the app | Closing Radar stops the packaged scheduler | Describe this accurately; first capture should be immediate after setup, not dependent on startup/autostart |
| No interactive clean-machine upgrade gate | A green build does not establish successful first-run use | Verify install, capture, file upload, map, PDF/Word, upgrade and retained personal data on Windows |

Python documents the pipe limitation in [selectors](https://docs.python.org/3/library/selectors.html).
Microsoft recommends checking and distributing the runtime in its
[WebView2 distribution guide](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution).

The current installer has a stable AppId, installs per user and keeps the separate data folder. These are
useful foundations for an upgrade, but upgrades with running processes, schema changes and WebView2 need
an actual test. Signing was skipped in the checked workflows; do not describe the binary as signed.

### Separate three kinds of update

1. **Application:** check a fixed repository's published stable release, compare semantic versions,
   skip drafts/prereleases, cache the result and never block offline startup. Show one dismissible
   "Hay una nueva versión" notice with release notes and download. First release can open the official
   release page; silent self-installation is unnecessary. New installations already on the latest version
   should see no update prompt. Later installer upgrades back up data and validate migrations.
2. **Offers:** "Actualizar ofertas" runs selected markets in Lima and shows per-source progress,
   partial failure and useful counts. It is unrelated to installing a new application version.
3. **Classification rules:** initially ship versioned packs with the app. A changed rules hash triggers
   bounded background projection rebuilding with progress; it must not freeze the first map request.

Release discovery can use the documented
[GitHub Releases API](https://docs.github.com/en/rest/releases/releases#get-the-latest-release).
Use fixed trusted destinations, timeouts and version comparison rather than executing remote commands.
If automatic installer download is added later, verify the expected release artifact/integrity and
publisher signature where available, and handle locked processes and rollback explicitly.

## Minimal first-run experience

Use the existing modal entry point, with a draft that resumes and can be reopened in Settings. Save setup
state in SQLite so a browser-storage reset does not repeat or lose it. Manual entry remains available.

```text
Choose career, Lima/Callao already selected
  -> Drop CV (.pdf or .docx), or continue without CV
  -> Review prefilled identity, education, dated experience and detected tools
  -> Confirm profile and start first capture
  -> Open map with all areas of that market, last seven days
```

The user can reach the map quickly with career plus a confirmed draft. Ask only for missing essential
information. District and desired work mode are optional refinements; they are search preferences and
cannot be reliably inferred from a CV. Do not force a long skill-level questionnaire or an API key.
A CV may contain several degrees: the selected search career must not rewrite the factual qualifications.

### Import pipeline

- Accept text PDFs and DOCX first. Existing `pypdfium2` can extract PDF text; DOCX can be parsed using a
  reviewed library or bounded ZIP/XML reader. Legacy `.doc`, encrypted PDFs and scanned pages need explicit
  handling. OCR is a later feature; an image-only CV must show an actionable result instead of an empty profile.
- Extract to a draft only. Store per-field text/page evidence and a categorical review state, not invented
  numerical confidence. Parse contacts and dates, recognize section headings and known program/tool aliases.
  Layout and prose parsing are less certain; two-column PDFs, DOCX tables and overlapping work need fixtures.
- A tool mention creates a detected tool, not an advanced skill level. Academic status and employment dates
  require explicit evidence. Present unrecognized or ambiguous values for correction. Do not infer personality,
  ability, professional licensing, salary, exact address or degree completion.
- Keep baseline extraction local and functional without the chat agent. Optional model-assisted interpretation
  requires explicit opt-in before sending CV text to a provider, and still returns a reviewable draft.
- Apply only after confirmation through a unified profile import operation. The current manual onboarding
  saves the SQL profile, while factual CV history lives in `cv_master.json`; the importer must populate both
  consistently. Validate all fields, back up, write atomically where possible and restore the file if DB work
  fails. Reuse the rollback pattern in `profile_edit.py`; do not scatter writes across UI steps.
- Limit file size, expanded DOCX size, page count, parsing time and accepted formats. Import text only; do not
  run macros or follow external document relationships. Do not log full CV text or include it in telemetry.
- Preserve uploaded originals only if the user chooses to keep them; field provenance must survive acceptance.
  Reimport offers a diff and never silently erases previously confirmed facts.

Suggested components: `cv_import.py` for bounded extraction and drafts, explicit preview/apply endpoints
in `api_me.py`, and a compact setup flow reused by desktop and mobile. Do not expose the importer to chat
unless a later explicit requirement justifies it.

### Usage popups

After the first useful results, show at most three short, optional tips: select a district; use star/detail;
record an application. Persist a tutorial version and offer "Omitir" and "Volver a ver". Show an empty-state
explanation and capture progress instead of teaching map interactions before any offers exist. Keep full
instructions in Help and use the tour only for visible actions.

## Career expansion without weakening matching

The scalable unit is an occupational market, not one copied rules file per academic degree. Maintain a
small career catalog that maps degree/program aliases to one or more supported markets. A market owns
its roles, areas, evidence rules, exclusions, skills, discovery queries and validation cases.

Keep these axes distinct:

- **Person:** confirmed education, dates, experience and declared levels.
- **Market:** what the job does (for example accounting, business analytics, software, clinical care).
- **Academic requirement:** which degrees/statuses the posting explicitly accepts, rejects or leaves unclear.
- **Place:** region, province/city, district and location precision.

An offer can belong to multiple markets without duplication. A psychologist's organizational recruiting
role can share HR/business functions; a clinical psychologist role needs its own occupational and explicit
qualification rules. An engineer merely using SAP is not automatically a software professional. An
industrial graduate is not automatically an accountant because both use Excel.

### Suggested rollout

| Stage | Markets | Reason and gate |
| --- | --- | --- |
| First public beta | Existing Industrial and Systems/Software | Finish setup, capture and location correctness before promising more careers |
| Next | Accounting and Administration/business roles | Shared analytical tooling, but distinguish taxation, accounting, finance, commercial work and unrelated sales |
| Then | Organizational Psychology / HR; separately clinical/educational tracks if supported | Separate recruiting/training from patient care and education; preserve explicit degree/licensing requirements |
| Later | Civil, mechanical/electrical and other engineering markets one at a time | Maintenance, physical infrastructure and software are not interchangeable occupational contexts |

Do not expose a selectable unsupported career as if it had validated coverage. An unsupported degree can
be recorded factually while the user explicitly explores a supported market, with that limitation stated.

The engine already supports JSON packs and multiple independent projections. Expansion still requires:

- Remove two-market assumptions in `RefreshPanel.tsx`, `RefreshRequest.market_ids` (currently max 2), browser
  defaults and capture settings. Populate selectors from the catalog, with groups/search as needed.
- Keep a simple single Market control. On switching, retain all areas and seven days by default. Offer
  detailed academic fit as an optional refinement; incomplete degree text must not silently remove offers.
- Split broad discovery from precise tagging. Preserve valid fetched offers; assign occupational relevance
  plus academic evidence instead of discarding everything that lacks an exact degree phrase.
- Review title, duties and qualification evidence, not just single keyword matches. Avoid synonym duplication
  across packs through shared alias/rule resources and market-specific exceptions.
- Label a representative sample per new market, including overlapping roles, unrelated roles and sparse text.
  Start with 50–100 review cases as a development gate, not a precision guarantee; retain a held-out set and
  measure false acceptance, false rejection, uncertain share and retrieval coverage separately.

Adding a selector is low complexity. Reliable CV extraction and first-run setup are medium complexity.
Validated multi-career filtering and clean-machine Windows release behavior are the larger work. An initial
CV flow should deliberately exclude OCR and arbitrary Word formats; those materially expand scope.

## Geography: current behavior and verified gaps

The backend can resolve cities and departments outside Lima; scheduled capture can request extra cities.
The detailed polygon map and district catalog are Lima/Callao specific. A map centered on Lima does not
itself impose a geographic database filter; unselected district view can list offers from elsewhere.

Current resolution: named city outside Lima -> Lima district alias -> department -> explicit Lima center.
Bare "Perú" is unlocated. If a generic Lima field exists, title and explicit workplace-description clauses
can refine it to a district. Coordinates are centroids, not office addresses. The radius is approximate
straight-line distance, not a commute estimate or guaranteed job-site distance.

A source-level comparison on November 4 found 50 polygon features and 39 unique resolved district labels.
Fourteen polygon labels have no exact backend label and three backend labels have no exact polygon label;
these are different forms of mismatch, not 14 proven missing official districts. Examples include absent
Ancón, Cieneguilla and Bellavista aliases; Lima vs Cercado de Lima; Lurigancho vs Lurigancho-Chosica; and
`Mi Peraz` in the stored geometry label. The frontend normalizes Huachipa to `lurigancho`, but does not
currently normalize Lurigancho-Chosica the same way.

Executable resolution probes confirmed:

| Input | Current result | Assessment |
| --- | --- | --- |
| San Borja, Lima | San Borja / district | Expected |
| Miraflores, Arequipa | Arequipa / city | Avoids assigning the Lima district; loses Arequipa district detail |
| Bellavista, Callao | Callao / district | Wrongly collapses the more specific district |
| San Martín, Perú | San Martín de Porres / district | Ambiguous department/district alias is resolved too confidently |
| Lima | Lima / city | Must not imply an exact district |
| Perú | No point | Expected |

Correction: one versioned place catalog with stable identifiers (prefer administrative codes where
available), parent city/province/department and aliases. Join polygons, centroids and offers by identifier,
not display name. Keep area/market fields independent. Make Lima/Callao an explicit API scope rather than
relying on initial map position or substring search. Place unknown-district Lima offers in a visible
"Lima, distrito por precisar" group; do not attribute them to the center district. Keep unlocated offers
separate. Use ambiguity rules and provenance, and audit all polygon/catalog mappings.

## Scalability and delivery order

SQLite per installation remains appropriate for the focused local product; changing database engines is
not a prerequisite to publishing. More installed users do not share one SQLite write lock. They do,
however, duplicate network searches against the same sources, which is the first distribution bottleneck.

Locally, ingestion currently computes projections for every installed pack inside its transaction, and
a first scoped read can backfill the entire history. Cost grows roughly with offers times markets, plus
source/query/city combinations. Use enabled markets, cached content/rules hashes, deferred classification
for unexplored markets, computations outside write locks and bounded jobs with visible progress. Avoid
capturing every career and every city by default. Measure before claiming user/offer capacity.

If usage later justifies a shared service, separate a shared public-offer distribution layer from local
CVs, keys, favorites and applications. Do not upload existing personal data implicitly. Shared distribution
needs its own source-access arrangements, scheduling, quality monitoring and synchronization design;
it is a later architecture choice, not a requirement for the first beta.

Implementation order and acceptance gates:

1. **Windows foundation:** portable Computrabajo transport/source diagnostics, WebView2 handling and boot
   logging; close the historical dependency-audit findings with a fresh audit. Validate a clean Windows PC
   without Python/Node and capture at least one working source with honest partial-failure status.
2. **CV setup:** draft import, review/confirm, resumable modal and first capture; verify PDF/DOCX layouts,
   no-text/encrypted files, cancellation, no-key use, rollback and preservation on reimport.
3. **Geographic correctness:** reconcile polygons/catalog IDs, explicit Lima/Callao API scope, unknown groups,
   approximate-distance text, and the ambiguous-place regression cases above.
4. **Release delivery:** build the exact reviewed revision, add new-version notice, validate install over an
   old profile, data retention, startup/close, offline startup and renderer fallback; publish as a beta.
5. **Adoption:** test onboarding with 5–10 new people, measure time to useful offers, import corrections and
   wrong-market/wrong-location reports, with explicit consent for any collected feedback.
6. **Expansion:** Accounting/Administration after reviewed cases; other domains after the same gates.
   Change cities one at a time after geographic identifiers and polygon providers are generalized.

The release gate is a successful complete first use on a clean Windows machine, not merely the number
of careers in a dropdown. Keep the roadmap small enough that real new users can reach useful offers.
