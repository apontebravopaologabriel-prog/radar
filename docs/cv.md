# My CV: import once, prepare for each offer

The primary workflow is **Mi CV → import/review → prepare for an offer → preview → download**.
The same factual profile is available from the desktop rail and Settings → Mi CV on desktop/mobile.
No agent or API key is required. Detailed editing and agent assistance are optional.

## User-facing model

- **Mesa de postulación (`Preparar CV`)** is the default view in `Mi CV` (☰), acting as the bridge between
  the Inbox (`◎` Map / starred offers) and the Tracker (`✓` Procesos). It shows starred offers (`★`) with
  their requirement readiness, already-exported CV packages ready to upload or promote via **Me contactaron**,
  and a market picker to prepare a CV for any active offer without starring it first.
- Opening an offer shows the actual PDF page preview with **Descargar PDF**, **Editar en detalle**,
  requirements versus factual evidence, and **Me contactaron → Procesos**. No hypothetical candidate is
  needed, and the initial screen does not pin the agent.
- **Editar en detalle** reveals Studio: included/omitted lines, ordering, hand edits, templates, photo,
  page budget, undo/redo and optional agent suggestions. Returning to preview preserves those edits.
- **Comparar ★ y brechas** is a dedicated tab comparing up to four starred offers against factual profile
  evidence, surfacing what to demonstrate or improve using deterministic baseline requirements only.
- **Mi trayectoria** edits the factual trajectory (experience, education, courses/certificates, projects,
  languages) without repeating the file-import dropzone or personal/search settings once a profile exists;
  full file import and personal/search preferences live in **Settings → Mi CV** (`/ajustes`).

The old Objectives/Plan/Matrix/Compare/hypothetical-CV tabs are removed from the primary interface.
Historical hypothetical target JSON files and read APIs remain compatible; they are never presented as
real facts or exported. The default UI no longer directs the user to unavailable agent tools.

## Import and review

`cv_import.py` extracts bounded local text from PDF/DOCX (8 MB, PDF up to 20 pages, 60,000 text characters).
Scans without a text layer and old `.doc` files need conversion. Extraction is heuristic: sections and
separators must be recognizable, dates and reading order can need correction. No OCR or LLM is used.

Import recognizes name, email/phone/LinkedIn, headline, summary, education, dated experience with bullets,
courses/certificates, projects and explicitly stated language levels. Recognized tools remain mentions,
without an invented proficiency level. The review exposes every section and the original extracted text.

The shared `CvImportPanel` is used for first run and updates:

1. Drop/select a file, or start manually.
2. Review/correct extracted fields; the resumable draft autosaves locally on the API.
3. **Revisar cambios** shows the before/after values of every changed factual field.
4. **Confirmar y guardar** merges reviewed data, preserves facts absent from the new file, records a
   profile version and refreshes scores. The first-run screen starts capture only for a new profile.
5. Subsequent imports offer **Deshacer importación**, guarded by the current CV revision.

Repeated imports match normalized section identities. Dated jobs at the same employer can remain separate.
An import is a merge, not deletion of the existing trajectory; removals happen explicitly in the editor.

Original binary files are immutable and content-addressed under `cv_imports/` beside the database.
Preview stages the file, but only confirmation makes it the current original. The original is downloadable
and can be associated unchanged with an offer using **Usar mi archivo original**. Profile edits do not
rewrite that file. Older source files remain local; do not version them.

## Factual editing and concurrency

`CvHistoryEditor` and `cv_profile.py` edit the real trajectory without chat. Fields include dates, bullets,
project descriptions and skills, certificate issuer, and language evidence. Sections are collapsed by
purpose, edited explicitly and saved together; the last save can be undone. Pending edits are retained in
browser storage with their base section values and resumed only when compatible with the saved profile.
Identity/preferences reuse `ProfileTab` and `profile_edit.py`, including their save-on-blur and undo.

`PATCH /api/me/cv` replaces only supplied sections, validates all of them before writing, keeps unrelated
fields, makes an atomic backup and returns an undo snapshot. SHA-256 revisions reject stale writes with
HTTP 409. Import and agent/profile editing share a per-file lock. Score refresh failures are reported after
saving rather than pretending the CV save failed.

Storage responsibilities remain unchanged:

