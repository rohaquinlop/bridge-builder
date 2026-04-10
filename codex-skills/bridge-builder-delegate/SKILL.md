---
name: bridge-builder-delegate
description: Delegate an implementation request to the bridge-builder MCP
    server against the current repository or a configured default repository.
---

# Bridge Builder Delegate

Use this skill when a request should be delegated to the `bridge-builder` MCP
server instead of being implemented directly in the current Codex thread.

## Preconditions

- The `bridge-builder` MCP server is registered in the host.
- Prefer `run_here(request)` when the server is configured with
  `BRIDGE_BUILDER_DEFAULT_REPO`.
- Otherwise call `run_pipeline(request, repo_path)` and use the current Codex
  session working directory as `repo_path` unless the user specifies another
  repository.

## Workflow

1. Convert the user's request into a concise implementation request suitable
   for the MCP tool.
2. Decide which tool to call:
    - Use `run_here(request)` when the default repository is configured or the
      user explicitly wants the server's configured target repository.
    - Use `run_pipeline(request, repo_path)` when the target repository should
      be the current session repository or a path provided in the request.
3. Execute the MCP tool.
4. Report back:
    - resolved repository
    - generated implementation summary
    - touched files
    - verification performed
    - remaining risks

## Response Guidance

- Keep the reply short and execution-focused.
- If the MCP call fails because no default repository is configured, retry
  with `run_pipeline` and the current session working directory when
  appropriate.
- If the target repository is ambiguous, state which repository path was used.

## Example Invocation

```text
Use the bridge-builder-delegate skill to:
Add a CLI flag to export results as JSON.
```
