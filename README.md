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
PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 poetry install --no-root

# Refresh vendored type stubs for offline QA tooling
poetry run python -m scripts.sync_type_stubs --sync

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

## Node & pnpm (developer note)

This repository uses pnpm for Node dependency management. The repo includes `pnpm-lock.yaml` files at the root and the docs site (`docs-starlight/`).

To prepare your environment:

```bash
corepack enable
corepack prepare pnpm@latest --activate
pnpm install --frozen-lockfile
cd docs-starlight && pnpm install --frozen-lockfile
```

If you don't want to pin the lockfile locally during development, omit `--frozen-lockfile`.

We include `pnpm-workspace.yaml` to manage the root project and the docs subproject as a workspace so you can run cross-package scripts with `pnpm -w`.

**Crawlkit adapters + optional Firecrawl SDK:**

- `crawlkit/` provides first-party fetch, render, distill, entity extraction, and Celery orchestration modules that replace the
  former Firecrawl demos while remaining deterministic by default.
- FastAPI surfaces under `/crawlkit` expose `/crawl`, `/markdown`, and `/entities` endpoints so automation clients and MCP tools
  can reuse the same primitives as the CLI.
- Feature flags keep migrations reversible: enable Crawlkit adapters with `FEATURE_ENABLE_CRAWLKIT=1` and opt into the
  production Firecrawl SDK by additionally setting `FEATURE_ENABLE_FIRECRAWL_SDK=1`, `ALLOW_NETWORK_RESEARCH=1`, and
  `FIRECRAWL_API_KEY` (via `.env` or the environment). Both flags default to `0` so offline QA and evidence gathering remain
  deterministic until reviewers sign off.

**Automation CLI auto-bootstrap:** `apps.automation.cli` now provisions Python 3.13 with uv whenever the active interpreter is older than 3.13. This keeps ephemeral runners and fresh shells aligned with the minimum supported version while installing project dependencies before QA commands run.

**No requirements.txt needed:** Poetry is the single source of dependency management. Use `pyproject.toml` for all dependencies.

**Offline installation (for air-gapped environments):**

```bash
# Inspect the offline plan (verifies caches before running)
python -m scripts.bootstrap_env --offline --dry-run

# Execute the cached bootstrap plan
python -m scripts.bootstrap_env --offline
```

When running offline, seed the following caches ahead of time:

- `artifacts/cache/playwright/` containing the Chromium, Firefox, and WebKit archives for Playwright (copied from a connected machine).
- `artifacts/cache/tldextract/publicsuffix.org-tlds/*.tldextract.json` to satisfy the public suffix lookups without network access.
- `artifacts/cache/node/` populated with `*.tgz` tarballs for npm/pnpm so JavaScript installs can operate entirely from disk.
- `artifacts/cache/pip/` housing pre-downloaded Python wheels if you intend to use `uv pip sync` in fully air-gapped environments.
  The mirror helper (`python scripts/mirror_wheels.py`) refreshes cp314/cp315
  wheel inventories under `artifacts/cache/pip/<python-tag>/` and copies the
  wheels into the cache root alongside `mirror_state.json`, which records the
  lockfile hash and blocker snapshot used during the run. Use
  `python scripts/mirror_wheels.py --dry-run` to verify the cache matches the
  current `poetry.lock` before invoking `uv pip sync` offline.

**Note:** By default, `uv` uses its own cache directory (typically at `~/.cache/uv`). To ensure `uv pip sync` uses your pre-populated cache at `artifacts/cache/pip/` during offline installation, set the `UV_CACHE_DIR` environment variable before running the bootstrap command:

