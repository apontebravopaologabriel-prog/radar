# Proposal: market analysis as Radar's primary value

Status: implemented. Scoped overview and drill-down, relative saved views, a compact global SQL workspace, secondary CV access through Settings, and tray alignment are shipped. CV functionality and data are preserved.

## Current findings

The map filter trigger grows with its count but used fixed reserved header space. It is now bottom-right and opens upward. Radar's popup reserves room for that trigger. The offer tray's detached border and left inset produce a visually independent box; moving it behind/over the navigation rail would create another collision.

The current CV interface already starts with offer preparation, but contains CV, Matrix and Data modes plus imported profile, history editing and Studio. For a user who does not use it, this is a second product to maintain. Local factual data can support personal comparisons, but is not a prerequisite for market analytics.

Analysis remains a global SQL workspace with presets, movable windows and physics. Saved SQL is not a saved map scope. Some queries use reference-market area/skill tables, and salary aggregates do not consistently separate currency or period. Better charts alone cannot repair these definitions.

## Recommended information architecture

Primary navigation: Map, Analysis, Processes. Keep saved offers in the existing tray. Move optional CV/profile access to Settings; retain Prepare CV only as a secondary offer-detail action if users still need it. Preserve profile, files, APIs and historical records; removing the underlying CV subsystem is a separate decision. Personal fit/baseline features must explicitly require a profile and must not fabricate data when none exists.

Keep the tray compact/resizable and align it more tightly with the left navigation geometry (16px outer margin, below the rail at short heights), with one quiet surface and internal row dividers instead of repeated floating borders. Do not attach a full-height permanent sidebar by default: it would allocate most of its space to empty chrome and shrink the map when the chat is pinned. A later docked list mode can be evaluated independently.

## Analysis first

Use a fixed responsive overview, not window management: three meaningful KPIs (matching offers, employers, share publishing pay), followed by demand by area/competency, publication activity, salary distributions and employers/locations. A question opens a full detail section with chart, exact definition, sample size and matching offers.

The same canonical map scope must reach every chart: engineering market, seven/14/30/90 local calendar days, geography/radius, source, role area, competency, seniority, modality and salary bounds, with identical personal exclusions. Scope must be visible, persist across navigation and be stored with saved views. A click adds a scope constraint and reveals underlying offers. Historical capture counts must not be presented as market growth, and portal sample counts must not be labeled market share.

Use one deterministic backend overview response built from shared job filtering and selected-market projections. Keep arbitrary SQL read-only and explicitly global under Advanced; do not rewrite arbitrary SQL to appear scoped. Save relative-filter/query definitions, not chart result snapshots. Handle failures explicitly rather than silently preserving an old chart as current.

Keep scripts/queries versioned in code behind named questions. Provide Explore for scoped questions and Advanced for SQL. Remove gravity/Tetris, floating windows and preset SQL selection from the default overview. Add named saved views only after count parity and chart definitions are tested.

## References and technical choice

- https://github.com/apache/echarts — a charting library suitable for a lazily loaded Analysis renderer; keep the existing Next.js/FastAPI/SQLite stack and load only required chart components.
- https://github.com/evidence-dev/evidence — reference for reports defined in SQL/Markdown/code, not a reason to migrate Radar to a second application framework.
- https://github.com/metabase/metabase — reference for shared dashboard filters and drilling into records, not a deployment dependency.
- https://github.com/reactive-resume/reactive-resume — a dedicated resume-building product; illustrates the separate scope Radar would be taking on by investing heavily in a CV editor.

Implementation: `analysis.py` reuses `list_jobs` and shared location inference, with explicit district/radius constraints. Typed `/api/analytics/overview` returns the deterministic aggregates; `/api/analytics/offers` returns paginated records for each bucket. Salary groups keep currency and period separate (including unknown periods); publication days use Lima's calendar and include zero days. Source counts are local capture coverage, never market share.

The default view uses responsive native bar charts without a new charting dependency. SQL remains read-only and explicitly global, in a simple optional editor. Stored query definitions from the previous floating workspace remain available under SQL; window geometry, gravity and result snapshots are no longer needed. Saved views store relative scope definitions in the browser. Filters survive a same-tab round trip through Settings; map district/radius state survives switching to Analysis and back.

Mi CV is available through Settings and Prepare CV in an offer; files, comparisons, profile editing and Studio remain functional. Retiring the underlying CV subsystem is a separate product decision. No new BI server, database engine, cloud dependency or automatic LLM-generated SQL is introduced.
