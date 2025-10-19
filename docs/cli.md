# CLI Guide

Two complementary CLIs ship with the repository:

- `apps.analyst.cli` — the analyst- and end-user-focused surface that wraps the enrichment tooling.
- `apps.automation.cli` — a developer experience helper that mirrors the CI quality gates.

Both entry points run through Poetry: `poetry run python -m apps.analyst.cli ...` and `poetry run python -m apps.automation.cli ...`.
The repository ships a ready-to-run dataset at `data/sample.csv` so you can validate and
enrich immediately after installing dependencies.

> **Compatibility note:** `firecrawl_demo.interfaces.cli` remains available for backwards compatibility and simply re-exports the analyst CLI.

## Analyst commands (`apps.analyst.cli`)

### `validate`

```bash
poetry run python -m apps.analyst.cli validate data/input.csv --format json
```

- Loads CSV/XLSX data.
- Runs dataset validation and prints issues.
- Returns JSON (for automation) or text summaries.
- Exit status is `1` when validation fails so automations can gate on QA.
- Pass `--progress` to render a progress bar while validating large files.

### `enrich`

```bash
poetry run python -m apps.analyst.cli enrich data/input.csv --output data/output.csv --format text
```

- Validates, enriches, and writes the dataset.
- Automatically appends evidence rows to `data/interim/evidence_log.csv`.
- Supports JSON output for pipelines.
- Displays a Rich-powered progress bar for text output by default (`--no-progress` to disable).
- JSON responses now include an `adapter_failures` field so pipelines can alert on degraded runs.

### `contracts`

```bash
poetry run python -m apps.analyst.cli contracts data/output.csv --format json
```

- Executes the curated Great Expectations suite stored under `data_contracts/great_expectations/`.
- Reports failing expectations and their affected columns for triage.
- Exits non-zero when any contract fails so CI and analysts can gate publishes.

### `mcp-server`

```bash
poetry run python -m apps.analyst.cli mcp-server
```

- Runs the MCP JSON-RPC bridge over stdio.
- Designed for GitHub Copilot or other MCP-compliant clients.
- Accepts `initialize`, `list_tasks`, `run_task`, and `shutdown` methods.
- Exposes new orchestration tasks — `summarize_last_run` for metrics snapshots and
  `list_sanity_issues` for remediation queues — so Copilot can reason about pipeline
  health without parsing CSVs.

## Exit Codes

- `0`: Success.
- `1`: Dataset failed validation or an unhandled error occurred.

## Environment Variables

- `FIRECRAWL_API_KEY`: Loaded via `config.Settings` for future Firecrawl integrations.
- `FIRECRAWL_API_URL`: Override default API endpoint.

## Developer QA helpers (`apps.automation.cli`)

The developer CLI mirrors the GitHub Actions workflow locally and adds DX-focused conveniences.

### `qa plan`

```bash
poetry run python -m apps.automation.cli qa plan
```

- Prints the full QA execution plan as a Rich table.
- Accepts `--skip-dbt` to omit long-running contract steps when iterating quickly.

### `qa all`

```bash
poetry run python -m apps.automation.cli qa all --dry-run
```

- Executes (or previews with `--dry-run`) the cleanup, test, lint, type-check, security, pre-commit, build, and dbt stages.
- Supports `--fail-fast` and `--skip-dbt` toggles to match local needs.

### Targeted QA commands

Each QA stage is also exposed individually:

- `poetry run python -m apps.automation.cli qa tests`
- `poetry run python -m apps.automation.cli qa lint`
- `poetry run python -m apps.automation.cli qa typecheck`
- `poetry run python -m apps.automation.cli qa security --skip-secrets`
- `poetry run python -m apps.automation.cli qa build`
- `poetry run python -m apps.automation.cli qa contracts --dry-run`

## Analyst UI

The repository includes a Streamlit-based analyst UI for interactive review and feedback on enriched datasets.

```bash
poetry run streamlit run firecrawl_demo/interfaces/analyst_ui.py
```

Features:

- View enriched records and relationship graphs
- Annotate/flag specific records with feedback
- Audit trail for all feedback submissions

> **Note:** The UI is currently a basic prototype for analyst workflows.
