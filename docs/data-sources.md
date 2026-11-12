# Data sources and privacy

Radar reads public job postings and stores them in a local SQLite file. Nothing is uploaded anywhere by Radar itself.

## Sources

| Source | How it is read | Notes |
| --- | --- | --- |
| Indeed | JobSpy (scraper) | The portal's terms may prohibit automated access. Use at your own risk, at low frequency; keep it as an opt-in "advanced source". |
| LinkedIn | JobSpy (scraper) | Same warning; LinkedIn is the most restrictive. Radar never logs into your account or uses your session. |
| Computrabajo | Native public HTTP (`computrabajo_native.py`); optional legacy `mcp-computrabajo@1.0.0` via `npx` | Public search and detail pages only; no cookies. |
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

## Computrabajo transport (2026-11-04)

The default is native Python HTTP for public search cards and public offer detail, with bounded downloads,
no portal cookies and no application/profile actions. `sources/computrabajo_native.py` documents the
parser. The public markup/field conventions were reviewed against `mcp-computrabajo` 1.0.0 (MIT); see
[upstream package](https://www.npmjs.com/package/mcp-computrabajo). The Node distribution is not bundled.
Legacy MCP is explicit opt-in and still requires the user's configured runtime. HTTP 403 or challenge
pages are isolated source failures; Radar does not bypass them or treat them as a successfully empty market.

## Computrabajo HTML request compatibility (2026-11-09)

The public listing opened normally in a browser, while the original native request received an awselb/2.0 403 before parsing. A standard HTML request with Spanish language negotiation and a compatible User-Agent that explicitly identifies Radar returned HTTP 200 and 20 dated, located cards. The native adapter now uses that request shape for public search/detail. No portal account, personal browser profile, proxy, CAPTCHA handling or new dependency is used. Future 403/challenge responses still fail explicitly and retain source isolation/backoff; this is not a guarantee of uninterrupted portal access.

## Bumeran query matching (2026-11-10)

Bumeran's public search (`/api/avisos/searchV2`) matches every term in the query, so the long phrases used by the
career packs ("analista de datos reportes Excel", "data scientist machine learning") returned zero offers while the
same market answered 9–10 offers for the two-word core. The adapter now retries the same step with progressively
shorter prefixes (4, 3 and 2 words, never ending in a stopword) and keeps the first variant that answers, so
`analista de datos reportes Excel` resolves as `analista de datos`. The full phrase is always tried first; the
shortened variants only run when the portal answered with no offers. Classification and relevance tiers still
filter what enters, so a broader query cannot by itself promote an offer.

The two transport calls no longer swallow errors: when neither the JSON API nor the public HTML page answers,
`BumeranSource.search` raises `BumeranUnavailable(status_code=…)`. Scheduled capture and the in-app refresh record
that as a source failure instead of a successful empty market (HTTP 403 also counts towards the source pause).
`source_fetch` forwards the status from `urllib`'s `HTTPError.code` as well.
