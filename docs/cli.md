---
title: CLI Guide
description: Command-line interface for analysts and automation workflows
---

# CLI Guide

Two complementary CLIs ship with the repository:

- `apps.analyst.cli` — the analyst- and end-user-focused surface that wraps the enrichment tooling.
- `apps.automation.cli` — a developer experience helper that mirrors the CI quality gates.

Both entry points run through Poetry: `poetry run python -m apps.analyst.cli ...` and `poetry run python -m apps.automation.cli ...`.
The repository ships a ready-to-run dataset at `data/sample.csv` so you can validate and
enrich immediately after installing dependencies.

> **Compatibility note:** `firecrawl_demo.interfaces.cli` remains available for backwards compatibility and simply re-exports the analyst CLI. Legacy automation that shells out to `python -m app.cli` continues to work via a compatibility shim that forwards to `apps.analyst.cli`.

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
poetry run python -m apps.analyst.cli enrich data/input.csv --output data/output.csv --plan plans/run.plan --commit commits/run.commit --format text
```

- Validates, enriches, and writes the dataset.
- Automatically appends evidence rows to `data/interim/evidence_log.csv`.
- Supports JSON output for pipelines.
- Displays a Rich-powered progress bar for text output by default (`--no-progress` to disable).
- JSON responses now include an `adapter_failures` field so pipelines can alert on degraded runs.
- Requires at least one recorded `*.plan` artefact when policy mandates plan→commit guardrails (`--plan` accepts multiple paths; `--force` is available only when `PLAN_COMMIT_ALLOW_FORCE=1`).
- Requires at least one `*.commit` artefact summarising the approved diff, `If-Match` value, and RAG/RAGAS metrics that met policy thresholds (`--commit` accepts multiple paths).
- Successful runs append JSON audit entries to `data/logs/plan_commit_audit.jsonl`, capturing plan paths, commit metadata, and policy decisions for traceability.

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

The developer CLI mirrors the GitHub Actions workflow locally and adds DX-focused conveniences. It is exposed as both `apps.automation.cli` and the compatibility shim `python -m dev.cli` for tooling that expects the legacy module path.

### `qa plan`

```bash
poetry run python -m apps.automation.cli qa plan
```

- Prints the full QA execution plan as a Rich table.
- Accepts `--skip-dbt` to omit long-running contract steps when iterating quickly.
- Pass `--write-plan path/to/change.plan` (and optionally `--write-commit path/to/change.commit`) to generate artefacts that satisfy the plan→commit policy. Use `--if-match-token` to customise the commit header and `--overwrite` when regenerating existing files.
- Provide `--instructions "text"` to add contextual notes recorded in the generated plan/commit artefacts.

### `qa all`

```bash
poetry run python -m apps.automation.cli qa all --dry-run
```

- Executes (or previews with `--dry-run`) the cleanup, dependency sync, test, lint, type-check, security, pre-commit, build, and dbt stages.
- Supports `--fail-fast` and `--skip-dbt` toggles to match local needs.
- Automatically provisions Python 3.13 with uv when the active interpreter is older than 3.13 (disable with `--no-auto-bootstrap`).
- Enforces plan artefacts before running destructive steps such as `scripts.cleanup`; supply `--plan path/to/change.plan` and matching `--commit path/to/change.commit` acknowledgements when the policy contract requires them, or pass `--generate-plan` to materialise fresh artefacts automatically (use `--plan-dir` to control the output directory).

### `qa fmt`

```bash
poetry run python -m apps.automation.cli qa fmt --generate-plan --plan-dir tmp/plans
```

- Applies Ruff auto-fixes, isort, and Black in sequence to normalise imports and formatting.
- Requires plan artefacts by default; use `--plan/--commit` to provide them or `--generate-plan` (with optional `--plan-note` / `--if-match-token`) to materialise compliant artefacts automatically.
- Honours `--dry-run` and `--no-auto-bootstrap` toggles when previewing or skipping uv provisioning.

### Targeted QA commands

Each QA stage is also exposed individually:

- `poetry run python -m apps.automation.cli qa tests`
- `poetry run python -m apps.automation.cli qa lint`
- `poetry run python -m apps.automation.cli qa fmt --generate-plan`
- `poetry run python -m apps.automation.cli qa typecheck`
- `poetry run python -m apps.automation.cli qa security --skip-secrets`
- `poetry run python -m apps.automation.cli qa build`
- `poetry run python -m apps.automation.cli qa contracts --dry-run`
Additional output from these commands is summarised in the automation CLI console tables and plan artefacts, eliminating the need for the legacy problems report workflow.

Pass `--auto-bootstrap/--no-auto-bootstrap` to any targeted command to control whether uv is invoked automatically. The `qa dependencies` command now installs the Poetry environment before running the compatibility survey and guard checks, ensuring ephemeral runners start from a consistent toolchain.

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
