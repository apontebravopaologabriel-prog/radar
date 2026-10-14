# CVs: target profiles, gap analysis and downloadable CV

Status: implemented. Source files: `cv_targets.py`, `cv_baseline.py`, `cv_plan.py`, `cv_build.py`,
`cv_docx.py`, `cv_edit.py`, `cv_photo.py`, `profile_edit.py`, `api_cv.py`, `api_me.py`,
`frontend/components/CvView.tsx`.

Two different things, never mixed:

| | Target CV (hypothetical) | Downloadable CV (real) |
| --- | --- | --- |
| What | Ideal candidate the company seems to want for an offer | Your real CV, selected and ordered for an offer |
| Source | Written by the agent from the offer | `cv_master.json` only |
| Exportable | **Never.** Fixed mark `HIPOTÉTICO — no enviar` | DOCX and PDF |
| Purpose | See the exact target, measure the gap, decide what to learn | Apply with true content |

```text
offer -> ideal candidate (hypothetical) -> gap vs real profile -> actions -> evidence -> closure
```

## Local data (outside Git and outside SQLite)

In `~/.local/share/radar/` (or next to `RADAR_DB_PATH`): `cv_master.json` (real profile: experience,
education, certificates, projects), `targets/*.json` (one target per offer, `<company>_<title>.json`),
`photo.jpg`, `cvs/<date>/` (generated files). Include them in backups. The API never accepts a file path from
the client. The profile comes from text the user writes or a LinkedIn "Save as PDF" export; Radar never
automates or reads LinkedIn sessions.

The profile has one owner per field so nothing drifts:

| Data | Stored in |
| --- | --- |
| Name, headline, summary, home district, contact | `cv_master.json` (backup before edit) |
| One-line education, target areas, places, work modes, skills | SQLite `user_profile` / `user_skills` |
| Experience, certificates, projects | `cv_master.json` via `update_cv` |

## Principles

1. **Hypothetical is never official.** Mark is fixed; no PDF/Word export.
2. **Every item declares its origin:** `explicito` (the offer says it; keep the quote), `inferido` (implied by the
   role; keep the reason), `tipico` (probable filler for the field; lower confidence).
3. **Code computes the gap, not the LLM.** `cv_baseline.py` crosses the requirements Radar detected in the
   offer against the real profile: `cubierto` (certificate or experience), `parcial` (aptitude or self-claim
   without backing), `falta`; plus years of experience and education level from the description. The LLM only
   writes the ideal and proposes actions and **cannot reassign** a status the code computed (same `key` →
   code wins). Items the code does not cover are `estado: agente` (shown `ᵃ`). Soft skills are listed but not
   scored. Proximity is weighted and shows "insufficient data" with too few signals. Experience counts total years
   and separately years in roles mentioning the offer's skills (reaching the number only by summing all →
   `parcial`). CV skills are matched with the same aliases the active career uses for offers; projects count as
   strong evidence.
4. **Proximity vs fit.** Proximity: does your CV prove the offer's requirements. Fit (the map score): does the
   offer match your preferences (area, location, level). The view shows both and a reconciling sentence
   ("fits but you lack evidence", "you qualify but fit is low").
5. **Honest closure plan.** Each gap is typed by cost:

   | Kind | Example | Closure |
   | --- | --- | --- |
   | `dias` | Python certification, new tool | Short course |
   | `semanas` | Power BI dashboard, SQL analysis | Project with evidence |
   | `no_cerrable_rapido` | "2 years of experience" | A course does not replace it: internships, freelance, real projects, or aim at lower-level offers |

6. **District by rules.** If an offer names a zone, the nearest district is computed with the district
   coordinates and Haversine; the LLM only writes it. The distance from the user's real district is shown.
   Coordinates are approximate.

## Target CV format

JSON, not free Markdown (to render columns, mark covered/missing and build the matrix). The readable `.md` is
generated from it.

