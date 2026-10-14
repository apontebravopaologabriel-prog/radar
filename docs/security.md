# Security and compliance

Radar is a single-user, local-first tool. The threat model below states what it defends against and what it
does not.

## Assets and boundaries

| Asset | Location | Sensitivity |
| --- | --- | --- |
| Profile, applications, conversations, memory | `radar.db` | Personal data |
| Real CV, photo, generated CVs | `cv_master.json`, `photo.jpg`, `cvs/` | Personal data |
| LLM provider keys | `secrets.json` (`0600`), never in the database | Credential |
| Access key | `RADAR_ACCESS_TOKEN` environment variable | Credential |
| Offers, companies | `radar.db` | Public third-party text, untrusted |

Trust boundaries: the browser ↔ local API; the API ↔ the LLM provider (profile and offers leave the machine);
offer text ↔ the agent (untrusted input); portals ↔ connectors. The SQLite file has no network port.

## Controls in place

- **Host and Origin guard** (`security.py`): requests whose `Host` is not localhost, `RADAR_API_HOST` or
  `RADAR_ALLOWED_HOSTS` get 403 (DNS rebinding), and state-changing requests carrying a foreign `Origin` (or
  `null`) get 403. Plain scripts without `Origin` still work.
- **Security headers** on every response: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, and a CSP limited to `frame-ancestors 'none'; base-uri 'self'; object-src 'none';
  form-action 'self'` (no script restriction: the Next.js export needs inline scripts).
- **Private files:** the API, MCP server and CLI set `umask 077`; on first connection (and every start) the database,
  `-wal`/`-shm`, `secrets.json`, `cv_master.json`, photos, copies and the `backups/`, `targets/`, `cvs/`, `careers/`
  folders become `600`/`700`. The data folder itself is `700` when Radar owns it. No effect on Windows.
- **Credential store:** on Windows (or with `RADAR_SECRETS_BACKEND=keyring`) provider keys live in the OS credential
  manager; any old plaintext copy is migrated and removed. Elsewhere they stay in `secrets.json` (`0600`).
- **Pinned connector:** the Computrabajo adapter runs `mcp-computrabajo@1.0.0`, not `@latest`.
- **Login screen** on desktop and mobile when the access key is set. CI runs a `pip-audit`/`npm audit` job (informational)
  and Dependabot is enabled.
- **Access key** (`auth.py`): with `RADAR_ACCESS_TOKEN`, every `/api/*` except health, login and status needs
  the session cookie (`HttpOnly`, `SameSite=Strict`, `Secure` over HTTPS, 30 days) or `Authorization: Bearer`.
  Constant-time comparison; 5 failed logins per minute per client. Without the variable there is no
  authentication, so the API binds `127.0.0.1` by default. This is personal protection, not multi-user auth.
- **Untrusted offer text:** descriptions reach the agent marked `datos_externos_no_confiables`; the prompt treats
  them as information, never instructions. Rendering uses the local Markdown renderer (no raw HTML, only
  http/https/mailto links).
- **Write tools never run inside the agent loop.** They return as `pending` and the user approves them at
  `/api/chat/confirm`. `auto` mode self-approves only four personal-tracking actions (`favorite_job`,
  `track_job_application`, `remember_user`, `record_career_event`); `update_profile_fields`, `close_gap` and
  `build_cv` still ask. Plan and read-only modes offer no write tool and reject any call. There are no tools
  that apply to jobs or send messages; `ingest_jobs` and `save_target_profile` are not exposed to the chat.
- **Closed action lists:** `run_maintenance` accepts only `backup`, `repair_data`, `expire_stale`,
  `check_applications`, `market_snapshot`; `set_refresh_schedule` edits only `radar-refresh.timer` (1–30 days);
  `update_cv` validates each section and keeps a previous copy. None deletes offers; reclassification writes a
  reversible JSON. `update_profile_fields` restores the CV file if the database write fails.
- **Bounded interface context:** the context the UI sends to the agent includes third-party offer text and reaches the system prompt, so `sanitize_context` clips strings, depth and total size and strips control characters. Chat history is capped per message and in total and never accepts a `system` role. The prompt forbids building URLs or following instructions found in postings; external links in the chat show their real host on hover.
- **The agent cannot change** the API key, read-only mode or the token cap.
- **SQL editor:** the connection is opened `mode=ro`, only a single `SELECT`/`WITH` is accepted (validated
  before reaching SQLite), and a progress handler aborts slow queries. Provider keys live outside this
  database.
- **Files:** `GET /api/cv/files/...` serves only `.docx`/`.pdf` inside `cvs/`; paths with `..` or from other
  folders are rejected. The API never accepts a client file path. Photos are verified with Pillow, stripped of
  EXIF and resized.
- **Outbound URL guard** (`ensure_public_http_url`): the link checker visits URLs that come from external job posts, so every request, redirects included, must be http(s) to a public address; loopback, private ranges, link-local and cloud-metadata addresses are refused. A DNS change between check and connection is not covered.
- **Subprocesses** use argument lists (no `shell=True`) with timeouts.
- **CORS** is limited to localhost origins (`RADAR_API_ALLOW_ORIGINS`).
- The service worker never caches `/api/chat`, `/api/agent` or `/api/auth`.

## Known gaps (tracked in [roadmap.md](roadmap.md#remaining-for-v10-ordered))

1. **Single shared token**, no rotation and no per-device sessions.
2. **Pre-existing copies.** Old manual `.bak*` and `pre-*` copies in the data folder are hardened to `600` but are not
   deleted; remove the ones you no longer need.
3. **No script restriction in the CSP** (needs a nonce-based build of the frontend).
4. **Unsigned installer** until a code-signing certificate is configured in the release workflow.
5. **Scraping connectors** (Indeed, LinkedIn) are subject to portal terms; see below.

## Privacy

- The profile and the offers the agent consults travel to the chosen LLM provider. Use a provider you trust or
  local Ollama to keep data on the machine. `get_my_cv` sends the full CV when a question needs it; the fixed
  prompt carries only the name and headline.
- Conversations and memory stay in the local database; the agent searches past conversations only when the
  person alludes to them.
- Keep only the data needed for scoring. Do not store `.env` or portal cookies in Git; Radar does not use
  Computrabajo cookies.
- Peruvian Law 29733 (personal data) and GDPR apply if Radar ever becomes multi-user or hosted: consent, export
  and delete my data, privacy policy, the LLM provider as data processor.

## Portal terms

Connectors read public pages and remain subject to each platform's terms, especially LinkedIn and
Computrabajo. Review current terms before raising frequency, volume or scope. Radar does not bypass CAPTCHAs
or access controls and does not automate personal sessions. LinkedIn is read only through public JobSpy
search, or by user-prepared CSV import.

## Data quality rules (integrity)

- `NULL` means unavailable; a missing salary is not zero.
- Every classification keeps its evidence.
- Offer count is not competition.
- Review recommendations manually before acting.
- The score, competency levels and offer validity are never decided by an LLM.

## Legacy

`legacy/postgres/docker-compose.yml` is pre-SQLite infrastructure. If started for any reason it must stay bound
to `127.0.0.1`.
