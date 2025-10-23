---
title: Operations & Quality Gates
description: Baseline checks, testing procedures, and operational workflows
---

# Operations & Quality Gates

## Baseline Checks

Run these before changes (already automated in CI). Start by clearing local
artefacts so the suite mirrors CI output and ensure the minimum interpreter is
available:

```bash
python -m scripts.bootstrap_env --dry-run
python -m scripts.bootstrap_env

python -m scripts.bootstrap_python --install-uv --poetry
poetry run python -m scripts.cleanup --dry-run
poetry run python -m scripts.cleanup
```

> The offline Safety audit consumes the vendored `safety-db` snapshot; plan quarterly updates so advisories stay current.
> The bootstrap flow provisions the uv-managed Python 3.13 interpreter, syncs the Poetry environment (`poetry install --sync --no-root`), and creates an in-project `.venv/` via `poetry.toml` so shells, CI, and offline runners use the same toolchain without additional configuration.

> Python 3.13 is the project baseline. `scripts/bootstrap_env` provisions the correct interpreter automatically, and helper wrappers like `scripts/run_pytest.sh` guard against accidental use of stale global Pythons.

Before executing the rest of the suite, confirm the pinned dependencies ship
compatible wheels for every Python target tracked in `presets/dependency_targets.toml`
(Python 3.13 as the stable baseline, Python 3.14 and 3.15 tracked for upcoming upgrades).
The guard command enforces that only the curated allow-list of wheel gaps remains
and fails fast if new blockers appear or previously known issues clear without
updating the configuration:

```bash
python -m scripts.dependency_matrix survey --config presets/dependency_targets.toml --output tools/dependency_matrix/report.json
python -m scripts.dependency_matrix guard --config presets/dependency_targets.toml --blockers presets/dependency_blockers.toml --status-output tools/dependency_matrix/status.json --strict
```

The survey parses `poetry.lock`, checks each wheel artefact, and captures
issues in `tools/dependency_matrix/report.json` so platform engineers can
triage Python upgrade blockers before QA time is spent. The guard emits
`tools/dependency_matrix/status.json` with machine-readable metadata for
Renovate, CI summaries, and release checklists.

> Tip: `poetry run python -m apps.automation.cli qa dependencies --dry-run`
> invokes the same survey/guard pipeline but automatically installs the Poetry
> environment and provisions Python 3.13 via uv when the active interpreter is older than 3.13.

The mirrored wheel cache backing offline installs is automated via
`scripts/mirror_wheels.py`. Run `python scripts/mirror_wheels.py --dry-run`
after the dependency guard to ensure `artifacts/cache/pip/mirror_state.json`
matches the current `poetry.lock`. CI executes the full mirror refresh in
`.github/workflows/wheel-mirror.yml` (nightly and on lockfile changes), uploads
the cache artifact, and fails fast when `python -m scripts.wheel_status --fail-on-missing`
detects unresolved blockers. Escalate dry-run or workflow failures to the
Platform supply-chain rotation (Slack `#platform-supply-chain`, pager `platform-deps@aces.example.com`) so upstream wheel
owners receive the F-011 alert within the same business day.

Then execute the quality gates:

```bash
poetry run ruff check .
poetry run black --check .
poetry run isort --check-only .
poetry run mypy .
```

### Security & Dependencies

```bash
poetry run bandit -r firecrawl_demo
poetry run python -m tools.security.offline_safety --requirements requirements.txt --requirements requirements-dev.txt
poetry run pre-commit run --all-files
```

### Testing

```bash
./scripts/run_pytest.sh --maxfail=1 --disable-warnings --cov=firecrawl_demo --cov-report=term-missing
```

`scripts/run_pytest.sh` discovers the Poetry-managed Python 3.13 interpreter (or provisions one via `uv`) so local shells never fall back to an outdated `pytest` binary on the system PATH.

### Data Quality

```bash
poetry run python -m apps.analyst.cli contracts data/sample.csv --format json
poetry run python -m apps.analyst.cli coverage --format json
poetry run dbt build --project-dir data_contracts/analytics --profiles-dir data_contracts/analytics --target ci --select tag:contracts --vars '{"curated_source_path": "data/sample.csv"}'
```

The `coverage` command reports contract coverage across all curated tables and
exits with code 1 if coverage is below 95%. This ensures that all curated
datasets have quality checks defined before they are published.

### Data Contracts & Schema Validation

The project uses **Pydantic-based data contracts** (v1.0.0) for all domain models. To validate data against contracts:

