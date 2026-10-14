# Operations

All paths assume the repo at `/home/paolo/Projects/Radar`. Data lives in `~/.local/share/radar/` (or next to
`RADAR_DB_PATH`); logs live in `~/.local/state/radar/`.

## Install

```bash
cp .env.example .env
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest
cd frontend && npm ci && npm run build      # produces frontend/out (gitignored)
```

No external service is needed. SQLite is created on first use.

## Environment variables

| Variable | Default | Effect |
| --- | --- | --- |
| `RADAR_DB_PATH` | `~/.local/share/radar/radar.db` | Database path (also accepts `sqlite:///path`). All local files live next to it |
| `RADAR_API_HOST` / `RADAR_API_PORT` | `127.0.0.1` / `8100` | API bind address |
| `RADAR_API_ALLOW_ORIGINS` | localhost:3000, 127.0.0.1:3000 and :8100 | CORS origins |
| `RADAR_ALLOWED_HOSTS` | empty | Extra `Host` names the API accepts (besides localhost and `RADAR_API_HOST`), e.g. a Tailscale name. Other hosts get 403 (DNS-rebinding guard) |
| `RADAR_STATE_DIR` | OS state folder (`~/.local/state/radar`) | Logs (`refresh.log`) |
| `RADAR_SECRETS_BACKEND` | `auto` | `file` (0600 file), `keyring` (OS credential store) or `auto` (keyring on Windows only) |
| `RADAR_INTERNAL_SCHEDULER` | `1` | `0` disables the in-process scheduler (it is off anyway when the systemd timer exists) |
| `RADAR_FRONTEND_DIR` | `frontend/out` (or the bundled copy) | Static frontend folder |
| `RADAR_PDF_FONT` | unset | Folder with `regular.ttf`, `bold.ttf`, `italic.ttf` for the CV PDF |
| `RADAR_ACCESS_TOKEN` | unset | Enables the access key for `/api/*` (see Remote access) |
| `RADAR_CAREER` | `industrial_engineering` | Default career pack when none is stored |
| `RADAR_JOBSPY_SITES` | `indeed,linkedin` | JobSpy portals |
| `RADAR_COMPUTRABAJO_COMMAND` / `_ARGS` | `npx` / `-y,mcp-computrabajo@1.0.0` | Computrabajo MCP adapter command (version pinned in `sources/computrabajo.py`) |
| `RADAR_COMPUTRABAJO_ENABLED` | `1` | `0` pauses Computrabajo in the refresh |
| `RADAR_COMPUTRABAJO_DETAILS` | on | `0` skips the per-offer detail call (fast tests) |
| `RADAR_MAX_AGE_DAYS` | `10` | Freshness window of the refresh script |
| `RADAR_STALE_AFTER_DAYS` | `45` | Days unseen before an offer is deactivated |
| `RADAR_LIVENESS_CHECK_LIMIT` | `150` | URLs visited per refresh to detect closed offers |
| `RADAR_CITIES` | empty (Lima only) | Comma list of extra cities for the refresh, e.g. `Arequipa,Trujillo` |
| `RADAR_MCP_TRANSPORT` | `stdio` | MCP transport |

## Ingestion

```bash
.venv/bin/radar ingest --source computrabajo --query "practicante de procesos" --location Lima --limit 10
```

- Computrabajo reads the result cards, then `get-job-detail` for description, salary, contract and schedule.
  A failing detail call keeps the card and does not interrupt the batch. Relative dates ("Hace 2 días",
  "Hoy", "Ayer") are parsed so fresh offers are not dropped.
- JobSpy (Indeed, LinkedIn) installs in the main environment: `pip install -e '.[jobspy]'` (imports verified on Python 3.14
  with NumPy 1.26.3 and inside the packaged app). Use a separate environment only if that install fails on your Python.

  ```bash
  .venv/bin/radar ingest --source jobspy --query "practicante ingeniería industrial" --location Lima --limit 10
  ```

- `--max-age-days` defaults to 14 on the CLI; the web UI defaults to 7 and offers 14, 30 and 90. Offers
  without a date, in the future or out of range are stored but never recommended.

### Assisted import (portals without a permitted connector)

For LinkedIn, Bumeran, Laborum, Empleos Perú, Hiring Room or a corporate page, prepare a CSV/JSON:

```text
title,company,url,location,description,work_mode,salary_min,salary_max,salary_currency,salary_period,application_status,application_checked_at
```

Optional extra columns: `published_at`, `hours_per_week`, `schedule_text`.

```bash
.venv/bin/radar import-jobs --source linkedin --file offers.csv
```

Radar normalizes, classifies, deduplicates, extracts salary from text and keeps the original URL. No password,
cookie or account automation. Re-import a row to update it; history is kept.

