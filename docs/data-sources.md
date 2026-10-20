# Data sources and privacy

Radar reads public job postings and stores them in a local SQLite file. Nothing is uploaded anywhere by Radar itself.

## Sources

| Source | How it is read | Notes |
| --- | --- | --- |
| Indeed | JobSpy (scraper) | The portal's terms may prohibit automated access. Use at your own risk, at low frequency; keep it as an opt-in "advanced source". |
| LinkedIn | JobSpy (scraper) | Same warning; LinkedIn is the most restrictive. Radar never logs into your account or uses your session. |
| Computrabajo | `mcp-computrabajo@1.0.0` through `npx` (pinned) | Public search pages only; no cookies. |
| Bumeran | Public JSON-LD / API connector | Direct public job posting queries and single URL import. |
| Empleos Perú | Public MTPE API connector | Public Peruvian Ministry of Labor job portal. |
| Single URL import | Direct fetch with SSRF guard | Any public offer URL from Computrabajo, LinkedIn, Indeed, Bumeran, or Empleos Perú. |
| CSV import | A file you provide | Your responsibility to have the right to use it. |

- Each portal runs isolated: one failure does not stop the others. Rate is low (weekly timer or a manual refresh).
- Every offer keeps its original link; attribution is the portal name shown next to it. Descriptions are shown for your
  own reading and are not redistributed.
- Radar never bypasses CAPTCHAs, never automates applications and never sends messages.

## What leaves your machine
- **Portal requests** while capturing offers (the search terms of your career pack).
- **LLM provider**, only if you enable the agent: your messages, the tool results it reads (offers, market data) and,
  when a question needs it, your CV (`get_my_cv`). Use a provider you trust, or a local model (Ollama) to keep it local.
- **Map tiles** are requested by your browser while you use the map: OpenFreeMap on the desktop (`tiles.openfreemap.org`) and OpenStreetMap on mobile. They see your IP and the area you view, not your data.
- Nothing else: no analytics, no telemetry, no crash reports.

## What stays local
Profile, CV, photo, applications, conversations, memory, API keys (OS credential store on Windows; `secrets.json` with
`0600` elsewhere) and the database. The data folder is outside the repository and must never be committed.

## Third-party notices
Radar uses open-source libraries (FastAPI, Next.js, MapLibre, Leaflet, pypdfium2, Pillow, JobSpy, among others) under their
own licenses; see each package. Map data © OpenStreetMap contributors, served by OpenFreeMap.

Radar is not affiliated with Indeed, LinkedIn, Computrabajo, Bumeran, or Empleos Perú.
