# ACES Aerodynamics Enrichment Stack

Modular toolkit for validating and enriching South African flight-school datasets. The stack emphasises evidence-backed research, POPIA-compliant contact handling, and automation surfaces for analysts and GitHub Copilot.

## Getting Started

**Python version required:** `>=3.13,<3.14` (recommended: 3.13.x)

**Environment setup:**

```bash
# Install Poetry if not already installed
pip install poetry

# Set Python version for the project (recommended: 3.13)
poetry env use 3.13

# Install all dependencies (including Firecrawl SDK)
poetry install --no-root

# Run end-user CLI commands (analyst workflow)
poetry run python -m app.cli overview
poetry run python -m app.cli validate data/sample.csv --format json
poetry run python -m app.cli enrich data/sample.csv --output data/sample_enriched.csv
poetry run python -m app.cli contracts data/sample_enriched.csv --format text

# Developer DX helpers mirroring CI
poetry run python -m dev.cli qa plan
poetry run python -m dev.cli qa all --dry-run
```

The repository now ships a ready-to-run sample dataset at `data/sample.csv` so analysts and Copilot can exercise the pipeline without additional setup.

**Firecrawl SDK integration:**

- The [official Firecrawl Python SDK](https://docs.firecrawl.dev/sdks/python) is available as an optional dependency.
- The CLI and pipeline default to deterministic research adapters so offline QA remains stable.
- Set `FEATURE_ENABLE_FIRECRAWL_SDK=1`, `ALLOW_NETWORK_RESEARCH=1`, and your `FIRECRAWL_API_KEY` (via `.env` or the environment)
  when you are ready to exercise the live SDK.

**No requirements.txt needed:** Poetry is the single source of dependency management. Use `pyproject.toml` for all dependencies.

**Offline installation (for air-gapped environments):**

```bash
# For development environments (includes testing, linting, type checking tools)
pip install -r requirements-dev.txt

# For production environments (runtime dependencies only)
pip install -r requirements.txt
```

The exported requirements files include pinned versions with SHA256 hashes for reproducible, secure installations.

## Features

- **Dataset validation** with detailed issue reporting (`firecrawl_demo.core.validation`).
- **Research adapters** for deterministic enrichment and future OSINT integrations (`firecrawl_demo.integrations.research`).
- **Feature-flagged Firecrawl integration** guarded by `FEATURE_ENABLE_FIRECRAWL_SDK` and `ALLOW_NETWORK_RESEARCH` so offline QA stays deterministic.
- **Triangulated intelligence** that merges regulator, press, and directory evidence to spot rebrands or ownership changes.
- **Pipeline orchestrator** producing `PipelineReport` objects for UI/automation (`firecrawl_demo.core.pipeline`).
- **CLI** commands for analysts and automation runs (`firecrawl_demo.interfaces.cli`).
- **Automated sanity checks** that normalise URLs, clear invalid contacts, surface duplicate organisations, and feed
  remediation guidance into the evidence log and MCP.
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
poetry run dbt build --project-dir analytics --profiles-dir analytics --target ci --select tag:contracts --vars '{"curated_source_path": "data/sample.csv"}'
```

> Ruff enforces the Flake8 rule families (`E`, `F`, `W`) alongside Bugbear (`B`), import sorting (`I`), and security linting (`S`), eliminating the need to run Flake8 separately.

> The offline Safety runner relies on the vendored `safety-db` snapshot so QA can execute without network connectivity. Update the dependency periodically to refresh advisories.

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
- `dev/` — experimentation workspace for analysts/developers. Codex allowed only after Promptfoo smoke tests pass.
- `tools/` — shared automation helpers (Promptfoo configs, audit recipes, QA fixtures).
- `app/` — deployable application surface consuming the enrichment libraries.
- `dist/` — hardened crawler distribution footprint with Codex integrations disabled.

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
