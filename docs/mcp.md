---
title: MCP Integration
description: Model Context Protocol bridge for GitHub Copilot and automation agents
---

# MCP Integration

The Model Context Protocol (MCP) bridge enables GitHub Copilot or other automation agents to drive the enrichment pipeline.

## Transport

- **Mode**: JSON-RPC 2.0 over stdio.
- **Server**: `watercrawl.interfaces.mcp.server.CopilotMCPServer`.
- **CLI Entry**: `poetry run python -m watercrawl.interfaces.cli mcp-server`.

## Methods

| Method     | Description                       | Params                             |
| ---------- | --------------------------------- | ---------------------------------- |
| initialize | Negotiates capabilities.          | None                               |
| list_tasks | Returns available pipeline tasks. | None                               |
| run_task   | Runs a task with a payload.       | `{ "task": str, "payload": dict }` |
| shutdown   | Gracefully stops the server.      | None                               |

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
      "rows": [...],
      "plan_artifacts": ["plans/run.plan"],
      "commit_artifacts": ["commits/run.commit"],
      "if_match": "\"dataset-etag\""
    }
  }
  ```

  or `{ "path": "data/input.xlsx" }`.

  Commit artefacts are JSON documents that capture the reviewed diff (`diff_summary`), approved diff format (`diff_format`), the `if_match` ETag, and RAG metrics (faithfulness, context precision, answer relevancy). Requests missing these artefacts are rejected with a `-32001` error and the plan→commit policy message.

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
- Error (plan→commit violation): `{ "error": { "code": -32001, "message": "Command 'mcp.enrich_dataset' requires at least one *.commit artefact." } }`

## Copilot Workflow

1. `initialize`
2. `list_tasks`
3. `run_task` for `validate_dataset`
4. Inspect issues, remediate locally.
5. `run_task` for `enrich_dataset` (include `plan_artifacts`, `commit_artifacts`, and `if_match` to satisfy the plan→commit guard)
6. `run_task` for `summarize_last_run` (optional) to capture metrics/sanity counts.
7. `run_task` for `list_sanity_issues` to queue remediation work.
8. `shutdown`

Include the CLI `--format json` outputs in your automation logs to maintain an audit trail.
