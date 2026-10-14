# Design: CV Studio (editor, agent panel, export and application folders)

Status: **phases 1–4 implemented in v0.9** (packages and naming, document model and templates, Studio UI, agent suggestions with the fact guard); import and the learning loop remain. It replaces the older "fill your own `.docx`" idea. Implementation notes and endpoints: [cv.md](cv.md#cv-studio-tab-estudio-of-the-cvs-view).

## Goal

For an offer, in one screen and without opening Word, GenOffice or any other program:

1. See your CV as pages, tailored to the offer.
2. Ask the agent (panel on the right) for changes, review each one, accept or reject.
3. Edit a line yourself when you prefer to.
4. Export PDF (primary) or Word, and find the file again later without hunting through folders.

Everything keeps the project's central guarantee: **every line of the CV traces to a real line of `cv_master.json`, and nothing
the agent writes can introduce a fact you did not give.**

## What GenOffice shows us, and what we copy

GenOffice (Apache-2.0, Electron) lets an agent edit a real `.docx` in a visible editor with tracked changes and rollback.
We copy the experience, not the code: its editor, Rust/WASM engines and Electron shell are far too large to embed, and a
general Word editor is the wrong tool for a structured, truth-constrained CV. What we adopt: a page canvas, the agent beside
it, **every agent edit arrives as a reviewable suggestion**, one-click rollback, and export to the real formats.

## Architecture

```text
cv_master.json (facts, source of truth)  ──┐
offer (requirements, language)            ──┼─> selection by code (exists) ─> CV document (versioned)
template (data) + variant (photo/no photo) ─┘                                      │
                                                                                   ├─> PDF renderer (fpdf2): the export AND the preview
                                                                                   ├─> DOCX writer (stdlib): approximate look, for portals that ask for Word
                                                                                   └─> hit map: line id -> page, box (click a line in the preview)
```

- **CV document** (new): ordered sections and blocks, each with `source_id` (the `cv_master` line it comes from), its text,
  included/omitted flag, optional approved rewording, template id, variant. Stored in SQLite with a revision history; it
  never overwrites `cv_master.json` unless you choose "also update my master".
- **One renderer for preview and PDF.** The preview is the exported PDF turned into page images (a PDF rasterizer such as
  `pypdfium2`, to be verified in the spike for Windows wheels and size), so what you see is exactly what you export. While writing
  each block the PDF writer records its page and box, which gives the **hit map**: clicking a line on the page selects its
  source line. The Word export shares the content but not the pixel layout; the UI says so.
- **Templates as data:** typography, columns, sidebar, photo box, section order, spacing. Two to start: a one-column ATS template
  and a sidebar template with photo that reproduces your current CV (built once from your PDF or a screenshot as reference).
- **Agent tools** (all go through the existing confirmation model):
  `cv_doc_get` (read the document and the offer), `cv_doc_propose` (a list of operations: include/omit, reorder, switch
  variant/template, set page budget, reword a line), `cv_doc_accept` / `cv_doc_reject` (by you, in the UI). Proposals are stored
  as pending suggestions; nothing changes the document until accepted.

## The fact guard (why rewording is safe)

An agent suggestion that rewords a line is checked **by code**, not by a model: from the proposed text, extract numbers, percentages,
currency amounts, dates, organization and product names, and skills/tools (the career pack's aliases). Any such token that is not in
the original line or in its experience entry is flagged **"dato nuevo no verificado"** in red and cannot be accepted until you
add that fact to your master yourself. Rewording that only trims, reorders or changes verbs passes. Accepted rewordings carry a
visible "reformulado" mark in the editor (not in the exported file) and keep the original one click away.

## Interface

Full-screen view inside CVs, tab `Estudio`:

| Area | Content |
| --- | --- |
| Left (narrow) | Outline: sections and lines with include/omit toggles, drag to reorder, line trace ("from: Experience › Empresa X › bullet 2"), coverage of the offer's requirements, versions |
| Center | Page canvas (the real PDF rendered), zoom, page budget indicator, click a line to select it, double-click to edit text yourself |
| Right | The existing agent panel, pinned, with the open document and the offer as screen context; suggestions appear inline on the canvas as before/after, with Accept / Reject per change and "Accept all safe" |
| Top bar | Template, variant (with/without photo), undo/redo, **Export PDF / Word**, **Prepare application** |

Editing text by hand writes to the document (and optionally to your master). Nothing here needs the internet except the agent.

## Where files live: application packages

Uploading to portals is manual, so the file has to be easy to find and look professional to the recruiter. Two different names:

| What | Name | Why |
| --- | --- | --- |
| **Folder (for you)** | `2026-10-14 Empresa - Puesto` | Sorted by date, readable, one per application, unique even for repeated offers (`-2`) |
| **File the recruiter sees** | `CV Ana Pérez - Analista BI.pdf` (pattern configurable) | Recruiters see only the filename: your name plus the role, no internal codes, ASCII-safe fallback for portals that mangle accents |

Each application gets one folder containing: the CV PDF (and Word if exported), the cover-letter draft, `oferta.md` (a **snapshot** of
the posting: title, company, URL, date, full description, because postings disappear), `postulacion.json` (CV document id and
revision, template, variant, hash, status, dates) and notes. Re-generating makes `v2`, `v3` inside the same folder; the current one
is marked. Radar keeps an index in the database (`application_packages`, linked to `applications` and the sent-CV log), so the
**Postulaciones** view lists every application with its status, files and link, searchable, and "which CV did I send to X?" always
has an answer.

**Root folder:** a user-visible folder, not the hidden app-data directory (file-upload dialogs make hidden folders painful).
Default `Documents/Radar/Postulaciones`; configurable. On your machine the natural choice is
`~/Documents/Personal/Postulaciones/`, which also falls inside your existing Documents mirror to Drive (check that you want CVs
there). Generated files never go inside the repository.

**Manual-upload helpers:** "Open folder" (a closed action: Radar derives the path from the database, never from the client), "Copy
path", "Open posting" in the browser, and after you confirm, "Mark as applied" which logs the application. Radar never submits
an application for you.

## Plan and acceptance

| Phase | Deliverable | Acceptance | Effort |
| --- | --- | --- | --- |
| 0. Spike | PDF → page images with hit map; Windows wheel and size of the rasterizer; fpdf2 columns, sidebar and photo; reference template from your PDF | A one-page sidebar CV rendered with photo and a clickable line map, measured on Linux and in CI on Windows | 2 days |
| 1. Packages and naming | `application_packages`, folder layout, filename patterns, offer snapshot, Postulaciones view, open-folder/copy-path, migration of today's `cvs/` | Every generated CV lands in its application folder; nothing is overwritten; the index matches the disk | S–M |
| 2. Document model and templates | CV document with revisions, selection by code feeding it, two templates, variants, PDF and Word from the same document | Same content produces identical PDF on repeat; trace for every line; page budget respected | M |
| 3. Studio UI | Outline, page canvas with hit map, include/omit/reorder, hand editing, undo/redo, export buttons | You can tailor and export a CV for a real offer without leaving Radar | M |
| 4. Agent panel | `cv_doc_*` tools, suggestions as before/after, the fact guard, accept/reject, "accept all safe" | A rewording that adds a number or a tool is blocked in tests; agent edits never change the document unaccepted | M |
| 5. Import | Word/PDF → `cv_master.json` with line-by-line confirmation (matters most for peers; your master already exists) | A real CV imports with a correction pass under five minutes | M |
| 6. Learning loop | Sent-CV log analytics (which version got replies), keyword coverage report, cover-letter draft | Reports from your own history | S–M |

Order note: for the author the master already exists, so phases 1–4 come before import; for the peer pilot, phase 5 must land before it.

## Tests

- Unit: document revisions and undo, selection determinism, filename sanitation (accents, long names, collisions, reserved
  Windows names), fact guard (adds number / tool / org → blocked; trims → passes), hit map coordinates.
- Golden files: rendered page images of the reference templates compared with a tolerance.
- Security: the open-folder action only resolves paths from the database; Origin guard covers the new endpoints.
- Agent evaluation: a set of edit requests with expected operations, and adversarial ones ("add 5 years at Google").

## Risks and open questions

- **Rasterizer on Windows:** a spike item. Fallback: the webview's built-in PDF viewer (no hit map, still exact).
- **Exact replica of your current CV:** needs your PDF or a screenshot as the design reference; fonts must be redistributable
  (use a bundled open font if your Word uses a proprietary one).
- **Word export fidelity:** approximate by design; PDF is the exact one.
- **Rewording value vs risk:** if the fact guard proves too strict, loosen it per token class, never silently.
- **Questions for you:** the export root folder; the filename pattern; whether the sidebar-with-photo template is your actual style;
  whether CVs in Drive (via your Documents mirror) is acceptable.
