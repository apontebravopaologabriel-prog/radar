# Design: automatic context summarization

Status: **implemented** (v0.9, `agent/loop.py`: `should_autocompact`, `split_for_compaction`, `run_turn(last_prompt_tokens=...)`; event `compacted`; setting `agent_autocompact_pct`, optional `agent_summary_model`). Before it, compaction was manual: `/compact [focus]` calls `loop.compact()` (one LLM call,
350-word bullet summary) and the UI warns at 70 % context; old tool results are already cut to 700 characters
(`_trim_old_tool_results`). Nothing triggers by itself, so a long session ends in an error or a degraded model.

## How similar agents do it

| Tool | Trigger | What it keeps | Lesson for Radar |
| --- | --- | --- | --- |
| Claude Code | Auto near the limit (about 95 % by default, configurable; many recommend 60–70 %), plus manual `/compact` with focus instructions | Human-readable summary of goals, decisions, relevant tool outputs, current state; three tiers: micro-compaction of bulky tool results, auto, manual | Compact early; keep persistent rules outside the summary (CLAUDE.md ↔ Radar memory) |
| Codex CLI | Token threshold (about 167K of 200K), lowered by config | Session memory first, opaque server-side compression if insufficient; re-reads recent files after | Avoid LLM calls when a cheap structure is enough; a bad trigger can double the cost |
| OpenCode | Model-driven compress tool at task boundaries | Prunes irrelevant tool outputs, keeps about 40K tokens of recent messages, nests overlapping summaries | Keep a verbatim tail; prune before summarizing; protect recent context |

Sources: [Claude Code auto-compact](https://www.morphllm.com/claude-code-auto-compact), [context compaction
comparison of Codex CLI, Claude Code and OpenCode](https://codex.danielvaughan.com/2026/04/14/context-compaction-deep-dive-codex-cli-claude-code-opencode/),
[auto-compact overview](https://www.promptlayer.com/glossary/auto-compact).

Summaries are lossy by design. The mitigation is to move durable facts to memory and to keep the raw
conversation in the database.

## Design for Radar

Three tiers, cheapest first:

1. **Prune (exists):** old tool results cut to 700 characters. Extend: drop `thinking`/`reasoning` of old turns
   and collapse repeated identical tool calls.
2. **Auto-compact (new):** at the start of `run_turn`, if the last real `prompt_tokens` (from provider usage,
   not an estimate) exceeds `agent_autocompact_pct` of `context_window` (default 65 %, setting 40–90, 0 = off),
   summarize everything except the last 4 user turns (verbatim tail). Never in the middle of a tool-call pair
   or while a confirmation is pending; if the summary call fails, fall back to tier 1 and warn.
3. **Manual (exists):** `/compact [focus]` uses the same code path.

Mechanics:

- The server emits `{"type": "compacted", "summary": ..., "kept_from": n, "before_pct": 71, "after_pct": 19}`.
  The client replaces the sent history with `[summary, ...tail]` and shows one line
  `▸ context compacted 71% → 19%` (expandable to read the summary; `Esc Esc`/rewind restores the full history).
- **Structured prompt** (replaces the free bullets): goal and constraints; decisions taken; data obtained with
  source tool and date; offer ids and places mentioned; open questions and next step; user preferences stated
  (candidates for memory). Max about 350 words, Spanish, nothing invented.
- **Durable facts go to memory:** the summarizer returns `memory_candidates`; they are shown as normal
  `remember_user` confirmation cards (never saved silently).
- **Nested summaries:** a second compaction summarizes `[previous summary + new turns]` instead of stacking
  summaries.
- **Raw history is never lost:** `conversations` keeps the full text; `search_past_conversations` still finds
  it. The summary is stored as a marked message with the index of the first kept message.
- **Cost control:** optional `agent_summary_model` (cheap model) for the summary call; its tokens are recorded
  in `agent_usage`; the monthly cap is checked first (as `compact()` does today).
- **Deterministic, not silent:** thresholds are code and settings; the model only writes prose. The summary is
  data for the next turn and is never used to decide scores or levels.

## Implementation notes

- The client sends `last_prompt_tokens` (the provider-reported size of the last prompt) with every chat request; the server never guesses.
- Tail = last 4 user turns (`KEEP_TAIL_TURNS`), always starting at a user message, so tool-call pairs are never split. Needs at least 4 messages to summarize (`MIN_HEAD_MESSAGES`).
- On failure the server emits `notice` and continues with pruning only.
- `memory_candidates` come from the `PREFERENCIAS` section of the summary and are shown to the person with a `# text` hint; nothing is saved automatically.
- Settings: `agent_autocompact_pct` (default 65; 0 off; clamped 20–90), `agent_context_window` (default 64 000), `agent_summary_model`.
- Not yet built: retention eval in `scripts/agent_eval.py`, "restore full history" from the compaction line.

## Tests

- Unit (simulated provider): triggers at the threshold, not below; keeps the tail; no trigger during pending
  confirmation; failure falls back to pruning; second compaction nests.
- Retention eval (extend `scripts/agent_eval.py`): plant 5 facts (ids, a decision, a preference) early in a long
  conversation, force compaction, ask about each; target at least 4 of 5 recalled.
- Cost check: tokens per turn after compaction fall below the pre-compaction value in the same conversation.

## Out of scope for now

Server-side opaque compression (provider specific), model-driven "compress" tool, sub-agent delegation (v1.4).
