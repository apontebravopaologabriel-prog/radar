# Chat agent

Reference for the in-app agent: identity, tools, modes, interface, memory and limits. The agent shares its
tool registry (`src/radar/tools.py`) with the MCP server, so an external agent can do the same things (see
[mcp.md](mcp.md)). It is optional and off by default; when off the server rejects `/api/chat*` with 403
`agent_disabled`, no code is loaded and no provider is contacted.

## Identity

The system prompt has two parts: operational rules (`SYSTEM_PROMPT` in `src/radar/agent/loop.py`) and the
persona (`src/radar/agent/soul.md`, packaged with the `radar` package). The persona is a senior industrial and
systems engineer using the **ISE Body of Knowledge (IISE, 2026)** and Peruvian market judgment: direct,
realistic, independent, loyal to the data and to the person's future rather than to agreeing with them.

- Uses the 14 BoK areas under Radar's names (plus `Otras` and `Ventas / Comercial`, out of focus).
- Separates data (tool output) from inference or projection and states its confidence.
- When comparing, always states the criterion (volume, median salary, mode, seniority, area mix).
- Answers a greeting without calling tools; never runs `get_setup_status` or `get_today_feed` on its own.
- Knows the person: name and CV headline are in the prompt; `get_my_cv` gives the full history.
- If classification rules changed since the last reclassification, the prompt adds a notice to run
  `audit_classification` and propose `reclassify_jobs`.
- Replies in Spanish, without announcing what it is about to do.

Change personality in `soul.md`; update `help.md` when something visible changes.

## Tools: 62 in the registry, 49 in the chat, 20 that write

`@tool(write=..., chat=...)` in `tools.py` declares each tool. `write` means a confirmation card; `chat=False`
means MCP only. **On-demand loading:** tools of groups `cv`, `perfil` and `sistema` (`TOOL_GROUPS`) are only
offered after the model calls `load_tools` (a loop meta-tool, not in the registry). Loaded groups are
remembered from the history; calling an unloaded tool returns a notice. A new tool with no group is always
available, so put heavy, rarely used tools in a group.

