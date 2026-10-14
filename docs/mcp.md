# MCP server (optional)

Radar works fully on its own with the integrated agent ([agent.md](agent.md)). The MCP server is an optional
door for people who prefer an external agent (Claude Code, Antigravity, Hermes, any MCP client). It exposes
the same registry (`src/radar/tools.py`, 62 tools, 20 write tools) over stdio (`radar-mcp`, FastMCP). Nothing
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

Command (adjust the path): `/home/paolo/Projects/Radar/.venv/bin/radar-mcp`

```json
{
  "mcpServers": {
    "radar": {
      "command": "/home/paolo/Projects/Radar/.venv/bin/radar-mcp",
      "cwd": "/home/paolo/Projects/Radar"
    }
  }
}
```

The process needs read/write access to the SQLite file and its folder (target CVs, `cv_master.json`).

| Client | Setup |
| --- | --- |
| Claude Code | `claude mcp add radar -- /home/paolo/Projects/Radar/.venv/bin/radar-mcp` |
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

## MCP-only tools worth knowing

| Tool | Notes |
| --- | --- |
| `health()` | Availability check; changes nothing |
| `ingest_jobs(source, query, location="Lima", limit=25, max_age_days=14)` | Fetch, classify, deduplicate and save only dated, recent offers. Operational limit 100 |
| `get_market_summary()` | Active total, primary areas, frequent skills |
| `list_recommended_jobs(limit=10, max_age_days=14)` | Active, dated, within range, with link, date, mode, sector, salary, hours; needs a profile. LinkedIn offers additionally need `application_status=open` and a recent check |
| `get_job_history(job_id, limit=20)` | Time series of one offer |
| `capture_market_history(snapshot_date=null)` | Store market metrics |
| `list_targets()`, `get_target_context(job_ids)`, `save_target_profile(job_id, profile)`, `get_target_matrix()`, `resolve_nearest_districts(reference, limit=3)` | Target CV workflow: [cv.md](cv.md#mcp-tools) |

`search_saved_jobs(limit, seniority, area, max_age_days=14, search, sector, exclude_sector)` excludes hidden
offers and returns a description excerpt. `run_readonly_sql` accepts only a single `SELECT`/`WITH` (max 50 rows).
LinkedIn, Bumeran, Laborum and Empleos Perú enter through CSV/JSON import, never through account automation.

## Policy for external agents

An external agent must: declare source and filters, distinguish `NULL` from confirmed data, respect scores and
evidence, and ask the person before writing (profile, CV, timer, maintenance, reclassification, weights). There
are no tools to apply to jobs or send messages. Do not expose the stdio server over a network without
authentication.
