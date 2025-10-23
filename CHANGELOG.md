# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added - Phase 1: Data Contracts & Evidence Enforcement

- **CI Enforcement**: Added contracts command to CI workflow that blocks publish on failures
  - CI now runs `poetry run python -m apps.analyst.cli contracts data/sample.csv --format json`
  - Pipeline fails if any Great Expectations or dbt checks fail
  - Added coverage check step to ensure ≥95% threshold is met

- **Deequ Quality Checks**: Implemented deterministic Deequ enforcement with PySpark fallback
  - `firecrawl_demo.integrations.contracts.deequ_runner` now enforces HTTPS, duplicate detection,
    verified-contact completeness, and confidence thresholds even without PySpark
  - CLI and CI fail when any Deequ check fails, aligning release blockers across GX/dbt/Deequ
  - PySpark availability is still surfaced for future JVM-backed processing
  - Updated `data_contracts/deequ/README.md` with usage, fallback behaviour, and troubleshooting guidance

- **Contract Coverage Tracking**: Implemented coverage tracking to ensure ≥95% of curated tables covered
  - `firecrawl_demo.integrations.contracts.coverage` module calculates coverage metrics
  - Tracks coverage by tool (Great Expectations, dbt, Deequ)
  - `calculate_contract_coverage()` function discovers curated tables and checks for contracts
  - `report_coverage()` generates JSON reports for automation and CI

- **Coverage CLI Command**: Added `coverage` command to analyst CLI
  - Reports contract coverage across all curated tables
  - Supports text and JSON output formats
  - Exits with code 1 if coverage below 95% threshold
  - Shows coverage breakdown by tool and lists uncovered tables
  - Added to analyst CLI overview and command list

- **Tests**: Added comprehensive test coverage for new functionality
  - `tests/test_contract_coverage.py`: Tests for coverage tracking and reporting
  - `tests/test_deequ.py`: Tests for deterministic Deequ checks and failure reporting
  - `tests/test_contracts.py`: Extended CLI coverage to assert Deequ evidence logging and failure messaging
  - All tests validate expected behavior for Phase 1 gates

- **Documentation**: Updated documentation to reflect Phase 1 completion
  - `docs/data-quality.md`: Added Phase 1.3 section documenting Deequ, CI enforcement, and coverage
  - `docs/operations.md`: Added coverage command to Data Quality section
  - `Next_Steps.md`: Marked Phase 1 as complete with completion notes
- **Whylogs Drift Observability**: Introduced alert routing and dashboards
  - Slack webhook notifications triggered when `DRIFT_SLACK_WEBHOOK` is configured and drift exceeds threshold
  - Prometheus/Grafana starter dashboard published at `docs/observability/whylogs-dashboard.json`
  - Operations guide updated with routing instructions and environment variables (`DRIFT_DASHBOARD_URL`, webhook guidance)
  - Added tests covering Slack notifier success/failure paths and pipeline integration
- **Mutation Testing Pilot**: Added mutmut workflow for pipeline hotspots
  - `poetry run python -m apps.automation.cli qa mutation` orchestrates the pilot with curated targets/tests
  - Artefacts written to `artifacts/testing/mutation/` (summary JSON and raw results)
  - Dry-run mode supported for CI validation and documentation updates in `docs/operations.md`
- **Backstage TechDocs Integration**: Catalog metadata, CI publishing, and golden-path template established
  - `catalog-info.yaml` registers the system/component/resource for Backstage
  - `.github/workflows/techdocs.yml` generates TechDocs artifacts using `techdocs-cli`
  - `templates/golden-path/` scaffolds new services with plan→commit guardrails, TechDocs docs, and bootstrap scripts
  - Documentation updated (`README.md`, `docs/operations.md`, `CONTRIBUTING.md`) to reference Backstage onboarding

### Documentation & CLI

- Documented Crawlkit fetch/distill/extract/orchestrate modules and feature flags (`FEATURE_ENABLE_CRAWLKIT`, `FEATURE_ENABLE_FIRECRAWL_SDK`) across README, CONTRIBUTING, MkDocs, and Starlight docs.
- Updated CLI shims, `main.py`, `examples.py`, and automation guidance to import Crawlkit adapters and describe the new `/crawlkit/crawl`, `/crawlkit/markdown`, and `/crawlkit/entities` FastAPI endpoints.
- Refreshed MCP Promptfoo gate documentation to require Crawlkit artefacts in evaluation fixtures and linked QA evidence in Next_Steps.

### Changed

- Updated `firecrawl_demo.integrations.contracts.__init__.py` to export new modules
  - Added `DeequContractResult`, `run_deequ_checks`, `DEEQU_AVAILABLE` exports
  - Added `ContractCoverage`, `calculate_contract_coverage`, `report_coverage` exports
  - Added `DBT_AVAILABLE` and `GREAT_EXPECTATIONS_AVAILABLE` flags to exports

- Updated `firecrawl_demo.interfaces.analyst_cli.py` to include coverage command
  - Imported coverage tracking functions
  - Added `coverage` command with text/JSON output support
  - Command enforces 95% threshold and exits with code 1 on failure

- Updated `apps/analyst/cli.py` to include coverage in user-facing commands
- Replaced the Firecrawl research adapter with a Crawlkit-powered implementation that respects the
  new `FEATURE_ENABLE_CRAWLKIT` flag and falls back gracefully when network access is disabled.
  - Added coverage to `_USER_FACING_COMMANDS` dictionary
  - Included coverage in overview command's ordered command list
- Enhanced the Crawlkit research adapter to surface fetch failure diagnostics and deduplicate
  multi-source seed URLs, with new integration tests covering press/regulator triangulation.

- Updated CI workflow (`.github/workflows/ci.yml`)
  - Added "Run data contracts" step after tests
  - Added "Check contract coverage" step to enforce 95% threshold

### Phase 1 Exit Criteria Met

✅ GX/dbt/Deequ block publish: Contracts enforced in CI, deterministic Deequ checks integrated
✅ Pint/Hypothesis enforced in CI: Tests run as part of pytest suite  
✅ ≥95% curated tables covered: Coverage tracking ensures threshold is met

## [0.1.0] - Previous Work

See commit history for earlier changes. This CHANGELOG starts with Phase 1 completion.