| Group | Tools |
| --- | --- |
| Market and offers | `search_saved_jobs`, `get_today_feed`, `find_jobs_near`, `get_job_details`, `explain_job_fit`, `compare_jobs`, `get_skill_demand`, `get_market_breakdown` (by area, place, company, work mode, seniority, sector or portal), `get_place_profile`, `compare_places`, `get_salary_stats`, `plan_learning`, `get_market_history`, `get_data_schema`, `run_readonly_sql`. MCP only: `get_market_summary`, `list_recommended_jobs`, `get_skill_impact`, `get_job_history`, `health` |
| Profile, CV, memory | `get_my_profile`, `update_profile_fields`\*, `get_user_profile`, `get_my_cv`, `update_cv`\*, `get_user_memory`, `remember_user`\*, `search_past_conversations`, `get_career_timeline`, `record_career_event`\*, `list_career_tracks`, `set_career_track`\*, `create_career_pack`\* |
| Closure plan, CV studio and application packages | `get_closure_plan`, `close_gap`\*, `preview_cv`, `build_cv`\* (legacy), `cv_doc_get`, `cv_doc_propose` (creates suggestions the person accepts in the Studio; nothing changes until then), `prepare_application`\* (exports the PDF/Word to the offer's folder; never submits), `list_application_packages` |
| Tracking | `favorite_job`\*, `track_job_application`\*, `list_job_applications` |
| Capture and system | `refresh_market`\*, `get_refresh_status`, `get_system_status`, `set_refresh_schedule`\*, `run_maintenance`\*, `set_score_weights`\*, `audit_classification`, `reclassify_jobs`\*, `get_setup_status`, `get_help`. Not exposed to chat or MCP (CLI/onboarding only): `ingest_jobs`, `capture_market_history` |
| Target CVs (MCP only, read-only) | `get_target_context`, `list_targets`, `get_target_matrix`, `resolve_nearest_districts` |

\* writes: the chat shows a card and runs it only after approval. `update_profile` (full replacement) and `save_target_profile` exist
only for onboarding and the CLI; neither the chat nor the MCP server exposes them (the app agent uses `update_profile_fields`).

Design decisions:

- **Shortest path:** direct tools first. `run_readonly_sql` is the last resort, 2 attempts, and its errors
  include the schema so no step is spent on `get_data_schema`.
- **No limits that break the answer:** at most 8 steps per turn; the last step removes the tools. An identical
  repeated query is cut. Large results are trimmed per item (always valid JSON); older turns keep an excerpt.
- **Format and speed:** the prompt asks for offers as a numbered list with the title as a link to the portal (never a table; tables only for 2-4 short columns), the title being an internal link `radar:job:<id>` that opens the offer in the map detail (`Markdown.tsx` dispatches `radar:open-job`; `RadarClient` handles it, fetching `GET /api/jobs/{id}` when the offer is not in the current lists) plus a `[portal ↗]` link to the original, 5 offers by default, ~120 words, and independent tools in the same step. `search_saved_jobs` returns `url` and `relevance_score`, so ranking offers needs no `get_job_details` per offer.
- **Light tools:** `search_saved_jobs` returns a description excerpt; the full card is `get_job_details`.
- **Not changeable by the agent:** API key, read-only mode and token cap (the person changes them in Settings).
  It never applies to jobs or sends messages.

## Modes

`Shift+Tab` cycles three modes shown in the footer:

| Mode | Behavior |
| --- | --- |
| `manual mode on` | Every action that changes data asks for confirmation |
| `auto mode on` | Auto-approves only personal tracking: `favorite_job`, `track_job_application`, `remember_user`, `record_career_event`. System, CV, profile, weights, capture and reclassification still ask |
| `plan mode on` | The server offers no write tools and rejects any call. The agent researches and ends with a numbered plan; a card approves it (`1`) or keeps planning (`2`); approving leaves plan mode and executes step by step |

`/plan [goal]` enters plan mode (with a goal it sends it at once), `/plan off` leaves. The persistent
**read-only** setting (`/readonly`, Settings) always removes write tools and shows `· read-only` in the footer.

## Interface

Floating window (`Ctrl+J`) or panel pinned right on desktop; `Agent` tab on mobile. Terminal look (12 px text,
square corners, hidden scrollbars, Claude Code style colors). The empty conversation shows a banner with the
mark, version, model, career and active offers. The top bar shows the conversation title (click or `/rename`).

| Key | Action |
| --- | --- |
| `Enter` / `Shift+Enter` | Send / newline (also `\` + Enter) |
| `/` · `Tab` · `↑↓` | Commands, autocomplete, choose |
| `@` | Mention a district, city or offer; the message carries the explicit list |
| `↑` (empty) / `Ctrl+R` | Recall / search earlier messages |
| `Esc` / `Esc Esc` | Stop the answer / go back to edit your last message |
| `Shift+Tab` | Mode: manual → auto → plan |
| `Ctrl+K` | Screen context: off → selection → full |
| `Ctrl+O` | Show or hide full tool output |
| `Ctrl+C` | Stop; with an empty field, twice closes |
| `PgUp` / `PgDn` | Scroll the conversation |
| `1` `2` `3` | Approve / approve always (session) / reject (`y`, `n` also work) |
| `#` text | Save to memory |
| `?` (empty) | Shortcuts window |

### Commands

Names follow Claude Code, with Spanish aliases. `local` commands use the API and spend no tokens
(`COMMANDS` in `frontend/components/agent/commands.ts`).

- Temporary window (closes with `Esc`, not part of the conversation): `/help`, `/keys`, `/status`, `/doctor`,
  `/tools`, `/context`, `/cost`, `/profile`.
- Short notice: `/copy`, `/export`, `/pin`, `/readonly`, `/refresh`, and `/model` or `/effort` with an argument.
- Answer in chat: `/today`, `/map`, `/pipeline`, `/skills`, `/compact`, `/memory`.
- Pickers: `/model` and `/effort` share one (`↑↓` model, `←→` effort: `auto`, `none`, `low`, `high`, `max`;
  `Enter` applies); `/resume` lists conversations (type to filter by title or content, `Enter` opens, `Ctrl+D`
  deletes after confirmation).
- `/plan` (plan mode), `/delete todo` (needs `/delete todo confirmar`), `/rename`, `/clear` (`/new`).
- Ask the model: `/init`, `/explain`, `/learn`, `/summary`.

### Screen context

The agent receives view (`map`, `analysis`, `cvs`), map mode, district and radius (with the district's own
count `districtJobs`), filters, open offer and result counters; Analysis adds a summary of its windows.
`Ctrl+K` chooses how much is sent: **off**, **selection** (default; no SQL or analysis rows) or **full**. It is
treated as navigation data, used silently and never quoted. `@` mentions always travel and take priority.

## Automatic context summarization

When the last prompt reported by the provider exceeds `agent_autocompact_pct` (default 65 %, 0 = off) of the context
window, the server summarizes everything except the last 4 user turns and emits a `compacted` event with the
new history; the UI shows the summary and any preference candidates to save with `#`. Old tool results are also
cut to 700 characters. Manual `/compact [focus]` uses the same code. Design and rationale:
[design-auto-compaction.md](design-auto-compaction.md).

## Memory and conversations

- **Durable memory** (`agent_memories`, text search): confirmed preferences, goals and decisions. Saved with
  `remember_user` (confirmation card) or `# text`. The 30 most recent notes go in the prompt; the rest are
  found with `get_user_memory`. No secrets or full conversations.
- **Conversations** (`conversations`): stored in the local database, resumed with `/resume`. The agent searches
  them with `search_past_conversations` (accent-insensitive, returns fragments) only when the person alludes to
  something discussed before.

## CV and profile editing

`update_cv(section, action, item, match)` edits `cv_master.json`, the file the CVs view reads. Sections:
`certifications`, `experience`, `education`, `languages`, `projects`, `contact`, `gaps`, `summary`, `headline`.
Actions: `add`, `update`, `remove`. It validates allowed fields and `YYYY-MM` dates, rejects duplicates and
ambiguous matches, keeps untouched keys, writes atomically and saves `cv_master.json.bak-<date>` (last 5). Only
with what the person dictates. Details: [cv.md](cv.md).

## System and maintenance tools

`get_system_status`, `run_maintenance`, `set_refresh_schedule`, `set_score_weights`, `audit_classification`,
`reclassify_jobs`, `refresh_market`, `get_refresh_status`: behavior in
[operations.md](operations.md#data-maintenance-commands). Everything that writes asks for confirmation, never
deletes offers and leaves a reversible copy when applicable.

## Extending

- **New tool:** a function in `tools.py` with `@tool(write=..., chat=...)`; it shows up in MCP and chat.
  Add it to the table above, regenerate the skill (`radar skill export --out docs/skills`) and add a test in
  `tests/test_tools.py`.
- **New command:** an entry in `COMMANDS` in `commands.ts` (and in `VIEWS` if it opens a window or notice).
- **Personality or rules:** `soul.md` and `SYSTEM_PROMPT`.
- **Quality check:** `scripts/agent_eval.py` runs 17 typical questions against the configured provider in
  read-only mode (spends tokens, recorded in `agent_usage`). Last real run (DeepSeek, 2026-09-20): all 17
  chose the right tool; it refused "apply for me and write the recruiter" and resisted an injected
  instruction. Re-run after changing tools, grouping or prompts.
