# Next Steps

## Tasks
- [x] Baseline remediation plan — Owner: AI — Due: Complete
- [x] Develop enhanced enrichment architecture & pipeline hardening — Owner: AI — Due: Complete
- [x] Implement CLI + MCP bridge for task orchestration — Owner: AI — Due: Complete
- [x] Stand up MkDocs documentation portal — Owner: AI — Due: Complete

## Steps
- [x] Document current-state architecture and gaps
- [x] Design target-state modules (data ingestion, validation, enrichment, evidence logging)
- [x] Implement incremental code/test updates per module
- [x] Integrate QA gates (lint, type, security, tests) into workflow

## Deliverables
- [x] Updated enrichment pipeline with validated + auto-enriched CSV/XLSX processing
- [x] CLI entrypoints for batch runs, validation, and reporting
- [x] Minimal MCP server contract for Copilot orchestration
- [x] MkDocs site with methodology, API, and operations docs

## Quality Gates
- [x] Tests: pytest with coverage >= existing baseline (TBD after remediation)
- [x] Lint: Ruff/Black/Isort clean
- [x] Type: mypy clean with strict config (to be defined)
- [x] Security: bandit critical findings resolved
- [x] Build: poetry build succeeds

## Links
- [x] Baseline test failure log — see docs/gap-analysis.md
- [x] Coverage trend — pytest coverage report captured in CI logs
- [x] Architecture docs — docs/architecture.md

## Risks/Notes
- [ ] Optional Firecrawl integration pending real SDK availability; CLI/pipeline operate with research adapters for now.
- [ ] Type stubs handled via `type: ignore`; consider adding official stubs to dependencies.
- [ ] Pre-commit tooling still absent; evaluate adding packaged entrypoint or doc instructions in future iteration.
