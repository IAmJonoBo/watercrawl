# Operations & Quality Gates

## Baseline Checks

Run these before changes (already automated in CI). Start by clearing local
artefacts so the suite mirrors CI output:

```bash
poetry run python -m scripts.cleanup --dry-run
poetry run python -m scripts.cleanup
```

> The offline Safety audit consumes the vendored `safety-db` snapshot; plan quarterly updates so advisories stay current.

Then execute the quality gates:

```bash
poetry run pytest --maxfail=1 --disable-warnings --cov=firecrawl_demo --cov-report=term-missing
poetry run ruff check .
poetry run python -m tools.sql.sqlfluff_runner
poetry run yamllint --strict -c .yamllint.yaml .
poetry run pre-commit run markdownlint-cli2 --all-files
poetry run pre-commit run hadolint --all-files
poetry run pre-commit run actionlint --all-files
poetry run mypy .
poetry run bandit -r firecrawl_demo
poetry run python -m tools.security.offline_safety --requirements requirements.txt --requirements requirements-dev.txt
poetry run pre-commit run --all-files
poetry run dotenv-linter lint .env.example
poetry run poetry build
poetry run python -m firecrawl_demo.interfaces.cli contracts data/sample.csv --format json
poetry run dbt build --project-dir data_contracts/analytics --profiles-dir data_contracts/analytics --target ci --select tag:contracts --vars '{"curated_source_path": "data/sample.csv"}'
```

- Generate local CI dashboards with `poetry run python -m scripts.ci_summary --coverage coverage.xml --junit pytest-results.xml --output ci-summary.md --json ci-dashboard.json` when validating reports outside GitHub Actions.

Run the `contracts` command against the latest curated export (swap in the
appropriate path if you are validating a non-sample dataset). The command exits
non-zero on any expectation or dbt test failure, mirroring CI contract
enforcement. `dbt build --select tag:contracts` is invoked under the hood and
archives run artefacts to `data/contracts/<timestamp>/` for provenance.

The CLI seeds `CONTRACTS_CANONICAL_JSON` so dbt macros and Great Expectations
share canonical province/status taxonomies and the 70-point evidence confidence
threshold. When invoking dbt directly, export this environment variable with the
JSON payload from `firecrawl_demo.integrations.contracts.shared_config` to avoid
drift between toolchains.

Every enrichment run now emits a lineage bundle under `artifacts/lineage/<run_id>/` containing OpenLineage, PROV-O, and DCAT documents together with optional lakehouse manifests. The PROV graphs call out the enrichment software agent, evidence counts, and quality metrics while DCAT entries surface reproducibility commands, contact metadata, and distribution records for the evidence log, manifests, and lineage bundle. Surface these artefacts in runbooks and attach them to incident reports so provenance checks stay reproducible.

Each run also captures a `version.json` manifest within the versioning metadata root (default `data/versioning/`). The manifest
records the input fingerprint, output fingerprint, row count, and the command required to reproduce the run. Attach this file to
release reviews so operators can replay or roll back snapshots deterministically.

> **Codex guardrail:** run `promptfoo eval codex/evals/promptfooconfig.yaml` before enabling any Codex or MCP-assisted sessions.
> Production platform deployments must leave Codex disabled; only the `apps/automation/` workspace may opt in after the smoke tests pass.

## Problems Report Aggregation

The `problems_report.json` artefact aggregates findings from multiple QA tools into a unified, machine-readable format for automated triage and human review. This pipeline ensures that linter errors, type issues, security vulnerabilities, and other code quality problems are surfaced consistently across CI, ephemeral runners, and local development environments.

### Pipeline Overview

The aggregation is performed by `scripts/collect_problems.py`, which executes a suite of QA tools in parallel and parses their outputs into a standardized JSON structure. The script is designed to be fast, with output truncation for large reports (max 2000 characters per message, 100 issues per tool) to prevent context overflow.

Supported QA tools include:

- **Ruff**: Python linter and formatter.
- **Mypy**: Static type checker.
- **Pylint**: Advanced Python linter (optional, may not be installed).
- **Bandit**: Security linter for Python code.
- **Yamllint**: YAML file linter.
- **SQLFluff**: SQL linter for dbt models (using DuckDB dialect).

Each tool's results are captured with status, return code, parsed issues, and summary metrics. The report includes a generation timestamp for freshness tracking.

### JSON Structure

The `problems_report.json` file follows this schema:

