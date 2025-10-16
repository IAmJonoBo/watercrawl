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

### `enrich`

```bash
poetry run python -m firecrawl_demo.cli enrich data/input.csv --output data/output.csv --format text
```

- Validates, enriches, and writes the dataset.
- Automatically appends evidence rows to `data/interim/evidence_log.csv`.
- Supports JSON output for pipelines.

### `mcp-server`

```bash
poetry run python -m firecrawl_demo.cli mcp-server
```

- Runs the MCP JSON-RPC bridge over stdio.
- Designed for GitHub Copilot or other MCP-compliant clients.
- Accepts `initialize`, `list_tasks`, `run_task`, and `shutdown` methods.

## Exit Codes

- `0`: Success.
- `1`: Validation/enrichment failure (unhandled exception).

## Environment Variables

- `FIRECRAWL_API_KEY`: Loaded via `config.Settings` for future Firecrawl integrations.
- `FIRECRAWL_API_URL`: Override default API endpoint.
