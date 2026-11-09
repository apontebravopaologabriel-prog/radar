# MCP server (optional)

Radar works fully on its own with the integrated agent ([agent.md](agent.md)). The MCP server is an optional
door for people who prefer an external agent (Claude Code, Antigravity, Hermes, any MCP client). It exposes
a curated, high-cohesion subset of the registry (`MCP_TOOLS` in `src/radar/tools_registry.py`, 22 tools) over stdio (`radar-mcp`, FastMCP), omitting UI-only tools, duplicate aliases and unconfirmed system writes (see "Same as the in-app agent?" below). Nothing
is registered or exposed unless you configure a client.

An external agent can combine Radar with other MCP servers (calendar, mail, notes); the integrated agent cannot.

## Connect a client (one step)

Settings → **Conectar IA** shows, per client (Claude Desktop, Claude Code, Cursor, Gemini CLI), the exact JSON to paste
or the exact command, and can write it for you after an explicit confirmation. The same from the terminal:

```bash
radar mcp config                     # prints every snippet and config path
radar mcp install claude_desktop     # also: cursor, gemini_cli
```

`install` merges Radar into the client's `mcpServers` without touching other servers, saves the previous file as
`<name>.radar-bak`, writes atomically and refuses files that are not valid JSON. Claude Code has no config file to edit:
copy its `claude mcp add ...` command. Restart the client afterwards. Endpoints: `GET /api/mcp/config`,
`POST /api/mcp/install` (closed client list). In the packaged app the command points to `radar-mcp.exe` next to
`Radar.exe`. Config file locations used: Claude Desktop (`%APPDATA%\Claude\claude_desktop_config.json` on Windows,
`~/Library/Application Support/Claude/` on macOS, `~/.config/Claude/` on Linux), Cursor `~/.cursor/mcp.json`, Gemini CLI
`~/.gemini/settings.json`; verify them against each client's current documentation.

## Manual configuration

Command (adjust the path to your installation): `/path/to/Radar/.venv/bin/radar-mcp`

```json
{
  "mcpServers": {
    "radar": {
      "command": "/path/to/Radar/.venv/bin/radar-mcp",
      "cwd": "/path/to/Radar"
    }
  }
}
```

The process needs read/write access to the SQLite file and its folder (target CVs, `cv_master.json`).

| Client | Setup |
| --- | --- |
| Claude Code | `claude mcp add radar -- /path/to/Radar/.venv/bin/radar-mcp` |
| Antigravity | Add the block to `~/.gemini/config/mcp_config.json` and reload servers (`Additional Options > MCP Servers`) |
| Hermes / others | Paste the JSON block into the client's server config |

Also copy the generated skill (`radar skill export --out docs/skills` → `docs/skills/radar/SKILL.md`) so the
client knows when and how to use each tool; it is the always-current tool list (name, read/write, parameters).
Reload the client's MCP server after Radar gains tools.

## What it publishes

- **Tools:** the registry. Group overview in [agent.md](agent.md#tools-62-in-the-registry-49-in-the-chat-20-that-write).
- **Resources:** `radar://topics`, `radar://help/{topic}`, `radar://schema`.
- **Prompts:** `configurar_radar`, `analizar_mercado`, `plan_de_aprendizaje`.
- **Transport:** stdio by default (`RADAR_MCP_TRANSPORT`).

## Same as the in-app agent?

Same registry and same functions, with these differences:

| | In-app agent | MCP server |
| --- | --- | --- |
| Tools | 50 (with on-demand groups) | **22 curated tools (`MCP_TOOLS`)**: focused on 1-call War-Room (`get_interview_dossier`), offer triage (`get_today_feed`, `search_saved_jobs`, `find_jobs_near`, `get_job_details`, `compare_jobs`), tracking (`track_job_application`, `favorite_job`, `list_job_applications`, `import_job_url`), CV & gap closure (`get_my_cv`, `update_cv`, `update_profile_fields`, `get_closure_plan`, `close_gap`, `prepare_application`), market analytics (`get_market_breakdown`, `get_skill_demand`, `get_salary_stats`, `get_place_profile`, `run_readonly_sql`) and `health`. UI-coupled tools (`get_help`, `get_setup_status`, `cv_doc_*`, chat memory) and duplicate aliases (`build_cv`, `explain_job_fit`, `get_user_profile`, `plan_learning`) are omitted to maximize tool-selection accuracy and minimize round-trips |
| Not exposed in either | `ingest_jobs`, `capture_market_history`, `update_profile`, `save_target_profile` (writes that skip the confirmation card; CLI and onboarding only) | |
| Writes | Always a confirmation card; none in plan or read-only mode | **Run directly**, with no card. Only Radar's read-only setting (`agent_read_only`) blocks them, plus whatever approval the client asks for |
| Tool loading | `cv`, `perfil`, `sistema` groups load on demand | All tools visible at once (heavier for the client's context) |
| Rules and persona | System prompt, persona, memory, screen context, auto-compaction | None: the client needs the generated skill (`docs/skills/radar/SKILL.md`). The CV fact guard is code, so it holds for every client |
| Extras | Studio panel, suggestions UI | Resources and prompts |

Write tools exposed through MCP: `update_cv`, `update_profile_fields`, `close_gap`, `favorite_job`, `track_job_application`,
`record_career_event`, `remember_user`, `set_career_track`, `create_career_pack`, `set_refresh_schedule`, `run_maintenance`,
`set_score_weights`, `reclassify_jobs`, `refresh_market`, `build_cv`, `prepare_application`. Turn on Radar's read-only mode, or make the
client ask before each call, when connecting an agent you do not fully trust. `cv_doc_propose` creates suggestions, not changes: the
person accepts them in the Studio.

## Tools worth knowing

| Tool | Notes |
| --- | --- |
| `health()` | Availability check; changes nothing |
| `get_market_summary()` | Active total, primary areas, frequent skills |
| `list_recommended_jobs(limit=10, max_age_days=14)` | Active, dated, within range, with link, date, mode, sector, salary, hours; needs a profile. LinkedIn offers additionally need `application_status=open` and a recent check |
| `get_job_history(job_id, limit=20)` | Time series of one offer |
| `list_targets()`, `get_target_context(job_ids)`, `get_target_matrix()`, `resolve_nearest_districts(reference, limit=3)` | Read-only target CV data: [cv.md](cv.md#mcp-tools) |
| `get_interview_dossier(query_or_job_id)` | Single-call interview prep dossier (searches active, applied and hidden offers up to 365 days; returns offer details, fit, deterministic baseline gap, tailored CV selection and `cv_master.json`) |

`search_saved_jobs(limit, seniority, area, max_age_days=14, search, sector, exclude_sector)` excludes hidden
offers and returns a description excerpt. `run_readonly_sql` accepts only a single `SELECT`/`WITH` (max 50 rows).
LinkedIn, Bumeran, Laborum and Empleos Perú enter through CSV/JSON import, never through account automation.

## Policy for external agents

An external agent must: declare source and filters, distinguish `NULL` from confirmed data, respect scores and
evidence, and ask the person before writing (profile, CV, timer, maintenance, reclassification, weights). There
are no tools to apply to jobs or send messages. Do not expose the stdio server over a network without
authentication.
