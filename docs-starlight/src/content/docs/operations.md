---
title: Operations & Quality Gates
---

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
| Lint          | Ruff, Black/Isort, Yamllint, Markdownlint, Hadolint, Actionlint all green; run SQLFluff on Python 3.13 until dbt restores Python 3.14 support. |
| Types         | `mypy` success, including third-party stubs.                                         |
| Security      | No `bandit`/`safety` High/Medium findings without mitigation.                        |
| Evidence      | Every enriched row logged with ≥2 sources.                                           |
| Sanity Checks | `sanity_issues` metric is zero or tracked with remediation owners.                   |
| Documentation | MkDocs updated for any behavioural change.                                           |

Monitor `adapter_failures` and `sanity_issues` in pipeline metrics/CLI output;
any non-zero count should trigger investigation into upstream research adapters
or missing evidence before publishing results.

### Problems report automation

`scripts/collect_problems.py` aggregates the core QA tools (Ruff, mypy, Yamllint) into `problems_report.json`. Optional integrations stay opt-in:

- **Bandit** only runs on Python versions prior to 3.14 while the upstream project restores support.
- **SQLFluff** is skipped automatically on Python ≥ 3.14 because dbt’s templater stack currently fails under `mashumaro`. When SQL linting is required, install Python 3.13 (`uv python install 3.13.0`), switch Poetry to that interpreter, run `poetry run python -m tools.sql.sqlfluff_runner --project-dir data_contracts/analytics`, and then switch back to the default interpreter.
- **Pylint** can be re-enabled by exporting `ENABLE_PYLINT=1` before running the collector; it remains optional to keep the default workflow fast.
- The optional Poetry group `ui` bundles Streamlit and PyArrow (currently limited to Python `<3.14`). Default installs skip the group so baseline environments no longer fail on missing Arrow wheels; run `poetry install --with ui` from Python 3.12/3.13 whenever you need the analyst UI or first-class Parquet exports.
- The `lakehouse` dependency group adds native Delta Lake support. Use `poetry install --with ui --with lakehouse` on Python 3.12/3.13 to record real Delta commits; without the group the writer falls back to filesystem snapshots and marks the manifest as degraded.
- Restore snapshots programmatically (`poetry run python -m firecrawl_demo.infrastructure.lakehouse restore --version 3 --output tmp.csv`) to verify time-travel and roll back runs when required.
- Configure drift monitoring via `DRIFT_BASELINE_PATH`, `DRIFT_WHYLOGS_OUTPUT`, and `DRIFT_WHYLOGS_BASELINE`. Each pipeline run logs a whylogs-style profile (fallback JSON when the library is absent) and surfaces alerts whenever ratios deviate beyond `DRIFT_THRESHOLD`.

The `.sqlfluff` configuration is already scoped to `data_contracts/analytics`, so teams stay on the same dbt golden path regardless of where the lint is executed.

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
