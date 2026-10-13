# Troubleshooting

## Data

| Symptom | Cause and fix |
| --- | --- |
| Database missing or empty | SQLite is created on first connection at `~/.local/share/radar/radar.db` (or `RADAR_DB_PATH`) with the full schema. If tables or catalog entries are missing, reconnect: `_ensure_runtime_schema()` re-applies them. See [database.md](database.md) |
| No recommendations | Set a profile (`radar profile` or Settings). Recommendations use `job_scores`, recalculated when the profile is saved |
| Unexpected duplicates | The fingerprint is normalized company + title + location; two different posts can share it. Source appearances are kept and nothing is deleted automatically |
| Area or district counts look odd | Ask the agent to run `audit_classification`; if stale it proposes `reclassify_jobs` (confirmation + reversible copy) |
| JobSpy returns incomplete data | Each portal limits fields. Salary, date, description or URL may be missing; Radar keeps `raw_payload` and stores `NULL` |

## Ingestion

| Symptom | Cause and fix |
| --- | --- |
| Computrabajo returns nothing | Use a shorter query, confirm `location=Lima`, check Node.js/npm, and that `npx mcp-computrabajo@latest` starts by itself |
| JobSpy does not install | `pip install -e '.[jobspy]'` in the main environment (imports verified on 3.14). If NumPy 1.26.3 fails to build on your Python, use a separate Python 3.12 environment |
| Refresh did not run | Linux with the timer: `systemctl --user status radar-refresh.timer`. Otherwise the in-process scheduler only runs while Radar is open: check Settings or `get_system_status` (next/last run) and `refresh.log` in the state folder (`~/.local/state/radar/refresh.log` on Linux); its final summary lists failed steps |

## Interface

| Symptom | Cause and fix |
| --- | --- |
| Map shows a WebGL error | MapLibre needs WebGL2. The frontend switches to `LeafletMapView` automatically; reload `/radar`. If it persists, check the browser console and `http://127.0.0.1:8100/api/health` |
| Not opening as a Chromium app | The launcher must run Chromium with `--app`, not `xdg-open`. Validate with `desktop-file-validate ~/.local/share/applications/radar.desktop` and `gtk-launch radar`. Close a window left in another browser and relaunch. Logs: `~/.local/state/radar/` |
| Interface does not load | FastAPI serves `frontend/out` on port 8100 (the launcher no longer uses the Next.js server). Rebuild with `cd frontend && npm run build`, check `frontend.log`, confirm `/radar` answers after `/api/health` |
| Explorer bottom hidden | The sidebar has its own scroll. During `npm run dev`, hard-reload. On small screens the offer list also scrolls internally |
| New route returns 404, new tool missing | The API runs old code. The launcher restarts it when `.py` files changed; otherwise restart manually ([operations.md](operations.md#desktop-launcher)), reload the external MCP server, and reload the page |
| Everything returns 401 | `RADAR_ACCESS_TOKEN` is set: sign in on the login screen of `/radar`, `/ajustes` or `/m` |
| Everything returns 403 `Host no permitido` | You reached the API through a name that is not allowed. Add it to `RADAR_ALLOWED_HOSTS` (or bind with `RADAR_API_HOST`) |

## CVs view

| Symptom | Cause and fix |
| --- | --- |
| "La API respondió 404" on `/api/cv/*` | The API runs old code; restart it |
| "Perfil real no cargado" | `cv_master.json` is missing next to the database. Without `targets/*.json` the view says there are no target CVs |
| No photo | Expected `photo.jpg` (or `photo.png`) in the data folder; upload from Settings |
| `save_target_profile` returns `errors` | Schema needs `quote` or `reason` on explicit items, `reason` on inferred and `cubierto` items, and valid `origin`, `status`, `kind` |
| PDF has odd characters | No TrueType font was found and Helvetica (Latin-1) was used. Install Calibri/Arial/DejaVu or point `RADAR_PDF_FONT` to a folder with `regular.ttf`, `bold.ttf`, `italic.ttf` |

## Agent

| Symptom | Cause and fix |
| --- | --- |
| "alcanzó el máximo de pasos" | A turn has 8 steps. The question probably needs SQL: try `get_market_breakdown` with filters (area, place, sector, `exclude_sector`, text) or `/plan` |
| Cannot save CV, timer or maintenance changes | Check the footer. `read-only` or `plan` mode offers no write tools: `/readonly off`, and leave plan with `Shift+Tab` or `/plan off` |
| `Shift+Tab` shows nothing | The footer shows the mode (`manual`, `auto`, `plan`) and, separately, `· read-only` |
| Chat refuses | The agent is off (Settings → Agent) or the monthly token cap was reached |
| Provider errors | 401 bad key, 402 no credit, 429 rate limit; transient failures (network, 429, 5xx) are retried once; bad key or no credit show a clear message |