```json
{
  "generated_at": "2025-10-18T12:37:05.925602+00:00",
  "tools": [
    {
      "tool": "ruff",
      "status": "completed",
      "returncode": 0,
      "issues": [
        {
          "path": "file.py",
          "line": 10,
          "column": 5,
          "code": "E501",
          "message": "Line too long"
        }
      ],
      "summary": {
        "issue_count": 1,
        "fixable": 1
      }
    }
  ]
}
```

- `generated_at`: ISO 8601 timestamp of report generation.
- `tools`: Array of tool results, each with:
  - `tool`: Tool name.
  - `status`: Execution status (e.g., "completed", "failed").
  - `returncode`: Exit code from the tool.
  - `issues`: Array of parsed issues (truncated if excessive).
  - `summary`: Tool-specific metrics (e.g., issue counts, severity breakdowns).
    - Optional fields: `stderr_preview`, `notes`, `raw_preview` (for parsing failures).
      Each preview stores chunked text to keep lines below shell output limits and includes truncation metadata when applicable.

### Wiring and Integration

- **CI Pipeline**: In `.github/workflows/ci.yml`, the report is generated after tests via `poetry run python scripts/collect_problems.py` and uploaded as a CI artifact named `ci-dashboards`. This ensures problems are visible in GitHub Actions runs.
- **Ephemeral Runners**: Automatically generated during containerized or serverless executions to surface issues without full IDE access.
- **Local Development**: Run manually or via the shell wrapper `scripts/collect_problems.sh` to check code quality before commits.
- **Automation CLI**: While `poetry run python -m apps.automation.cli qa all` mirrors most CI checks, the problems report is generated separately to aggregate findings post-QA.

Analysts and Copilot agents must check `problems_report.json` for outstanding issues before remediation or enrichment tasks. This workflow blocks clean evidence logging and enrichment until problems are resolved.

### Usage

To generate the problems report locally:

```bash
# Via Python script
poetry run python scripts/collect_problems.py

# Via shell wrapper
bash scripts/collect_problems.sh
```

The script outputs the path to the generated `problems_report.json`. Review the file to identify issues by tool, and address them using the standard QA commands (e.g., `poetry run ruff check . --fix` for auto-fixable Ruff issues).

For CI-like execution, run the full QA suite first:

```bash
poetry run python -m apps.automation.cli qa all
poetry run python scripts/collect_problems.py
```

This mirrors the CI sequence and ensures the report reflects the latest code state.

> Update the path passed to `dotenv-linter` to match the environment file under
> review (for example `.env`, `.env.production`, or `.env.sample`). The command
> exits non-zero when variables are duplicated, unexported, or malformed, so run
> it before committing any secrets configuration changes.

## Secrets Provisioning

The stack now resolves credentials and feature flags through `firecrawl_demo.governance.secrets`.

1. Choose a backend by setting `SECRETS_BACKEND` to `env`, `aws`, or `azure`.
2. For local development (`env`), populate `.env` or OS environment variables as before.
3. For AWS Secrets Manager, provide `AWS_REGION`/`AWS_DEFAULT_REGION` and an optional `AWS_SECRETS_PREFIX` (for example `prod/firecrawl/`). Credentials follow the active AWS profile or IAM role.
4. For Azure Key Vault, set `AZURE_KEY_VAULT_URL` and optionally `AZURE_SECRETS_PREFIX`; authentication flows through `DefaultAzureCredential`, so ensure managed identity or service principal access.
5. Rotation is handled centrally; override any individual secret locally by exporting the variable in your shell or `.env`.

The toolchain includes first-party type stubs for `pandas` and `requests`, so remove per-file `type: ignore` directives instead
of silencing mypy regressions.

## Acceptance Criteria

| Gate          | Threshold/Expectation                                                                |
| ------------- | ------------------------------------------------------------------------------------ |
| Tests         | 100% pass, coverage tracked via `pytest --cov`.                                      |
| Lint          | Ruff, Black/Isort, Yamllint, SQLFluff, Markdownlint, Hadolint, Actionlint all green. |
| Types         | `mypy` success, including third-party stubs.                                         |
| Security      | No `bandit`/`safety` High/Medium findings without mitigation.                        |
| Evidence      | Every enriched row logged with ≥2 sources.                                           |
| Sanity Checks | `sanity_issues` metric is zero or tracked with remediation owners.                   |
| Documentation | MkDocs updated for any behavioural change.                                           |

