# CLI Guide

The CLI lives in `firecrawl_demo.cli` and is available via `python -m firecrawl_demo.cli ...` when the Poetry environment is active.

## Commands

### `validate`

```bash
poetry run python -m firecrawl_demo.cli validate data/input.csv --format json
```

- Loads CSV/XLSX data.
- Runs dataset validation and prints issues.
- Returns JSON (for automation) or text summaries.
- Exit status is `1` when validation fails so automations can gate on QA.
- Pass `--progress` to render a progress bar while validating large files.

### `enrich`

```bash
poetry run python -m firecrawl_demo.cli enrich data/input.csv --output data/output.csv --format text
```

- Validates, enriches, and writes the dataset.
- Automatically appends evidence rows to `data/interim/evidence_log.csv`.
- Supports JSON output for pipelines.
- Displays a Rich-powered progress bar for text output by default (`--no-progress` to disable).
- JSON responses now include an `adapter_failures` field so pipelines can alert on degraded runs.

### `mcp-server`

```bash
poetry run python -m firecrawl_demo.cli mcp-server
```

- Runs the MCP JSON-RPC bridge over stdio.
- Designed for GitHub Copilot or other MCP-compliant clients.
- Accepts `initialize`, `list_tasks`, `run_task`, and `shutdown` methods.

## Exit Codes

- `0`: Success.
- `1`: Dataset failed validation or an unhandled error occurred.

## Environment Variables

- `FIRECRAWL_API_KEY`: Loaded via `config.Settings` for future Firecrawl integrations.
- `FIRECRAWL_API_URL`: Override default API endpoint.