```bash
# Run contract tests to verify schema compliance and snapshot stability
poetry run pytest tests/test_contract_schemas.py -v

# Export all contract schemas for documentation
poetry run python -c "from firecrawl_demo.domain.contracts import export_all_schemas; import json; print(json.dumps(export_all_schemas(), indent=2))"

# Export the matching Avro schema bundle when refreshing registry metadata
poetry run python -c "from firecrawl_demo.domain.contracts import export_all_avro_schemas; import json; print(json.dumps(export_all_avro_schemas(), indent=2))"
```

**Contract guarantees:**

- All domain models have versioned Pydantic equivalents in `firecrawl_demo/domain/contracts.py`
- JSON Schema **and Avro** export available for integration testing, registries, and API docs
- Backward compatibility adapters in `firecrawl_demo/domain/models.py`
- Schema stability enforced via regression tests (JSON + Avro snapshots stored under `tests/data/contracts/`)
- Evidence sinks normalise and validate entries via `EvidenceRecordContract`
- Plan→commit artefacts must satisfy `PlanArtifactContract`/`CommitArtifactContract` before execution

**When to update contract versions:**

- Increment **patch** (1.0.x) for documentation or non-breaking clarifications
- Increment **minor** (1.x.0) for backward-compatible additions (new optional fields)
- Increment **major** (x.0.0) for breaking changes (removing fields, changing validation rules)

After bumping the contract version, regenerate schema snapshots:

```bash
poetry run pytest tests/test_contract_schemas.py::TestSchemaExport::test_schema_stability_regression --snapshot-update
poetry run pytest tests/test_contract_schemas.py::TestSchemaExport::test_avro_schema_regression --snapshot-update
```

### Supply chain artifacts

- CI builds distribution artifacts via `poetry build`, produces a CycloneDX SBOM at `artifacts/sbom/cyclonedx.json`, and signs the wheel/sdist with Sigstore (bundles stored under `artifacts/signatures/`).
- Verify signatures locally:

  ```bash
  sigstore verify identity \
    --cert-identity "https://github.com/IAmJonoBo/watercrawl/.github/workflows/ci.yml@refs/heads/main" \
    --cert-oidc-issuer https://token.actions.githubusercontent.com \
    --bundle artifacts/signatures/bundles/dist/firecrawl_demo-*.whl.sigstore \
    dist/firecrawl_demo-*.whl
  ```

- Scorecard runs live in `.github/workflows/scorecard.yml`. Review the latest SARIF under the repository Security tab or download the `scorecard-results` artifact from workflow runs.

### Accessibility smoke test

- Run the Streamlit axe-core check locally with `poetry run python apps/analyst/accessibility/axe_smoke.py`. The script boots the analyst UI headlessly, runs axe against the rendered DOM, and fails on any violations outside the documented Streamlit chrome exclusions.

### Developer commit signing (gitsign)

