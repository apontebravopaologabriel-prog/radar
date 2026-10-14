# Changelog

## 1.0.1 — 2026-10-14

### Security
- Frontend dependencies updated so `npm audit --omit=dev` reports 0 vulnerabilities: Next.js 16.4.0 (brings a patched
  PostCSS and `sharp`) and MapLibre GL 6.14.0 (a critical advisory). The map import changed to the namespace form MapLibre 6 requires.
- Personal name removed from tests and docs; the README no longer embeds a screenshot hosted on GitHub.


## 1.0.0 — 2026-10-14

First stable release: a local-first career tool built around your own CV.

### Added
- **Postulaciones:** a tab in the offer tray (✓) and a full-screen view with your applications by status, files per
  application, notes, follow-up nudges after 7 days, and a way to undo a mistaken "applied" (`DELETE /api/applications/{id}`).
  Radar only records; it never applies for you.
- **Chat links:** the job title in the agent's answers opens that offer in the map detail (`radar:job:<id>`,
  `GET /api/jobs/{id}`); a `portal ↗` link goes to the original posting.
- Icon actions in the offer detail (pencil = CV Studio, check = applied).
- CV Studio, application packages, Systems/Software pack, automatic context compaction, MCP "Connect an AI client"
  (all from 0.9).

### Changed
- The agent answers offers as a numbered list (never a table), shorter, and asks for independent tools in one step.
  `search_saved_jobs` returns `url` and `relevance_score`.
- Chat tables scroll horizontally and keep readable columns in narrow panels.

### Security
- The interface context sent to the agent (it contains third-party offer text) is clipped in length, depth and total
  size and stripped of control characters before it reaches the system prompt.
- Chat history is capped (60 000 characters per message, 600 000 in total) and never accepts a `system` role.
- The agent is told never to build URLs or copy them from offer text, and to flag instructions found in postings.
- External links in the chat show their real destination on hover.

### Fixed
- HTTP 400 "Messages with role 'tool' must be a response to a preceding message with 'tool_calls'" after reopening a
  long conversation: the saved history was cut mid-turn. Fixed on the client (cut at a user message) and on the server
  (`sanitize_history`).

See [KNOWN-ISSUES.md](KNOWN-ISSUES.md) for what 1.0.0 does **not** do yet.
