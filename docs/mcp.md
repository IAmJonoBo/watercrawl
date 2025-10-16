# MCP Integration

The Model Context Protocol (MCP) bridge enables GitHub Copilot or other automation agents to drive the enrichment pipeline.

## Transport

- **Mode**: JSON-RPC 2.0 over stdio.
- **Server**: `firecrawl_demo.mcp.server.CopilotMCPServer`.
- **CLI Entry**: `poetry run python -m firecrawl_demo.cli mcp-server`.

## Methods

| Method      | Description                                      | Params                                  |
|-------------|--------------------------------------------------|------------------------------------------|
| initialize  | Negotiates capabilities.                         | None                                     |
| list_tasks  | Returns `validate_dataset` and `enrich_dataset`.  | None                                     |
| run_task    | Runs a task with a payload.                      | `{ "task": str, "payload": dict }`     |
| shutdown    | Gracefully stops the server.                     | None                                     |

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

## Responses

- Success: `{ "jsonrpc": "2.0", "id": 1, "result": { ... } }`
- Error (unknown task): `{ "error": { "code": -32601, "message": "Unknown task 'foo'" } }`

## Copilot Workflow

1. `initialize`
2. `list_tasks`
3. `run_task` for `validate_dataset`
4. Inspect issues, remediate locally.
5. `run_task` for `enrich_dataset`
6. `shutdown`

Include the CLI `--format json` outputs in your automation logs to maintain an audit trail.
