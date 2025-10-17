# ACES Aerodynamics Enrichment Stack

Modular toolkit for validating and enriching South African flight-school datasets. The stack emphasises evidence-backed research, POPIA-compliant contact handling, and automation surfaces for analysts and GitHub Copilot.

## Getting Started

**Python version required:** `>=3.11,<3.14` (recommended: 3.13.x)

**Environment setup:**

```bash
# Install Poetry if not already installed
pip install poetry

# Set Python version for the project (recommended: 3.13)
poetry env use 3.13

# Install all dependencies (including Firecrawl SDK)
poetry install --no-root

# Run CLI commands
poetry run python -m firecrawl_demo.cli validate data/sample.csv --format json
poetry run python -m firecrawl_demo.cli enrich data/sample.csv --output data/sample_enriched.csv
poetry run python -m firecrawl_demo.cli contracts data/sample_enriched.csv --format text
```

The repository now ships a ready-to-run sample dataset at `data/sample.csv` so analysts and Copilot can exercise the pipeline without additional setup.

**Firecrawl SDK integration:**

- The [official Firecrawl Python SDK](https://docs.firecrawl.dev/sdks/python) is available as an optional dependency.
- The CLI and pipeline default to deterministic research adapters so offline QA remains stable.
- Set `FEATURE_ENABLE_FIRECRAWL_SDK=1`, `ALLOW_NETWORK_RESEARCH=1`, and your `FIRECRAWL_API_KEY` (via `.env` or the environment)
  when you are ready to exercise the live SDK.

**No requirements.txt needed:** Poetry is the single source of dependency management. Use `pyproject.toml` for all dependencies.

## Features

- **Dataset validation** with detailed issue reporting (`firecrawl_demo.validation`).
- **Research adapters** for deterministic enrichment and future OSINT integrations (`firecrawl_demo.research`).
- **Feature-flagged Firecrawl integration** guarded by `FEATURE_ENABLE_FIRECRAWL_SDK` and `ALLOW_NETWORK_RESEARCH` so offline QA stays deterministic.
- **Triangulated intelligence** that merges regulator, press, and directory evidence to spot rebrands or ownership changes.
- **Pipeline orchestrator** producing `PipelineReport` objects for UI/automation (`firecrawl_demo.pipeline`).
- **CLI** commands for analysts and automation runs (`firecrawl_demo.cli`).
- **Automated sanity checks** that normalise URLs, clear invalid contacts, surface duplicate organisations, and feed
  remediation guidance into the evidence log and MCP.
- **Data contracts** with a dual Great Expectations + dbt suite, executed via the `contracts`
  CLI command and archived as evidence artefacts for each dataset revision.
- **Lineage + lakehouse artefacts** generated alongside every enrichment run (OpenLineage, PROV-O, DCAT, and snapshot manifests) so analysts can trace provenance and reproduce curated tables.
- **MCP server** exposing JSON-RPC tasks to GitHub Copilot (`firecrawl_demo.mcp.server`).
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
poetry run pytest --maxfail=1 --disable-warnings --cov=firecrawl_demo --cov-report=term-missing
poetry run ruff check .
poetry run mypy .
poetry run bandit -r firecrawl_demo
poetry run pre-commit run --all-files
poetry run dbt build --project-dir analytics --profiles-dir analytics --target ci --select tag:contracts --vars '{"curated_source_path": "data/sample.csv"}'
```

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