```bash
export UV_CACHE_DIR="$(pwd)/artifacts/cache/pip/"
python -m scripts.bootstrap_env --offline
The exported requirements files include pinned versions with SHA256 hashes for reproducible, secure installations, and the offline bootstrap flow uses those hashes with `uv pip sync` to hydrate `.venv/` deterministically.

**Dependency download resilience:**

The repository includes comprehensive timeout and retry configurations for all dependency managers to ensure reliable installations even with network issues:

- **pip**: Configured via `.config/pip/pip.conf` with 60-second timeout and 5 retries
- **Poetry**: Environment variables set in workflows and justfile recipes (`PIP_TIMEOUT=60`, `PIP_RETRIES=5`, `POETRY_INSTALLER_MAX_WORKERS=10`)
- **pnpm**: Configured via `.npmrc` with 60-second timeout and 5 retries with exponential backoff

To verify all configurations are correct:

```bash
./scripts/test_dependency_config.sh
```

See [docs/dependency-resilience.md](docs/dependency-resilience.md) for complete details.

## Features

- **Crawlkit modules** provide end-to-end crawl orchestration: polite fetching with robots.txt compliance, deterministic
  distillation to Markdown, entity extraction, and Celery task chaining (`crawlkit/fetch`, `crawlkit/distill`, `crawlkit/extract`,
  `crawlkit/orchestrate`).
- **FastAPI + CLI surfaces** expose Crawlkit functionality at `/crawlkit/crawl`, `/crawlkit/markdown`, and `/crawlkit/entities`
  while keeping the analyst CLI backward compatible via `watercrawl.interfaces.cli`.
- **Research adapters** combine Crawlkit, regulator, press, and directory intelligence (`watercrawl.integrations.research`)
  with feature flags to toggle Firecrawl or offline-only modes.
- **Dataset validation** with detailed issue reporting (`watercrawl.domain.validation`).
- **Pipeline orchestrator** producing `PipelineReport` objects for UI/automation (`watercrawl.application.pipeline`).
- **Configurable refinement profiles** living under `profiles/` to capture geography, taxonomy, evidence, and contact rules for
  any white-labeled deployment.
- **Automated sanity checks** that normalise URLs, clear invalid contacts, surface duplicate organisations, and feed
  remediation guidance into the evidence log and MCP.
- **Graph semantics + drift observability** with CSVW/R2RML validation, configurable node/edge thresholds, and mandatory whylogs
  baselines that surface `drift_baseline_missing` / `whylogs_baseline_missing` sanity findings when artefacts are absent.
- **Plan→commit safety gate** enforcing plan and commit artefacts (including `If-Match` headers and RAG metrics),
  prompt-injection heuristics, and append-only audit logs to `data/logs/plan_commit_audit.jsonl` for MCP and CLI writes.
- **Data contracts** with a dual Great Expectations + dbt suite, executed via the `contracts`
  CLI command and archived as evidence artefacts for each dataset revision.
- **Lineage + lakehouse artefacts** generated alongside every enrichment run (OpenLineage, PROV-O, DCAT, and snapshot manifests)
  so analysts can trace provenance and reproduce curated tables. PROV graphs record the enrichment agent, evidence counts, and
  quality metrics while DCAT entries expose reproducibility commands, contact metadata, and distribution links for manifests and
  lineage bundles. CLI runs now print the lineage directory plus lakehouse/version manifest paths for immediate runbook
  inclusion.
- **Versioned lakehouse snapshots** with deterministic fingerprints and reproduce commands captured in `data/versioning/`.
- **MCP server** exposing JSON-RPC tasks to GitHub Copilot (`watercrawl.interfaces.mcp.server`).
- **Infrastructure planning** module that codifies crawler, observability, policy, and plan→commit guardrails (`watercrawl.infrastructure.planning`).
- **MkDocs documentation** under `docs/` with architecture, gap analysis, and SOPs.

## Feature Flags & Environment Variables

- `FEATURE_ENABLE_CRAWLKIT=0` — toggle first-party Crawlkit adapters (fetch, distill, extract, orchestrate). Enable when ready to replace the legacy Firecrawl demos end-to-end.
- `FEATURE_ENABLE_FIRECRAWL_SDK=0` — prefer the production Firecrawl SDK when available; requires Crawlkit to be enabled and network access to be explicitly allowed.
- `ALLOW_NETWORK_RESEARCH=0` — permit live network lookups when set to `1` (default: offline-only triangulation).
- `FEATURE_ENABLE_PRESS_RESEARCH=0` or `FEATURE_ENABLE_REGULATOR_LOOKUP=0` — disable specific intelligence sources.
- `FEATURE_INVESTIGATE_REBRANDS=0` — skip rename/ownership heuristics.
- `REFINEMENT_PROFILE=za_flight_schools` — select the profile identifier to load (defaults to the South African flight school profile).
- `REFINEMENT_PROFILE_PATH=/abs/path/to/profile.yaml` — override the profile file path explicitly; takes precedence over `REFINEMENT_PROFILE`.

When offline, the pipeline still records reminders in the evidence log so analysts can follow up manually.

## Tests & QA

```bash
poetry run python -m scripts.cleanup --dry-run  # inspect cleanup targets
poetry run python -m scripts.cleanup            # remove cached artefacts
./scripts/run_pytest.sh --maxfail=1 --disable-warnings --cov=watercrawl --cov-report=term-missing
poetry run ruff check .
poetry run python -m tools.sql.sqlfluff_runner
poetry run yamllint --strict -c .yamllint.yaml .
poetry run pre-commit run markdownlint-cli2 --all-files
poetry run pre-commit run hadolint --all-files
poetry run pre-commit run actionlint --all-files
poetry run mypy .
poetry run bandit -r watercrawl
poetry run python -m tools.security.offline_safety --requirements requirements.txt --requirements requirements-dev.txt
poetry run pre-commit run --all-files
poetry run dbt build --project-dir data_contracts/analytics --profiles-dir data_contracts/analytics --target ci --select tag:contracts --vars '{"curated_source_path": "data/sample.csv"}'
poetry run python apps/analyst/accessibility/axe_smoke.py
# Aggregate lint/type issues (add --autofix to run available fixers before reporting)
poetry run python -m apps.automation.cli qa lint --no-auto-bootstrap
poetry run python -m apps.automation.cli qa typecheck --no-auto-bootstrap
poetry run python -m apps.automation.cli qa mutation --dry-run
```

> **Ephemeral Runner Support:** The automation QA commands (`qa lint`, `qa typecheck`, `qa mutation`) are resilient on ephemeral runners (GitHub Actions, Copilot sandboxes) with minimal dependencies. They bootstrap vendored tooling automatically and allow partial QA results even when the full environment isn't available. See [docs/operations.md](docs/operations.md#qa-automation-workflows) for details.

> `requirements-dev.txt` hashes refreshed on **2025-10-23 (UTC)** via
> `poetry export -f requirements.txt --with dev --output requirements-dev.txt`.
> Repeat the export whenever dependency versions change to keep offline QA
> reproducible.

> Ruff enforces the Flake8 rule families (`E`, `F`, `W`) alongside Bugbear (`B`), import sorting (`I`), and security linting (`S`), eliminating the need to run Flake8 separately.

> The offline Safety runner relies on the vendored `safety-db` snapshot so QA can execute without network connectivity. Update the dependency periodically to refresh advisories.

> The `scripts/run_pytest.sh` wrapper discovers the Poetry-managed Python 3.13 interpreter (or provisions one via `uv`) so `pytest` never falls back to a stale system binary.

The analyst CLI now accepts `--profile`/`--profile-path` switches on `validate`, `enrich`, and `contracts` so white-labeled profiles can be selected per run. The MCP server exposes matching `list_profiles` and `select_profile` actions for GitHub Copilot and local LLM copilots.

## Supply Chain Hardening

- GitHub Actions runs an OpenSSF Scorecard workflow on `main` and weekly schedules to track supply-chain posture (see `.github/workflows/scorecard.yml`).
- The primary CI job now publishes CycloneDX SBOMs (`artifacts/sbom/cyclonedx.json`) and Sigstore bundles for the built wheel and sdist (`artifacts/signatures/`).
- Verify a signed artifact locally with:

  ```bash
  sigstore verify identity \
    --cert-identity "https://github.com/IAmJonoBo/watercrawl/.github/workflows/ci.yml@refs/heads/main" \
    --cert-oidc-issuer https://token.actions.githubusercontent.com \
    --bundle artifacts/signatures/bundles/dist/watercrawl-*.whl.sigstore \
    dist/watercrawl-*.whl
  ```

- CI enforces policy-as-code verification via `scripts.verify_artifact_signatures`, blocking uploads when Sigstore bundles are missing or bound to the wrong GitHub workflow identity.
- Track Python 3.14/3.15 wheel readiness with `poetry run python -m scripts.wheel_status --output tools/dependency_matrix/wheel_status.json`; the report highlights blockers defined in `presets/dependency_blockers.toml`.

- Developers should configure [gitsign](https://github.com/sigstore/gitsign) locally (`gitsign init && git config --global commit.gpgsign true`) so every commit is OIDC-signed by default.

## Accessibility Checks

- The Streamlit analyst UI ships with an axe-core smoke test (`poetry run python apps/analyst/accessibility/axe_smoke.py`) that launches the app headlessly and reports WCAG violations. Known Streamlit chrome issues are whitelisted; any new violations fail CI and drop an `axe-results.json` artifact for triage.

## Documentation

**📚 Full documentation is available at [https://iamjonobo.github.io/watercrawl/](https://iamjonobo.github.io/watercrawl/)**

The documentation follows the **Diátaxis framework** for systematic technical documentation:

- **Tutorials** (Learning-Oriented): Step-by-step guides for new users
  - [Getting Started](/guides/getting-started/)
  - [First Enrichment Tutorial](/guides/tutorials/first-enrichment/)
  - [Working with Profiles](/guides/tutorials/profiles/)
  - [MCP Setup](/guides/tutorials/mcp-setup/)

- **How-To Guides** (Problem-Oriented): Practical solutions
  - [CLI Commands](/cli/)
  - [MCP Integration](/mcp/)
  - [Troubleshooting](/guides/troubleshooting/)

- **Reference** (Information-Oriented): Technical specifications
  - [API Reference](/reference/api/)
  - [Configuration](/reference/configuration/)
  - [Data Contracts](/reference/data-contracts/)

- **Explanation** (Understanding-Oriented): Conceptual deep-dives
  - [Architecture](/architecture/)
  - [Data Quality](/data-quality/)
  - [Lineage & Lakehouse](/lineage-lakehouse/)
  - [Operations](/operations/)
  - [Ephemeral QA Guide](/ephemeral-qa-guide/) - Quick-start for Copilot agents
  - [Architecture Decision Records (ADRs)](/adr/)

### Preview Documentation Locally

```bash
cd docs-starlight
pnpm install
pnpm run dev
# Open http://localhost:4321
```

### Build Documentation

```bash
cd docs-starlight
pnpm run build
# Output: docs-starlight/dist/
```

## Repository layout

- `watercrawl/core/` — canonical business logic, validation, pipeline orchestration, and shared models.
- `crawlkit/` — first-party fetch/distill/extract/orchestrate modules replacing the legacy demos.
- `watercrawl/integrations/` — contracts, research adapters, lineage, lakehouse, drift, and optional Firecrawl client bindings.
- `watercrawl/governance/` — safety, evaluation, and secrets providers isolated from crawler orchestration.
- `watercrawl/interfaces/` — CLI, analyst UI, and MCP orchestration entrypoints.
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
poetry run python -m watercrawl.mcp.server
```

See `codex/README.md` for the full workflow, including optional read-only context servers.

## Contributing

1. Run the baseline QA suite before committing.
2. Update/extend tests first.
3. Keep `Next_Steps.md` in sync with progress and risks.
4. Update MkDocs content when behaviour changes.
