# Repository Guidelines

## Project Structure & Module Organization

The repository is intentionally small. [`main.py`](main.py) contains the full FastMCP server, including tool definitions, repository-context extraction, Codex subprocess orchestration, and post-run verification hooks. [`README.md`](README.md) documents setup and host registration. [`pyproject.toml`](pyproject.toml) defines packaging and dependencies, and [`uv.lock`](uv.lock) pins the resolved environment. Generated implementation prompts are stored in `.agent_prompts/` at runtime.

## Build, Test, and Development Commands

- `uv add fastmcp`: add or update dependencies in the project environment.
- `uv run python main.py`: run the MCP server over stdio.
- `python3 -m py_compile main.py`: fast syntax check using the system interpreter.
- `uv run python -m py_compile main.py`: syntax check inside the project environment.
- `uv run python -c 'from main import _build_repo_context; ...'`: ad hoc validation for context-building helpers.

## Coding Style & Naming Conventions

Use Python 3.12+ features already present in the codebase, including type hints and standard-library parsing utilities. Follow 4-space indentation and keep functions focused and small. Prefer private helper names with a leading underscore for internal pipeline logic, for example `_build_repo_context` or `_post_verify`. Keep new configuration flags in uppercase module-level constants sourced from environment variables.

## Testing Guidelines

There is no dedicated test suite yet. For now, validate changes with `python3 -m py_compile main.py` and `uv run python -m py_compile main.py`, then run small `uv run python -c '...'` checks against the specific helper you changed. If you add tests later, place them under `tests/` and prefer focused unit tests around manifest parsing, symbol extraction, and pipeline helpers.

## Commit & Pull Request Guidelines

This repository does not yet have established Git history, so use short imperative commit messages such as `Add manifest-aware post verification`. Pull requests should explain the behavioral change, note any new environment variables, and include example MCP inputs or command outputs when the change affects orchestration or verification behavior.

## Security & Configuration Tips

This server executes `codex` subprocesses and optional local verification commands. Keep post-verification hooks conservative by default, and avoid enabling arbitrary package-script execution unless you trust the target repository. Use environment variables to tune models, reasoning effort, and verification behavior without hardcoding machine-specific settings.
