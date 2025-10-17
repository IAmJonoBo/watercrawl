# Operations & Quality Gates

## Baseline Checks

Run these before changes (already automated in CI):

```bash
poetry run pytest --maxfail=1 --disable-warnings --cov=firecrawl_demo --cov-report=term-missing
poetry run ruff check .
poetry run mypy .
poetry run bandit -r firecrawl_demo
poetry run pre-commit run --all-files
poetry run dotenv-linter lint .env.example
poetry run poetry build
poetry run python -m firecrawl_demo.cli contracts data/sample.csv --format json
poetry run dbt build --project-dir analytics --profiles-dir analytics --target ci --select tag:contracts --vars '{"curated_source_path": "data/sample.csv"}'
```

- Generate local CI dashboards with `poetry run python -m scripts.ci_summary --coverage coverage.xml --junit pytest-results.xml --output ci-summary.md --json ci-dashboard.json` when validating reports outside GitHub Actions.

Run the `contracts` command against the latest curated export (swap in the
appropriate path if you are validating a non-sample dataset). The command exits
non-zero on any expectation or dbt test failure, mirroring CI contract
enforcement. `dbt build --select tag:contracts` is invoked under the hood and
archives run artefacts to `data/contracts/<timestamp>/` for provenance.

Every enrichment run now emits a lineage bundle under `artifacts/lineage/<run_id>/` containing OpenLineage, PROV-O, and DCAT documents together with optional lakehouse manifests. Surface these artefacts in runbooks and attach them to incident reports so provenance checks stay reproducible.

> Update the path passed to `dotenv-linter` to match the environment file under
> review (for example `.env`, `.env.production`, or `.env.sample`). The command
> exits non-zero when variables are duplicated, unexported, or malformed, so run
> it before committing any secrets configuration changes.

## Secrets Provisioning

The stack now resolves credentials and feature flags through `firecrawl_demo.secrets`.

1. Choose a backend by setting `SECRETS_BACKEND` to `env`, `aws`, or `azure`.
2. For local development (`env`), populate `.env` or OS environment variables as before.
3. For AWS Secrets Manager, provide `AWS_REGION`/`AWS_DEFAULT_REGION` and an optional `AWS_SECRETS_PREFIX` (for example `prod/firecrawl/`). Credentials follow the active AWS profile or IAM role.
4. For Azure Key Vault, set `AZURE_KEY_VAULT_URL` and optionally `AZURE_SECRETS_PREFIX`; authentication flows through `DefaultAzureCredential`, so ensure managed identity or service principal access.
5. Rotation is handled centrally; override any individual secret locally by exporting the variable in your shell or `.env`.

The toolchain includes first-party type stubs for `pandas` and `requests`, so remove per-file `type: ignore` directives instead
of silencing mypy regressions.

## Acceptance Criteria

| Gate            | Threshold/Expectation                                   |
|-----------------|----------------------------------------------------------|
| Tests           | 100% pass, coverage tracked via `pytest --cov`.          |
| Lint            | No Ruff violations; Black/Isort formatting clean.        |
| Types           | `mypy` success, including third-party stubs.             |
| Security        | No `bandit` High/Medium findings without mitigation.     |
| Evidence        | Every enriched row logged with ≥2 sources.               |
| Sanity Checks   | `sanity_issues` metric is zero or tracked with remediation owners. |
| Documentation   | MkDocs updated for any behavioural change.               |

Monitor `adapter_failures` and `sanity_issues` in pipeline metrics/CLI output;
any non-zero count should trigger investigation into upstream research adapters
or missing evidence before publishing results.

## Evidence Sink Configuration

- `EVIDENCE_SINK_BACKEND`: choose `csv`, `stream`, or `csv+stream` to fan out.
- `EVIDENCE_STREAM_ENABLED`: toggle Kafka/REST emission when using the streaming stub.
- `EVIDENCE_STREAM_TRANSPORT`: `rest` (default) or `kafka` to switch log context.
- `EVIDENCE_STREAM_REST_ENDPOINT` / `EVIDENCE_STREAM_KAFKA_TOPIC`: document targets for future graph ingestion pipelines.

During enrichment the pipeline calls the configured `EvidenceSink`, so MCP tasks and CLI runs share the same audit trail plumbing. Use a mock sink in tests or dry runs to prevent filesystem writes.

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
