# Repository Guidelines

## Project Structure & Module Organization

This repository is intentionally small. `main.py` contains the full FastMCP server, including MCP tools, repository analysis, Codex subprocess orchestration, prompt auditing, and post-verification hooks. `README.md` explains installation and host setup. `pyproject.toml` defines the package metadata and dependency on `fastmcp`, while `uv.lock` pins the environment. Runtime prompt history is written to `.agent_prompts/` and is ignored by Git by default.

## Build, Test, and Development Commands

- `uv sync`: install project dependencies into the local environment.
- `uv run python main.py`: run the MCP server over stdio.
- `uv run bridge-builder`: run via the configured script entrypoint.
- `python3 -m py_compile main.py`: quick syntax check with the system interpreter.
- `uv run python -m py_compile main.py`: syntax check inside the project environment.
- `uv run python - <<'PY' ... PY`: use for focused helper validation during development.

## Coding Style & Naming Conventions

Use Python 3.12+ features already present in the codebase, including type hints and standard-library parsers such as `tomllib`. Follow 4-space indentation and keep helpers small and single-purpose. Internal functions should use a leading underscore, for example `_build_repo_context` or `_post_verify`. Add new environment-based settings as uppercase module constants near the top of `main.py`.

## Testing Guidelines

There is no formal test suite yet. At minimum, run both compile checks before committing. When changing parsing, ranking, or verification logic, add targeted `uv run python - <<'PY' ... PY` probes against the specific helper or a temporary repository. If a `tests/` directory is added later, prefer unit tests around manifest parsing, symbol extraction, and pipeline behavior.

## Commit & Pull Request Guidelines

Current history uses short imperative commit messages such as `Build bridge-builder MCP server` and `Harden pipeline verification and prompt auditing`. Follow that style. Pull requests should summarize the behavior change, note any new environment variables or verification hooks, and include example tool inputs or outputs when user-facing behavior changes.

## Security & Configuration Tips

This server executes `codex` subprocesses and optional local verification commands. Keep post-verification conservative by default, and only enable package-script verification for trusted repositories. Avoid hardcoding machine-specific paths; prefer environment variables and documented MCP host config.
