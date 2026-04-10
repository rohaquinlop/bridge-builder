---
description: Delegate an implementation task to the bridge-builder MCP server
argument-hint: [implementation request]
---

Use the `bridge-builder` MCP server to delegate this implementation task:

$ARGUMENTS

Execution rules:

- Treat the arguments as the full implementation request.
- Prefer `run_here(request)` when the server is configured with a default
  target repository.
- Otherwise call `run_pipeline(request, repo_path)` and use the current
  working directory as `repo_path` unless the user explicitly names a
  different repository path.
- If `run_here` fails because no default repository is configured, retry with
  `run_pipeline` and the current working directory when appropriate.

Report back with:

- resolved repository path
- implementation summary
- touched files
- verification performed
- remaining risks