Monitor `adapter_failures` and `sanity_issues` in pipeline metrics/CLI output;
any non-zero count should trigger investigation into upstream research adapters
or missing evidence before publishing results.

## Evidence Sink Configuration

- `EVIDENCE_SINK_BACKEND`: choose `csv`, `stream`, or `csv+stream` to fan out. Invalid
  backends now raise a configuration error so mis-typed values are caught early.
- `EVIDENCE_STREAM_ENABLED`: toggle Kafka/REST emission when using the streaming stub.
- `EVIDENCE_STREAM_TRANSPORT`: `rest` (default) or `kafka` to switch log context.
- `EVIDENCE_STREAM_REST_ENDPOINT` / `EVIDENCE_STREAM_KAFKA_TOPIC`: document targets for future graph ingestion pipelines.

During enrichment the pipeline calls the configured `EvidenceSink`, so MCP tasks and CLI runs share the same audit trail plumbing. Use a mock sink in tests or dry runs to prevent filesystem writes.

## Lineage emission controls

- `OPENLINEAGE_TRANSPORT`: `file` (default), `http`, `kafka`, or `logging` to choose how events are
  emitted after enrichment runs.
- `OPENLINEAGE_URL`: required when using the HTTP transport; events are POSTed with a JSON body per
  OpenLineage run event.
- `OPENLINEAGE_API_KEY`: optional bearer token injected as `Authorization: Bearer <token>` for HTTP emission.
- `OPENLINEAGE_KAFKA_TOPIC` / `OPENLINEAGE_KAFKA_BOOTSTRAP`: required when emitting directly to Kafka.
- `OPENLINEAGE_NAMESPACE`: overrides the namespace baked into lineage events without touching code.

CLI output surfaces the lineage artefact directory together with the lakehouse manifest and version
manifest paths so runbooks can link provenance bundles without digging through the filesystem.

## Infrastructure Configuration

- **Crawler** — tune via `CRAWLER_FRONTIER_BACKEND`, `CRAWLER_SCHEDULER_MODE`, `CRAWLER_POLITENESS_DELAY_SECONDS`, `CRAWLER_MAX_DEPTH`, `CRAWLER_MAX_PAGES`, and `CRAWLER_USER_AGENT`. Optional trap rules can be mounted with `CRAWLER_TRAP_RULES_PATH`.
- **Observability** — health probes default to port `8080` (`OBSERVABILITY_PORT`) with `/healthz`, `/readyz`, `/startupz` endpoints. Adjust SLOs using `SLO_AVAILABILITY_TARGET`, `SLO_LATENCY_P95_MS`, and `SLO_ERROR_BUDGET_PERCENT`. Alert channels derive from `OBSERVABILITY_ALERT_ROUTES` (comma-separated or JSON array).
- **Policy Gate** — set `OPA_BUNDLE_PATH` for the compiled policy bundle, override decision namespace via `OPA_DECISION_PATH`, and flip enforcement with `OPA_ENFORCEMENT_MODE` (`enforce` or `dry-run`). Cache TTL is controlled by `OPA_CACHE_SECONDS`.
- **Plan→Commit Workflow** — require planning in automation by keeping `PLAN_COMMIT_REQUIRED=1`. Change diff presentation with `PLAN_COMMIT_DIFF_FORMAT` (`markdown` or `json`) and publish audit events to the topic specified in `PLAN_COMMIT_AUDIT_TOPIC`. Emergency overrides can be toggled with `PLAN_COMMIT_ALLOW_FORCE`.

## Incident Response

1. Re-run CLI `validate` to reproduce issue locally.
2. Capture context (input rows, evidence log snippets).
3. File `Risks/Notes` entry in `Next_Steps.md` and update MkDocs if the workflow changes.
4. Implement fix with tests-first discipline.

## Release Playbook

1. Run full QA suite.
2. Update `CHANGELOG.md` (to be introduced) with highlights.
3. Regenerate MkDocs (`mkdocs build`) and publish artefacts.
4. Tag release following SemVer once automation surfaces confirm green status.

## Infrastructure Plan Drift

- `firecrawl_demo.infrastructure.planning.detect_plan_drift()` compares the active plan against the checked-in baseline snapshot.
- `tests/test_infrastructure_planning.py::test_infrastructure_plan_matches_baseline_snapshot` guards probe endpoints, the active OPA bundle path, and plan→commit automation topics from unexpected drift.
- Update the baseline snapshot intentionally whenever probes move or policy bundles change, and note the reason in `Next_Steps.md`.