```json
{
  "job_id": "...",
  "generated_at": "2026-09-19",
  "hypothetical": true,
  "location": { "district": "Surquillo", "reason": "zone near Miraflores", "method": "haversine" },
  "sections": {
    "summary": [{ "text": "...", "origin": "inferido", "reason": "..." }],
    "experience": [{ "text": "2 years improving processes", "origin": "explicito", "quote": "..." }],
    "tools": [{ "text": "Python", "origin": "explicito", "quote": "...", "status": "falta" }],
    "education": [], "certifications": []
  },
  "gaps": [
    { "item": "Python", "kind": "dias", "action": "Short course + sample script", "estimate_days": 5,
      "evidence_to_produce": "Repo automating a report" }
  ]
}
```

`save_target_profile` validates: `quote` or `reason` on explicit items, `reason` on inferred items and on
`cubierto`, valid `origin`, `status` and `kind`; it returns `errors` when invalid. Company, title, hypothetical
mark and distance are set by Radar. Saving the same offer again overwrites the file.

## Selecting targets

Targets are the **starred offers** (`job_user_favorites`). The ★ on the map adds a target, the `✕` in the CVs
view removes it. There is no second mechanism. The base gap appears immediately for every target; the agent
enriches only the ones that matter.

## CVs view

Floating tool **CVs** replaces the map with a full-screen view (header with photo, name and district):

Tabs: `Objetivos`, `Plan`, `Matriz`, `Comparar`, `CV`. Pick up to 4 targets (`MAX_COMPARED`) for matrix and compare.

1. **Objetivos:** ★ offers ranked from most to least reachable, with proximity and fit.
2. **Matriz:** rows = requirements, columns = picked targets; shows what repeats and what is specific
   (only items with a `key` in `experience` and `tools`).
3. **Comparar:** real profile next to the picked targets, sections aligned by row in one grid.
4. **CV:** detail of one target with photo render, hypothetical mark and the downloadable-CV panel.
5. **Plan** (`GET /api/cv/plan`, `get_closure_plan`): simulates covering each open skill, adds the proximity
   points each target would gain, crosses with the % of last-30-day offers requiring it. Structural items
   (years, degree) are listed apart. Recomputed when opened.

Content renders with the local Markdown renderer; never `dangerouslySetInnerHTML`.

Endpoints (read-only except photo and build): `GET /api/cv/profile`, `/selection`, `/targets`, `/plan`,
`/photo`, `/build/preview`, `POST /api/cv/build`, `GET /api/cv/files/{day}/{name}`; `POST/DELETE /api/me/photo`;
`PATCH /api/me`.

## Photo

`POST /api/me/photo` validates with Pillow (not by extension), strips EXIF (it can carry GPS), resizes to 640 px
on the long side and saves `photo.jpg` (a leftover `photo.png` is removed). Corrupt, heavy or foreign formats are
rejected without writing anything. The photo is never included in the downloadable CV (safer for ATS).

## Closing the loop

`close_gap(skill, kind, name, ...)` records evidence the person already has: a `certificado` (its name must
mention the skill) or a `proyecto` (with a description of what they did). It saves it in the real CV, removes
the matching gap note, adds a career timeline entry and returns each target's proximity before and after (or
says nothing changed and why). It never invents anything.

## CV Studio (tab `Estudio` of the CVs view)

Implemented in v0.9; the design and the reasons are in [design-cv-studio.md](design-cv-studio.md). You can open it three ways: the `Estudio` button on a target (★) row, the `Estudio` tab (an offer picker with search; no ★ needed),
or the "Estudio de CV →" button in an offer's detail on the map. It opens your real CV for that offer: outline on the left, the page in the center, the agent pinned on the right.

- **Document = operations over the deterministic selection** (`cv_doc.py`). Omit, include, move and edit a line are stored per offer in
  `cv_documents` with undo/redo; `cv_master.json` is never modified. Template, photo and page budget are options.
- **What you see is the exported PDF** (`cv_render.py`: templates `ats` and `sidebar`, with the photo as a circle). The page is the PDF rendered
  to an image (`pypdfium2`), and each line has a box, so clicking the page selects the source line.
- **Agent suggestions** (`cv_doc_get`, `cv_doc_propose`): ops proposed by the agent wait in `cv_suggestions` until you accept them (before/after
  in the outline). **Fact guard** (`cv_facts.py`): a reworded line that adds a number, an organization/product name or a skill that is not in
  that line or its job entry is flagged and cannot be accepted. The summary and headline may use the whole master.
