---
name: bridge-builder-delegate
description: Delegate implementation work to the bridge-builder MCP server.
  Use when a request should be executed by the bridge-builder pipeline
  instead of being implemented directly in the current Codex thread.
---

Use this skill when the `bridge-builder` MCP server should perform the
implementation instead of the current Codex thread.

Requirements:

- The `bridge-builder` MCP server is available in the host.
- Unless the user provides a repository path, treat the current working
  directory as the target repository when using `run_pipeline`.

Workflow:

1. Rewrite the user request into a concise implementation request for the MCP
   tool.
2. Choose the tool:
   - Use `run_here(request)` when a default repository is configured or the
     user explicitly wants the server's configured repository.
   - Use `run_pipeline(request, repo_path)` otherwise.
3. Execute the MCP tool.
4. If `run_here` fails because no default repository is configured, retry with
   `run_pipeline(request, repo_path)` and the current working directory when
   appropriate.
5. Reply with:
   - resolved repository path
   - implementation summary
   - touched files
   - verification performed
   - remaining risks

Keep the response short and execution-focused.
