# ACES Aerodynamics Enrichment Stack

Modular toolkit for validating and enriching South African flight-school datasets. The stack emphasises evidence-backed research, POPIA-compliant contact handling, and automation surfaces for analysts and GitHub Copilot.

## Quickstart

```bash
poetry install --no-root
poetry run python -m firecrawl_demo.cli validate data/sample.csv --format json
poetry run python -m firecrawl_demo.cli enrich data/sample.csv --output data/sample_enriched.csv
```

Set `FIRECRAWL_API_KEY` in `.env` if you intend to plug in the Firecrawl SDK.

## Features

- **Dataset validation** with detailed issue reporting (`firecrawl_demo.validation`).
- **Research adapters** for deterministic enrichment and future OSINT integrations (`firecrawl_demo.research`).
- **Feature-flagged Firecrawl integration** guarded by `FEATURE_ENABLE_FIRECRAWL_SDK` and `ALLOW_NETWORK_RESEARCH` so offline QA stays deterministic.
- **Triangulated intelligence** that merges regulator, press, and directory evidence to spot rebrands or ownership changes.
- **Pipeline orchestrator** producing `PipelineReport` objects for UI/automation (`firecrawl_demo.pipeline`).
- **CLI** commands for analysts and automation runs (`firecrawl_demo.cli`).
- **MCP server** exposing JSON-RPC tasks to GitHub Copilot (`firecrawl_demo.mcp.server`).
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

## Contributing

1. Run the baseline QA suite before committing.
2. Update/extend tests first.
3. Keep `Next_Steps.md` in sync with progress and risks.
4. Update MkDocs content when behaviour changes.
