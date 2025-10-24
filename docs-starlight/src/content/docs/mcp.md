---
title: MCP Integration
---

The Model Context Protocol (MCP) bridge enables GitHub Copilot or other automation agents to drive the enrichment pipeline.

## Transport

- **Mode**: JSON-RPC 2.0 over stdio.
- **Server**: `watercrawl.interfaces.mcp.server.CopilotMCPServer`.
- **CLI Entry**: `poetry run python -m watercrawl.interfaces.cli mcp-server`.

## Methods

| Method         | Description                                            | Params                                     |
| -------------- | ------------------------------------------------------ | ------------------------------------------ |
| initialize     | Negotiates capabilities and returns the active profile | None                                       |
| list_tasks     | Returns available pipeline tasks                       | None                                       |
| list_profiles  | Lists refinement profiles discovered in `profiles/`    | None                                       |
| select_profile | Switches to a specific profile (id or path)            | `{ "profile_id": str?, "profile_path": str? }` |
| run_task       | Runs a task with a payload                             | `{ "task": str, "payload": dict }`            |
| shutdown       | Gracefully stops the server                            | None                                       |

### Payload Shapes

- `validate_dataset`

  ```json
  {
    "task": "validate_dataset",
    "payload": {
      "rows": [ {"Name of Organisation": "...", ... } ]
    }
  }
  ```

- `enrich_dataset`

  ```json
  {
    "task": "enrich_dataset",
    "payload": {
      "rows": [...]
    }
  }
  ```

  or `{ "path": "data/input.xlsx" }`.

- `summarize_last_run`

  ```json
  { "task": "summarize_last_run", "payload": {} }
  ```

- `list_sanity_issues`

  ```json
  { "task": "list_sanity_issues", "payload": {} }
  ```

## Responses

- Success: `{ "jsonrpc": "2.0", "id": 1, "result": { ... } }`
- Error (unknown task): `{ "error": { "code": -32601, "message": "Unknown task 'foo'" } }`

## Copilot Workflow

1. `initialize`
2. `list_tasks`
3. `run_task` for `validate_dataset`
4. Inspect issues, remediate locally.
5. `run_task` for `enrich_dataset`
6. `run_task` for `summarize_last_run` (optional) to capture metrics/sanity counts.
7. `run_task` for `list_sanity_issues` to queue remediation work.
8. `shutdown`

Include the CLI `--format json` outputs in your automation logs to maintain an audit trail.

## Profile Management

- `list_profiles` returns `{ "profiles": [ { "id", "name", "description", "path", "active" } ] }` so copilots can present valid options.
- `select_profile` accepts either a profile identifier or full filesystem path. On success it returns the selected profile metadata and reinitialises the pipeline with the new configuration. Plan→commit guardrails remain enforced for `enrich_dataset` after switching.