## Profile and events

```bash
.venv/bin/radar profile --name "Name" --area "Procesos" --location Lima --skill Excel=advanced --skill SQL=intermediate
.venv/bin/radar career-event --type course --title "PostgreSQL course" --started-on 2026-09-11
```

Saving the profile recalculates scores of active offers. Events never delete earlier versions. Settings →
Profile and the agent edit the same data (see [cv.md](cv.md#profile-editing)).

## Data maintenance commands

| Command | Effect |
| --- | --- |
| `radar repair-data` | Recompute work mode, sector, salary, schedule for older rows |
| `radar audit-data` | Report duplicates, per-source links, area integrity, commercial titles |
| `radar expire-stale --days 45` | Deactivate offers no source has seen in N days (history stays) |
| `radar check-applications --limit 150 --recheck-after-days 3` | Visit active URLs; 404/410 → `closed`; 401/403 (anti-bot) → `unknown`, never assumed closed. Reliable mainly for LinkedIn |
| `radar market-snapshot` | Store dated market totals, areas and skills |
| `radar backup` | Consistent copy (SQLite backup API) in `backups/`, keeps the last 5 |
| `radar skill export --out docs/skills` | Regenerate the agent skill |

The agent offers the same through `run_maintenance(task)` (closed list: `backup`, `repair_data`, `expire_stale`,
`check_applications` up to 60 links, `market_snapshot`). Run a backup before reclassifying or repairing.
`update_cv` keeps `cv_master.json.bak-<date>` (last 5). `get_system_status` summarizes database size,
integrity, offers by tier, last capture and timer.

## Run as a desktop app (any OS)

`radar-app` (or `python -m radar.app`) starts the API, opens the interface in its own window when `pywebview` is
installed (WebView2 on Windows) or in the default browser otherwise, and runs the in-process scheduler. If Radar is
already running on the port it only opens the window. `radar-app --smoke` starts on a free port, checks health, the
frontend and the MCP tools, and exits (used by the release CI). The Windows installer is described in
[packaging.md](packaging.md).

## Scheduled refresh

The capture itself is `radar refresh [--cities A,B] [--max-age-days N] [--no-computrabajo]` (`src/radar/capture.py`):
cross-platform, in-process, driven by the active career pack (`market_queries` for Lima, `queries` for extra cities).
Who triggers it depends on the platform:

| Platform | Trigger |
| --- | --- |
| Linux with the systemd timer installed | `radar-refresh.timer` → `scripts/radar-refresh.sh` → `radar refresh` (log in `refresh.log`) |
| Windows, macOS, packaged app, Linux without the timer | The in-process scheduler (`scheduler.py`): checks every minute, runs when `refresh_every_days` (default 7, 0 = off) has elapsed since `refresh_last_at`, and 2 minutes after start if overdue. Only runs while Radar is open. `set_refresh_schedule` changes the interval |

The rest of this section describes the capture and the systemd flow.

`scripts/radar-refresh.sh` runs as the user service `radar-refresh.service`, fired by `radar-refresh.timer`
every 7 days (`OnUnitActiveSec=7d`) and 5 minutes after boot (`OnBootSec=5min`). It:

1. Runs the pack's broad searches (16 for Industrial Engineering: data/BI, processes, automation, ERP, planning,
   supply chain, logistics, purchasing, production, quality, maintenance, PMO...; 18 for Systems) on Indeed and
   LinkedIn (JobSpy, no login) and Computrabajo (MCP, full detail), then the pack's short queries per extra city.
2. Isolates each portal and step (3-minute limit each): a failure or timeout is logged in the final summary and does
   not block the rest.
3. Uses a 10-day window so weekly runs overlap. It never filters by salary.
4. Runs `repair-data`, `expire-stale` and `check-applications`, saves the market snapshot and finishes with
   `radar backup`.

```bash
systemctl --user status radar-refresh.timer
systemctl --user list-timers radar-refresh.timer
tail -f ~/.local/state/radar/refresh.log
systemctl --user disable --now radar-refresh.timer     # pause
systemctl --user enable --now radar-refresh.timer      # resume
```

Change the frequency from the agent (`set_refresh_schedule(days, on_boot)`: 1–30 days, 0 disables, Linux with
systemd only) or edit `~/.config/systemd/user/radar-refresh.timer`, then `systemctl --user daemon-reload` and
`systemctl --user restart radar-refresh.timer`.

### Coverage beyond Lima

Set `RADAR_CITIES="Arequipa,Trujillo"` (4 queries per city on JobSpy and Computrabajo; each city adds minutes).
A new city must also exist in `src/radar/geolocation.py` (`_CITIES`) to appear on the map. Coordinates are
city or department centroids, so an offer in an Arequipa district is placed at Arequipa.

### Focused refresh (agent and MCP)

`refresh_market(place, limit)` (asks confirmation) pulls offers biased to a district or city in the
background (several minutes); `get_refresh_status()` reports progress. JobSpy gets "District, Lima"; for
Computrabajo the district is appended to the keyword, so the result is biased, not limited, to the place.

## Desktop launcher

`scripts/radar-launch.sh` (Linux only; on other systems use `radar-app` or the installer) (the `Radar` entry in the system menu): builds `frontend/out` if missing, starts the
API if it is not running (and restarts it when any `src/radar/**/*.py` is newer than the process), and opens
`http://127.0.0.1:8100/radar` as a standalone Chromium app (`--app`, separate profile in
`~/.local/state/radar/chromium`). The API stays up when the window closes. Logs: `launcher.log`, `api.log`,
`frontend.log` in `~/.local/state/radar/`.

Manual API restart (new routes return 404 until then; also reload external MCP servers to see new tools):

```bash
pkill -f ".venv/bin/radar-api"
nohup .venv/bin/radar-api >>~/.local/state/radar/api.log 2>&1 &
```

## Hiding and restoring offers

In the offer detail, the eye icon asks for a reason (`closed`, `not_interested`, `applied`, `duplicate`,
`other`) and stores it in `job_user_status`. The eye icon in the tray lists hidden offers; the detail then offers
restore. `jobs` is never modified.

## Remote access (phone)

Radar is local; the phone must reach the PC, which must be on.

1. Install Tailscale on the PC and the phone (or use a Cloudflare tunnel).
2. Set a long unique key and bind the API only to the private interface:

   ```bash
   export RADAR_ACCESS_TOKEN='a-long-unique-key'
   RADAR_API_HOST=<tailscale-ip-of-the-pc> .venv/bin/radar-api
   ```

3. Open `http://<tailscale-ip>:8100/m` on the phone and install it ("Add to home screen"). The session cookie
   is `Secure` only over HTTPS; `tailscale serve` provides HTTPS.

Without `RADAR_ACCESS_TOKEN` there is no authentication: never expose the API beyond `127.0.0.1` that way, and
never bind `0.0.0.0` on a network you do not control. With the token set, both `/radar` and `/ajustes` show a login
screen. `RADAR_API_HOST` is added to the accepted `Host` names automatically; add other names (for example a
`tailscale serve` hostname) with `RADAR_ALLOWED_HOSTS`. See [security.md](security.md). Mobile remote access is
experimental in the 1.0 plan.

## Agent configuration

Settings → Agent: provider, model, reasoning effort, API key, monthly token cap, context window, read-only.
The key is stored in `secrets.json` (`0600`), never in the database or the browser. Usage is counted in
`agent_usage` and the chat stops at the cap. DeepSeek model ids: `deepseek-flash` (V4.1 Flash) and
`deepseek-v4-pro`; `deepseek-v4-flash` is a legacy alias shown only if already stored. UI and commands:
[agent.md](agent.md).

## What to back up, and where

Everything personal lives outside the repository (and must stay out), in the data folder (`~/.local/share/radar/`,
`%LOCALAPPDATA%\radar` on Windows):

| Item | Back it up? |
| --- | --- |
| `radar.db` (offers, profile, applications, conversations, memory) | Yes, **as a snapshot from `radar backup`**, never the live file with its `-wal`/`-shm` |
| `cv_master.json`, `photo.jpg`, `targets/`, `cvs/`, `careers/` | Yes (your real CV and generated files) |
| `secrets.json` (provider keys) | **No.** Keys are re-enterable; keeping them out of copies avoids leaking them |
| `backups/`, old `*.bak*` copies | These are the copies, not originals; prune the old manual ones |

`radar backup` (also the last step of every refresh) writes a consistent copy to `backups/` and keeps the last 5. That
folder is on the **same disk**, so it protects against mistakes, not against losing the machine. For a real backup copy
`backups/` plus the CV files to another place: an external drive, or a cloud folder through an encrypted remote
(`rclone` with a `crypt` remote) because the data is personal. A mirror of `~/Documents` does not include this folder. The
installer's uninstaller never deletes the data folder. A backup/restore screen and a JSON/CSV export are planned for v1.0.

## Verification

```bash
.venv/bin/ruff check && .venv/bin/pytest && git diff --check
cd frontend && npm run lint && npm test && npm run build
```

Manual logical backup: `sqlite3 ~/.local/share/radar/radar.db ".backup '/path/radar-$(date +%F).db'"`. Include
`cv_master.json`, `targets/`, `photo.jpg` and `careers/` in any backup. Do not edit the schema by hand; see
[database.md](database.md).
