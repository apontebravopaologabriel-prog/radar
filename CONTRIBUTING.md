# Contributing to Radar

Thank you for your interest in contributing to Radar! Radar is a local-first Career Intelligence application built with FastAPI, Next.js, and SQLite.

## Code of Conduct & Principles

- **Local-first & Privacy:** User data belongs to the user. Never introduce telemetry, external tracking, or cloud sync without explicit opt-in.
- **Traceable Scoring:** Radar never uses non-deterministic LLM calls to silently decide match scores, competency levels, or job validity.
- **Cross-platform:** Code must run reliably on Linux and Windows. Guard POSIX-specific system calls with `os.name`.

## Getting Started

### Prerequisites

- Python 3.11, 3.12, or 3.14
- Node.js 20+ and npm

### Local Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/apontebravopaologabriel-prog/radar.git
   cd radar
   ```

2. **Backend setup:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e '.[dev]'
   ```

3. **Frontend setup:**
   ```bash
   cd frontend
   npm ci
   npm run build
   cd ..
   ```

4. **Run the local server:**
   ```bash
   .venv/bin/radar-api
   # Open http://127.0.0.1:8100/radar in your browser
   ```

## Running Tests and Verification

Before submitting a Pull Request, ensure all tests and linters pass:

```bash
# Backend tests & lint
.venv/bin/pytest
.venv/bin/ruff check

# Frontend tests & lint
cd frontend
npm run lint
npm test
npm run build
cd ..

# Check git diff for whitespace / artifacts
git diff --check
```

If you add or modify MCP / Chat tools in `src/radar/tools.py`, regenerate the skill export:
```bash
.venv/bin/radar skill export --out docs/skills
```

## Pull Request Guidelines

1. Create a feature branch from `main`.
2. Keep commits atomic and descriptive.
3. Ensure no personal credentials or absolute paths are included in code or tests.
4. Update documentation in `docs/` and `help.md` when introducing user-facing changes.
5. Open a Pull Request with a clear description of the problem and the solution.
