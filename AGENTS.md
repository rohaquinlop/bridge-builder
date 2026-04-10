# Repository Guidelines

## Project Structure & Module Organization

This repository is intentionally compact. [`main.py`](/Users/rhafid/personal-projects/bridge-builder/main.py) contains the FastMCP server, MCP tool definitions, repository analysis, Codex subprocess orchestration, prompt auditing, and post-verification logic. [`README.md`](/Users/rhafid/personal-projects/bridge-builder/README.md) covers installation, MCP host setup, and runtime behavior. [`pyproject.toml`](/Users/rhafid/personal-projects/bridge-builder/pyproject.toml) defines package metadata, the `bridge-builder` script entrypoint, and dev tooling. [`codex-skills/bridge-builder-delegate/SKILL.md`](/Users/rhafid/personal-projects/bridge-builder/codex-skills/bridge-builder-delegate/SKILL.md) provides the optional Codex skill wrapper. Runtime prompt history is stored under `.agent_prompts/` and should stay out of Git.

## Build, Test, and Development Commands

- `uv sync`: install project and dev dependencies from [`uv.lock`](/Users/rhafid/personal-projects/bridge-builder/uv.lock).
- `uv run python main.py`: start the MCP server over stdio.
- `uv run bridge-builder`: run the same server through the package entrypoint.
- `uv run ruff check .`: run import-order linting configured in `pyproject.toml`.
- `uv run ty check`: run static type checks.
- `uv run python -m py_compile main.py`: quick syntax verification inside the project environment.

## Coding Style & Naming Conventions

Use Python 3.12+ and keep changes compatible with the existing single-module layout. Follow 4-space indentation, add type hints for new helpers, and prefer small focused functions. Use `snake_case` for functions and local variables, `UPPER_CASE` for module constants and environment flags, and leading underscores for private helpers such as `_post_verify`. Keep Ruff’s 80-character line target in mind.

## Testing Guidelines

There is no dedicated `tests/` directory yet, so every change should at least pass lint, type checks, and `py_compile`. For logic changes, add a focused probe with `uv run python - <<'PY'` against the affected helper or run the server locally and exercise the relevant MCP path. If you add formal tests later, place them under `tests/` and mirror the behavior-oriented naming used by the runtime code.

## Commit & Pull Request Guidelines

Recent commits use short imperative subjects, for example `Add linting and typing checks`. Follow that pattern and keep each commit scoped to one change. Pull requests should explain the behavior change, note any new environment variables or verification hooks, and include concrete examples when tool inputs or outputs change.

## Security & Configuration Tips

This server launches `codex` subprocesses and can run local verification commands against target repositories. Keep verification conservative, avoid hardcoded machine-specific paths, and prefer environment variables such as `BRIDGE_BUILDER_DEFAULT_REPO` for configuration.
