# ACES Aerodynamics Enrichment Stack

Modular toolkit for validating and enriching South African flight-school datasets. The stack emphasises evidence-backed research, POPIA-compliant contact handling, and automation surfaces for analysts and GitHub Copilot.

## Getting Started

**Python version required:** `>=3.13,<3.15` (baseline: 3.13.x)

**Environment setup:**

```bash
# Inspect and execute the consolidated bootstrap plan
python -m scripts.bootstrap_env --dry-run
python -m scripts.bootstrap_env

# Manual steps when you need finer-grained control
python -m scripts.bootstrap_python --install-uv --poetry
poetry install --no-root

# Refresh the dependency compatibility report and confirm only allow-listed
# wheel blockers remain before kicking off QA
python -m scripts.dependency_matrix survey --config presets/dependency_targets.toml --output tools/dependency_matrix/report.json
python -m scripts.dependency_matrix guard --config presets/dependency_targets.toml --blockers presets/dependency_blockers.toml --status-output tools/dependency_matrix/status.json

# Run end-user CLI commands (analyst workflow)
poetry run python -m apps.analyst.cli overview
poetry run python -m apps.analyst.cli validate data/sample.csv --format json
poetry run python -m apps.analyst.cli enrich data/sample.csv --output data/sample_enriched.csv
poetry run python -m apps.analyst.cli contracts data/sample_enriched.csv --format text

# Developer DX helpers mirroring CI
poetry run python -m apps.automation.cli qa plan  # add --write-plan/--write-commit to emit artefacts
poetry run python -m apps.automation.cli qa all --dry-run
poetry run python -m apps.automation.cli qa all  # auto-installs Python 3.13 via uv when needed; add --generate-plan to materialise plan/commit artefacts
poetry run python -m apps.automation.cli qa fmt --generate-plan --plan-dir tmp/plans
poetry run python -m apps.automation.cli qa problems --fail-on-issues
```

> `scripts.bootstrap_env` provisions the uv-managed interpreter, installs the
> Poetry environment (using `poetry install --sync`), installs pre-commit hooks, and syncs Node.js dependencies
> for both the repository root and the Starlight documentation site in a single
> run.

> The repository ships a `.python-version` (pyenv) and `poetry.toml` so that local
> virtual environments are created in-project under `.venv/`, ensuring CLI tooling,
> offline runners, and CI all share the same interpreter path without manual
> switching.

The repository now ships a ready-to-run sample dataset at `data/sample.csv` so analysts and Copilot can exercise the pipeline without additional setup.

**Firecrawl SDK integration:**