All contributors should configure [gitsign](https://github.com/sigstore/gitsign) to ensure commits are OIDC-signed:

```bash
brew install sigstore/tap/gitsign  # or follow upstream installation guidance
gitsign init
git config --global commit.gpgsign true
git config --global gpg.x509.program gitsign
git config --global gpg.format x509
```

With these settings, `git commit` automatically obtains an OIDC token from GitHub and records the signature in the commit metadata.

### Infrastructure & Config

```bash
poetry run yamllint --strict -c .yamllint.yaml .
poetry run pre-commit run hadolint --all-files
poetry run pre-commit run actionlint --all-files
poetry run dotenv-linter lint .env.example
poetry run poetry build
```

## CI Mirroring

Mirror CI locally before pushing:

```bash
# Full QA suite (mirrors CI)
poetry run python -m dev.cli qa all --dry-run

# Check evidence logging
poetry run python -m firecrawl_demo.interfaces.cli validate data/sample.csv --evidence-log data/interim/evidence_log.csv
```

> **Plan requirement:** When running `poetry run python -m apps.automation.cli qa all` (non dry-run), include one or more `--plan` arguments pointing at recorded `*.plan` artefacts so the cleanup step passes plan→commit enforcement. Use `--dry-run` while drafting the plan or `--force` only when `PLAN_COMMIT_ALLOW_FORCE=1`.

## Development Workflows

### E2E Pipeline Testing

```bash
# Full pipeline with sample data
poetry run python -m app.cli validate data/sample.csv
poetry run python -m app.cli enrich data/sample.csv --output data/processed/enriched.csv --plan plans/run.plan
poetry run python -m app.cli contracts data/processed/enriched.csv

# With evidence logging
poetry run python -m app.cli enrich data/sample.csv --output data/processed/enriched.csv --evidence-log data/interim/evidence_log.csv --plan plans/run.plan
```

### MCP Server Testing

```bash
# Start MCP server
poetry run python -m app.cli mcp-server

# Test MCP commands
poetry run python -m dev.cli mcp summarize-last-run
poetry run python -m dev.cli mcp list-sanity-issues
```

> **Plan guard:** When invoking `enrich_dataset` via MCP, include both `plan_artifacts` **and** `commit_artifacts` plus an `if_match` header in the payload so the server can record plan→commit evidence before executing destructive work. Commit artefacts capture the reviewed diff, policy decision, and RAG metrics; missing artefacts are rejected unless `PLAN_COMMIT_ALLOW_FORCE=1`.

> - Tune thresholds via `PLAN_COMMIT_RAG_FAITHFULNESS`, `PLAN_COMMIT_RAG_CONTEXT_PRECISION`, and `PLAN_COMMIT_RAG_ANSWER_RELEVANCY`.
> - Audit events append to `PLAN_COMMIT_AUDIT_LOG_PATH` (defaults to `data/logs/plan_commit_audit.jsonl`).

### Data Lakehouse Operations

```bash
# Snapshot to lakehouse
poetry run python -m firecrawl_demo.infrastructure.lakehouse snapshot --source data/processed/enriched.csv --destination data/lakehouse/

# Lineage capture
poetry run python -m firecrawl_demo.infrastructure.lineage capture --run-id $(date +%s) --input data/sample.csv --output data/processed/enriched.csv
```

- The Streamlit analyst UI and the Parquet writer engine are packaged in the optional Poetry dependency group `ui`. On Python 3.14+ the PyArrow wheels are still pending, so default installs on those interpreters skip these packages; run `poetry install --with ui` from Python 3.12/3.13 when you need the UI or native Parquet snapshots. Without the group, lakehouse exports fall back to CSV with remediation guidance in the manifest.
- The Delta Lake writer is provided by the optional dependency group `lakehouse`. Enable it alongside the UI group (`poetry install --with ui --with lakehouse`) on Python 3.12/3.13 to produce native Delta commits with time-travel support. When the group is absent, the writer automatically records filesystem snapshots and marks the manifest as degraded.
- Restore any snapshot (or Delta version) with:

```bash
# Restore the latest snapshot to a CSV file
poetry run python -m firecrawl_demo.infrastructure.lakehouse restore --output tmp/restored.csv

# Restore a specific Delta commit (requires --with lakehouse)
poetry run python -m firecrawl_demo.infrastructure.lakehouse restore --version 3 --output tmp/restored.csv
```

### Drift observability

- Configure drift baselines via `DRIFT_BASELINE_PATH` (JSON with `status_counts`, `province_counts`, and `total_rows`). Use `python -m firecrawl_demo.integrations.telemetry.drift` helpers or the provided notebook to generate the initial baseline from a trusted dataset.
- Whylogs profiles are emitted to `DRIFT_WHYLOGS_OUTPUT` (default `data/observability/whylogs/`). Set `DRIFT_WHYLOGS_BASELINE` to a stored profile metadata JSON to enable automatic alerting.
- Each pipeline run logs a whylogs-compatible profile (fallback JSON when the `whylogs` package is unavailable) and raises alerts when category ratios drift beyond `DRIFT_THRESHOLD` (default `0.15`). Alerts surface in `PipelineReport.drift_report` and increment the `drift_alerts` metric for downstream dashboards.
- Set `DRIFT_ALERT_OUTPUT` (default `data/observability/whylogs/alerts.json`) to control where append-only JSON alert logs are written. The log captures run ID, dataset name, exceeded-threshold flag, and the underlying distribution deltas for each execution so SOC teams can stream the file into log shipping or SIEM tooling.
- Expose Prometheus gauges by pointing `DRIFT_PROMETHEUS_OUTPUT` (default `data/observability/whylogs/metrics.prom`) at a directory scraped by node_exporter/textfile collectors. Metrics include `whylogs_drift_alerts_total`, `whylogs_drift_exceeded_threshold`, per-dimension ratio deltas, and the last generated timestamp, making it simple to wire Grafana dashboards and alert rules without parsing JSON. Sample alerting rules are available at `tools/observability/prometheus/drift_rules.yaml`; drop them into your Prometheus rules directory to notify on sustained drift conditions.
- Provide a Grafana starting point with `docs/observability/whylogs-dashboard.json`. Import the dashboard (UID `whylogs-drift`) and hook the `dataset` variable to the textfile metric labels to monitor active runs. The template surfaces alert counts, ratio deltas, and threshold breaches in a single panel.
- Optional Slack routing: set `DRIFT_SLACK_WEBHOOK` to an incoming webhook URL (and optionally `DRIFT_DASHBOARD_URL` to link back to Grafana). When drift exceeds the configured threshold the pipeline posts a summary message containing alert counts and the highest variance categories. Failures are logged to the pipeline metrics under `drift_alert_notifications_failed`.
- Generate or refresh baselines with `python -m tools.observability.seed_drift_baseline` (defaults to `data/sample.csv` and writes artifacts to `data/observability/whylogs/`). Run the same command against production datasets to recalibrate after confirmed distribution shifts.
- Set `DRIFT_REQUIRE_BASELINE=1` and `DRIFT_REQUIRE_WHYLOGS_METADATA=1` to raise `drift_baseline_missing` and `whylogs_baseline_missing` sanity findings when either artefact is absent, ensuring analysts remediate missing baselines before promoting a run.

### Mutation testing pilot

- Install the mutation tooling with `poetry install --with dev` (mutmut ships in the default development profile).
- Execute `poetry run python -m apps.automation.cli qa mutation` to launch the pilot. The command runs mutmut against pipeline hotspots (`firecrawl_demo/application/pipeline.py`, `firecrawl_demo/integrations/research/core.py`) using the focused pytest suite (`tests/test_pipeline.py`, `tests/test_research_logic.py`).
- Artefacts are written to `artifacts/testing/mutation/` including the raw `mutmut_results_<timestamp>.txt` output and a JSON summary with the exit code, targets, and test selection. A `latest.txt` symlink is maintained for dashboards that tail the newest run.
- Use `--dry-run` when sanity checking CI wiring; the summary file is generated without invoking mutmut so integration tests remain deterministic.
- Configure dashboards or QA checks to enforce the desired mutation score. Mutmut returns a non-zero exit code when surviving mutants remain, allowing CI to fail until gaps are addressed.

### Backstage TechDocs & Golden Path

- Backstage metadata lives in `catalog-info.yaml` and tracks the system/component/resources for the enrichment stack. Register this file in your Backstage instance to surface the service, TechDocs, and ownership.
- CI publishes TechDocs through `.github/workflows/techdocs.yml`. The workflow generates the static site with `techdocs-cli generate --no-docker` and uploads it as an artifact (`techdocs-site`). Consume it directly or attach a publish step compatible with your TechDocs backend (S3, GCS, etc.).
- New services should start from `templates/golden-path/`, which encodes plan→commit guardrails, TechDocs scaffolding, and bootstrap scripts that call `python -m scripts.bootstrap_env`. Update placeholders in `catalog-info.yaml` and `docs/index.md` before registering new components.
- Onboarding docs (`CONTRIBUTING.md`, `README.md`) reference the golden-path template; ensure new projects either use the template or document deviations in their ADRs.

### Graph semantics metrics

- CSVW and R2RML outputs now enforce configurable bounds via `GRAPH_SEMANTICS_ENABLED=1` and the `GRAPH_MIN_*` / `GRAPH_MAX_*` environment variables.
- Defaults guard against empty provinces/statuses, isolated organisation nodes, and low-degree graphs. Violations are reported as `GraphValidationIssue` entries (for example `PROVINCE_NODE_UNDERFLOW`, `EDGE_UNDERFLOW`, or `AVG_DEGREE_UNDERFLOW`) and counted in the pipeline metrics.

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

## QA Automation Guardrails

Automation across CI, ephemeral runners, and local development is now driven entirely by `apps.automation.cli`. The CLI orchestrates linting, type-checking, security scans, contract verification, mutation smoke tests, and evidence plan workflows without the legacy problems reporter artefacts.

### Pipeline Overview

- `qa all` mirrors the full CI workflow (cleanup, dependency verification, tests, lint/type/security checks, dbt contracts, build, signing) and can optionally generate plan/commit artefacts on the fly.
- `qa lint`, `qa typecheck`, `qa mutation`, `qa security`, `qa contracts`, and `qa build` expose focused subsets for faster iteration.
- `qa fmt` and `qa fmt --generate-plan` wrap Ruff/isort/Black with plan→commit enforcement so formatting changes remain auditable.
- Each command prints a Rich table summarising execution status, durations, and return codes. When `--generate-plan` is used, compliant plan/commit artefacts are written automatically and include step-by-step instructions for the executed QA tasks.

### Integration with Plan→Commit

Destructive or repo-wide commands (cleanup, fmt, all) require plan/commit acknowledgement. Supply existing artefacts via `--plan` / `--commit` or allow the CLI to create them with `--generate-plan`. Artefacts embed:

- The ordered command list executed (or planned) with shell-safe arguments.
- Any tags used to express intent (e.g., `dbt`, `formatting`, `security`).
- The contract schema version so evidence remains verifiable over time.

This approach replaces the previous `problems_report.json` workflow with richer provenance that slots directly into MCP and analyst review gates.

### Ephemeral Runner Support

The automation CLI is tuned for disposability:

- On Python <3.13 it will bootstrap a pinned interpreter via uv when `--auto-bootstrap` (default) is enabled.
- Type checking automatically reuses vendored stubs by exporting `MYPYPATH` internally, so `qa typecheck` delivers consistent results without the manual `run_with_stubs.sh` wrapper.
- When optional tooling is missing (e.g., SQLFluff or Bandit on minimal containers) the CLI reports the gap in the console summary and continues executing the remaining stages, mirroring CI.
- The `qa dependencies` command verifies bootstrap scripts, wheelhouse availability, and stub cache freshness so subsequent QA runs do not encounter missing binaries.

### Minimal Setup Recipes

For ephemeral agents with limited bandwidth:

```bash
# install only mandatory CLI dependencies
poetry install --no-root --with dev --sync

# run targeted QA without destructive actions
poetry run python -m apps.automation.cli qa lint --no-auto-bootstrap
poetry run python -m apps.automation.cli qa typecheck --no-auto-bootstrap
poetry run python -m apps.automation.cli qa mutation --dry-run
```

The Rich tables highlight failing tools, durations, and remediation hints. Because the CLI captures stdout/stderr previews for failing steps, contributors can triage issues directly from ephemeral logs without opening auxiliary artefacts.

**💡 For detailed guidance on constrained environments, see [Ephemeral QA Guide](ephemeral-qa-guide.md).**

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

### Vendored type stubs (offline QA)

The QA suite relies on a vendored cache of third-party type stubs so that `mypy`
and Ruff succeed without network access. Refresh the cache
whenever stub dependencies change:

```bash
poetry run python -m scripts.sync_type_stubs --sync
```

The command resolves versions from `poetry.lock`, installs the stubs into
`stubs/third_party`, and records a manifest for reproducibility. Ephemeral and
air-gapped runners only need to run the verification step (automatically wired
into `qa dependencies`):

```bash
poetry run python -m scripts.sync_type_stubs
```

If verification fails, regenerate the cache on a connected workstation with
`--sync`, commit the updated stubs + manifest, and rerun the QA command.

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

## Troubleshooting

### Common Issues

**Poetry environment issues:**

```bash
# Clear Poetry cache and reinstall
poetry cache clear --all .
poetry install --no-root

# Check Python version compatibility
python --version  # Should be 3.13.x
poetry env info
```

**Test failures:**

```bash
# Run specific failing test with verbose output
./scripts/run_pytest.sh tests/test_specific.py::TestClass::test_method -v -s

# Check for dependency conflicts
poetry show --tree | grep -A 5 -B 5 <problematic_package>
```

**Evidence logging not working:**

```bash
# Validate evidence log structure
poetry run python -c "import pandas as pd; pd.read_csv('data/interim/evidence_log.csv').head()"

# Check file permissions
ls -la data/interim/evidence_log.csv
```

**MCP server connection issues:**

```bash
# Test MCP server startup
poetry run python -m app.cli mcp-server --help

# Check for port conflicts
lsof -i :3000  # Assuming default MCP port
```

**Data quality contract failures:**

```bash
# Run contracts with verbose output
poetry run python -m app.cli contracts data/sample.csv --verbose

# Check dbt logs
tail -f analytics/logs/dbt.log
```

### Performance Issues

**Slow enrichment runs:**

- Enable caching: Set `FEATURE_ENABLE_CACHE=1`
- Use offline mode: Unset `FEATURE_ENABLE_FIRECRAWL_SDK`
- Profile with: `poetry run python -m cProfile -s time your_script.py`

**Memory usage:**

- Process in batches: Use `--batch-size` parameter in CLI commands
- Monitor with: `poetry run mprof run your_script.py`

### Getting Help

1. Check `problems_report.json` for automated issue detection
2. Review CI logs for similar failures
3. Search existing issues in the repository
4. Run `poetry run python -m dev.cli qa all --verbose` for detailed diagnostics

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