| Data | Owner |
| --- | --- |
| Identity, contact, summary, factual experience/education/projects/certificates/languages | `cv_master.json` |
| Search preferences and declared skill levels | SQLite profile/skill tables |
| Offer-specific omissions, ordering, wording and template | `cv_documents` operations |
| Original imported files | `cv_imports/` |
| Prepared files and offer snapshots | Visible application folders indexed by `application_packages` |

Backups use microsecond timestamps and retain the last five copies. A revision check also prevents undoing
an import over changes made afterward. Unknown tool levels and missing evidence are never silently treated
as proficiency or proof of qualification.

## Preparation, detailed editing and exports

`cv_build.select_full` deterministically chooses content within a page budget; it never invents or
rewrites facts. `cv_doc.py` applies per-offer operations without changing the factual master. The preview
and export share `cv_render.py`; the PDF is rendered as page images with selectable line boxes in detailed
editing. The ATS layout is the default; sidebar/photo and Word are optional.

A preview carries a revision of its rendered PDF. The normal download request includes it; if the document
changed, export stops before writing files and asks the user to review the new version. Agent proposals
remain before/after suggestions; the fact guard prevents accepting additions unsupported by the source.

`prepare_application`, the compatibility `build_cv` tool and the HTTP build route all export the **current
document**, including its reviewed operations, through `cv_packages.export`. The old internal CLI builder
and existing dated file download links remain available for compatibility. New package file URLs also
work through the compatibility download route. `preview_cv` returns the current document selection.

Application folders default to `Documents/Radar/Postulaciones`, with safe cross-platform filenames:

```text
YYYY-MM-DD Company - Role/
  CV Name - Role.pdf
  oferta.md
  postulacion.json
  anteriores/
```

Export creates a prepared package, never a submitted application or response-driven process. Manual sent-state recording remains a legacy API/history capability. **Usar mi archivo original** copies its exact bytes into the offer folder
and records its provenance without applying Studio edits. Exporting again archives previous files.
Prepared packages remain accessible in Mi CV and the offer detail without a tracking row.

## Comparison and improvement

The comparison is contextual in Mi CV, using starred offers and their existing baseline engine.
It shows requirements, evidence and reasons rather than several competing headline percentages.
**Con evidencia**, **Por revisar**, and **Sin evidencia en tu perfil** describe what is documented;
absence from the profile is not a claim that the person lacks the competency.

The existing closure-plan engine aggregates open skills and market demand. The UI shows a short list and
keeps structural education/experience requirements separate. Evidence can be added directly in Mi CV;
a completed course never silently establishes advanced skill or replaces years of relevant experience.
The regular deterministic fit score and its uncertainty semantics elsewhere in Radar are unchanged.

## API

| Route | Purpose |
| --- | --- |
| `POST /api/me/cv/preview` | Stage a local source and extract a reviewable draft |
| `GET /api/me/setup`, `PUT /api/me/setup/draft` | Resume/autosave import drafts |
| `POST /api/me/cv/changes`, `POST /api/me/setup/confirm` | Review and confirm a merge |
| `POST /api/me/cv/undo-import` | Revision-checked restore of the previous import |
| `GET/PATCH /api/me/cv` | Read/edit factual sections with optimistic concurrency |
| `GET /api/me/cv/original` | Download only the confirmed source file |
| `GET /api/cv/studio/{job}`, `.../page/{n}.png` | Current document and exact PDF preview |
| `POST .../ops\|options\|undo\|redo\|reset\|export` | Detailed document editing and export |
| `POST .../suggestions/{id}/accept\|reject`, `.../suggestions/accept-safe` | Reviewed agent suggestions |
| `GET /api/cv/packages`, `GET /api/cv/packages/{job}/files/{name}` | Prepared files/history |
| `POST /api/cv/packages/{job}/original\|open-folder\|applied` | Use source file, open folder, record manual submission |
| `GET /api/cv/selection`, `/targets`, `/plan` | Saved-offer comparison and improvement priorities |
| `GET/PUT /api/cv/settings` | Optional folder/naming preferences |

## Verification

`tests/test_cv_workflow.py` covers complete-section extraction, merge preservation and duplicate imports,
original-byte preservation, undo, stale-write rejection, atomic factual edits, API behavior with the agent
disabled, export matching its preview, and using an original without recording a submission. Existing
baseline, selection, Studio, package and profile tests continue to cover their respective engines.