- The [official Firecrawl Python SDK](https://docs.firecrawl.dev/sdks/python) is available as an optional dependency.
- The CLI and pipeline default to deterministic research adapters so offline QA remains stable.
- Set `FEATURE_ENABLE_FIRECRAWL_SDK=1`, `ALLOW_NETWORK_RESEARCH=1`, and your `FIRECRAWL_API_KEY` (via `.env` or the environment)
  when you are ready to exercise the live SDK.

**Automation CLI auto-bootstrap:** `apps.automation.cli` now provisions Python 3.13 with uv whenever the active interpreter is older than 3.13. This keeps ephemeral runners and fresh shells aligned with the minimum supported version while installing project dependencies before QA commands run.

**No requirements.txt needed:** Poetry is the single source of dependency management. Use `pyproject.toml` for all dependencies.

**Offline installation (for air-gapped environments):**

```bash
# Provision the 3.13 interpreter and sync dependencies with uv
python -m scripts.bootstrap_python --install-uv --poetry
uv pip sync requirements-dev.txt

# For production environments (runtime dependencies only)
uv pip sync requirements.txt
```

The exported requirements files include pinned versions with SHA256 hashes for reproducible, secure installations.

## Features

- **Dataset validation** with detailed issue reporting (`firecrawl_demo.domain.validation`).
- **Research adapters** for deterministic enrichment and future OSINT integrations (`firecrawl_demo.integrations.research`).
- **Feature-flagged Firecrawl integration** guarded by `FEATURE_ENABLE_FIRECRAWL_SDK` and `ALLOW_NETWORK_RESEARCH` so offline QA stays deterministic.
- **Triangulated intelligence** that merges regulator, press, and directory evidence to spot rebrands or ownership changes.
- **Pipeline orchestrator** producing `PipelineReport` objects for UI/automation (`firecrawl_demo.application.pipeline`).
- **CLI** commands for analysts and automation runs (`firecrawl_demo.interfaces.cli`).
- **Automated sanity checks** that normalise URLs, clear invalid contacts, surface duplicate organisations, and feed
  remediation guidance into the evidence log and MCP.
- **Graph semantics + drift observability** with CSVW/R2RML validation, configurable node/edge thresholds, and mandatory whylogs baselines that surface `drift_baseline_missing` / `whylogs_baseline_missing` sanity findings when artefacts are absent.
- **Plan→commit safety gate** enforcing plan and commit artefacts (including `If-Match` headers and RAG metrics), prompt-injection heuristics, and append-only audit logs to `data/logs/plan_commit_audit.jsonl` for MCP and CLI writes.
- **Data contracts** with a dual Great Expectations + dbt suite, executed via the `contracts`
  CLI command and archived as evidence artefacts for each dataset revision.
- **Lineage + lakehouse artefacts** generated alongside every enrichment run (OpenLineage, PROV-O, DCAT, and snapshot manifests) so analysts can trace provenance and reproduce curated tables. PROV graphs record the enrichment agent, evidence counts, and quality metrics while DCAT entries expose reproducibility commands, contact metadata, and distribution links for manifests and lineage bundles. CLI runs now print the lineage directory plus lakehouse/version manifest paths for immediate runbook inclusion.
- **Versioned lakehouse snapshots** with deterministic fingerprints and reproduce commands captured in `data/versioning/`.
- **MCP server** exposing JSON-RPC tasks to GitHub Copilot (`firecrawl_demo.interfaces.mcp.server`).
- **Infrastructure planning** module that codifies crawler, observability, policy, and plan→commit guardrails (`firecrawl_demo.infrastructure.planning`).
- **MkDocs documentation** under `docs/` with architecture, gap analysis, and SOPs.

## Feature Flags & Environment Variables

- `FEATURE_ENABLE_FIRECRAWL_SDK=1` — prefer the production Firecrawl SDK when available.
- `ALLOW_NETWORK_RESEARCH=1` — permit live network lookups (default: offline-only triangulation).
- `FEATURE_ENABLE_PRESS_RESEARCH=0` or `FEATURE_ENABLE_REGULATOR_LOOKUP=0` — disable specific intelligence sources.
- `FEATURE_INVESTIGATE_REBRANDS=0` — skip rename/ownership heuristics.

When offline, the pipeline still records reminders in the evidence log so analysts can follow up manually.

## Tests & QA

```bash
poetry run python -m scripts.cleanup --dry-run  # inspect cleanup targets
poetry run python -m scripts.cleanup            # remove cached artefacts
./scripts/run_pytest.sh --maxfail=1 --disable-warnings --cov=firecrawl_demo --cov-report=term-missing
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
poetry run dbt build --project-dir data_contracts/analytics --profiles-dir data_contracts/analytics --target ci --select tag:contracts --vars '{"curated_source_path": "data/sample.csv"}'
poetry run python apps/analyst/accessibility/axe_smoke.py
```

> Ruff enforces the Flake8 rule families (`E`, `F`, `W`) alongside Bugbear (`B`), import sorting (`I`), and security linting (`S`), eliminating the need to run Flake8 separately.

> The offline Safety runner relies on the vendored `safety-db` snapshot so QA can execute without network connectivity. Update the dependency periodically to refresh advisories.

> The `scripts/run_pytest.sh` wrapper discovers the Poetry-managed Python 3.13 interpreter (or provisions one via `uv`) so `pytest` never falls back to a stale system binary.

## Supply Chain Hardening

- GitHub Actions runs an OpenSSF Scorecard workflow on `main` and weekly schedules to track supply-chain posture (see `.github/workflows/scorecard.yml`).
- The primary CI job now publishes CycloneDX SBOMs (`artifacts/sbom/cyclonedx.json`) and Sigstore bundles for the built wheel and sdist (`artifacts/signatures/`).
- Verify a signed artifact locally with:

  ```bash
  sigstore verify identity \
    --cert-identity "https://github.com/IAmJonoBo/watercrawl/.github/workflows/ci.yml@refs/heads/main" \
    --cert-oidc-issuer https://token.actions.githubusercontent.com \
    --bundle artifacts/signatures/bundles/dist/firecrawl_demo-*.whl.sigstore \
    dist/firecrawl_demo-*.whl
  ```

- Developers should configure [gitsign](https://github.com/sigstore/gitsign) locally (`gitsign init && git config --global commit.gpgsign true`) so every commit is OIDC-signed by default.

## Accessibility Checks

- The Streamlit analyst UI ships with an axe-core smoke test (`poetry run python apps/analyst/accessibility/axe_smoke.py`) that launches the app headlessly and reports WCAG violations. Known Streamlit chrome issues are whitelisted; any new violations fail CI and drop an `axe-results.json` artifact for triage.

## Documentation

MkDocs site configuration lives in `mkdocs.yml`. Preview locally with:

```bash
poetry run mkdocs serve
```

Key pages:

- `docs/gap-analysis.md`: current vs target architecture.
- `docs/architecture.md`: layered design and flow diagrams.
- `docs/cli.md`: command usage and examples.
- `docs/mcp.md`: MCP contract for Copilot.
- `docs/operations.md`: QA gates and release process.

## Repository layout

- `firecrawl_demo/core/` — canonical business logic, validation, pipeline orchestration, and shared models.
- `firecrawl_demo/integrations/` — contracts, research adapters, lineage, lakehouse, drift, and Firecrawl client bindings.
- `firecrawl_demo/governance/` — safety, evaluation, and secrets providers isolated from crawler orchestration.
- `firecrawl_demo/interfaces/` — CLI, analyst UI, and MCP orchestration entrypoints.
- `apps/` — deployable application surfaces (`analyst` for humans, `automation` for CI orchestration).
- `tools/` — shared automation helpers (Promptfoo configs, audit recipes, QA fixtures).
- `platform/` — infrastructure guardrails and operational script documentation (see `scripts/` for Python modules).

## Codex developer experience

Codex agents can reuse the same guardrails as analysts by running the Promptfoo scenarios and optional MCP tooling bundled in
`codex/`:

```bash
# Run Codex smoke tests before enabling agent access
promptfoo eval codex/evals/promptfooconfig.yaml

# Launch the in-repo MCP server for Codex sessions
poetry run python -m firecrawl_demo.mcp.server
```

See `codex/README.md` for the full workflow, including optional read-only context servers.

## Contributing

1. Run the baseline QA suite before committing.
2. Update/extend tests first.
3. Keep `Next_Steps.md` in sync with progress and risks.
4. Update MkDocs content when behaviour changes.