- **Application packages** (`cv_packages.py`, `prepare_application`): exporting writes `<root>/YYYY-MM-DD Company - Role/` with the PDF
  (and Word if asked) named `CV <Name> - <Role>.pdf`, `oferta.md` (a copy of the posting), `postulacion.json` and `anteriores/` for older
  versions. Names are safe for Windows/macOS/Linux and accent-free by default; the folder is configurable (default
  `Documents/Radar/Postulaciones`, set from the Studio or `PUT /api/cv/settings`, restricted to a subfolder of your home).
  "Abrir carpeta" resolves the path from the database; "Ya la envié" logs the application in the pipeline. Radar never submits for you.
- **Endpoints:** `GET /api/cv/studio/{job}`, `.../page/{n}.png`, `POST .../ops|options|undo|redo|reset|export`, `.../suggestions/{id}/accept|reject`,
  `.../suggestions/accept-safe`, `GET /api/cv/packages`, `GET /api/cv/packages/{job}/files/{name}`, `POST .../open-folder|applied`,
  `GET|PUT /api/cv/settings`.

## Selection engine (what feeds the Studio)

`cv_build.select_full` decides, by code, what enters the CV for an offer; nothing is invented or reworded.

- Scores each bullet, project and certificate by the offer's skills (same aliases as the profile cross) and keeps the best within a page
  budget (1 page with under 36 months of experience or for internship/trainee/junior offers, otherwise 2). Every left-out line carries its
  reason and enough data to be put back.
- Skills marked `falta` are never listed; the summary is yours. Language (Spanish or English) follows the offer.
- Honest coverage: demonstrated in the body, listed without backing, absent (not added). Warnings: missing contact data or placeholders such as
  "(nombre no indicado)".
- Each line has an id derived from its content hash (`exp:1a2b3c4d`), so `cv_master.json` needs no format change.
- Writers: `cv_render.py` (PDF, exact) and `cv_docx.py` (Word, standard library, approximate look). A system TrueType font is used when found
  (Calibri/Arial/DejaVu/Liberation, or `RADAR_PDF_FONT`), otherwise Helvetica with Latin-1 fallbacks.

`preview_cv`/`build_cv` and `/api/cv/build` still work (files in `cvs/<date>/`); the Studio and `prepare_application` replace them.

## Profile editing

Settings → Profile and the agent edit the same data through `profile_edit.py`:

- **Partial edits.** `update_profile_fields` and `PATCH /api/me` touch only the given fields. Lists accept
  `*_add` and `*_remove`; skills accept `{skill: level | remove}`. Everything is validated before writing and
  the file is restored if the database write fails.
- **Before → after.** The chat confirmation card shows the exact change; Settings offers "Undo" (the response
  carries the ready-to-send `undo`).
- **Modes** are stored as offers and scoring use them: `onsite`, `hybrid`, `remote`.
- The name stays equal in both stores; the place copy in the file follows the database; declared tools are read
  from the database on the fly.

## MCP tools

`list_targets()` (targets by proximity with base gap), `get_target_context(job_ids)` (max 10: requirements with
evidence, base gap with `key` and status, real profile, distance), `save_target_profile(job_id, profile)`,
`get_target_matrix()`, `resolve_nearest_districts(reference, limit=3)`. Code computes requirement status; the
agent only assigns status to the rest, citing the real profile.

## Pending

Done in v0.9: the Studio (page preview with clickable lines, outline, hand edits, undo/redo), two templates, application packages with offer
snapshot and archived versions, the agent suggestions with the fact guard, and the tools `cv_doc_get`, `cv_doc_propose`, `prepare_application`
and `list_application_packages`.

Still planned for v1.0 ([roadmap.md](roadmap.md#v10-your-cv-installable-the-plan)): import from Word/PDF with line-by-line confirmation; a template
rebuilt from the author's current CV (needs the PDF or a screenshot as reference); versions per role and the sent-CV learning loop. Later:
cover-letter drafts and keyword coverage reports. Also pending: highlight the offer on the map when a target CV is open.
