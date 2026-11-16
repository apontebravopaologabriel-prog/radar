# My CV: factual profile and offer matching

The workflow is **Mi CV / Settings → import or edit factual trajectory → match against offers**.
No agent or API key is required; the factual profile (`cv_master.json`) feeds deterministic scoring, `Analysis → Comparar ★`, and the agent's `get_my_cv` / `get_interview_dossier` tools.

## Import and review

`cv_import.py` extracts bounded local text from PDF/DOCX (8 MB, PDF up to 20 pages, 60,000 text characters) without OCR or LLM calls.
Extraction is heuristic; review and confirm every field before saving.

1. Drop/select a file in **Settings → Mi CV** (`/ajustes`) or onboarding.
2. Review/correct extracted fields; **Confirmar y guardar** merges reviewed data, preserves existing facts, and refreshes scores.
3. Subsequent imports offer **Deshacer importación**, guarded by the current CV revision.

Original binary files are stored content-addressed under `cv_imports/` beside the database and remain downloadable via `/api/me/cv/original`.

## Factual editing and storage

`CvHistoryEditor` and `cv_profile.py` edit the factual trajectory (experience, education, courses/certificates, projects, languages) without chat.
`PATCH /api/me/cv` replaces only supplied sections, validates before writing, keeps atomic backups (last 5), and rejects stale revisions with HTTP 409.
Identity and search preferences reuse `ProfileTab` and `profile_edit.py`.

| Data | Owner |
| --- | --- |
| Identity, contact, summary, factual experience/education/projects/certificates/languages | `cv_master.json` |
| Search preferences and declared skill levels | SQLite profile/skill tables |
| Original imported files | `cv_imports/` |

## Offer matching

- `cv_baseline.py` deterministically compares offer requirements against factual profile evidence (no invented skills or hiring probabilities).
- `Analysis → Comparar ★` compares up to four starred or submitted offers against factual profile evidence.
- Historical hypothetical target JSON files and read APIs remain compatible; they are never presented as real facts.
