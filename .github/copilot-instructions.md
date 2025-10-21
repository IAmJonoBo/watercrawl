# Copilot instructions for Watercrawl

This repository contains the Watercrawl / Firecrawl demo enrichment toolkit (Python 3.13+).

When Copilot coding agent is asked to make changes in this repository, follow these guidelines to produce useful, auditable, and testable pull requests.

Project quick-start (what Copilot should use when running or testing locally)
- Build & dependencies (Poetry):
  - Install dependencies: `poetry install --no-root --with dev`
  - Tests: `poetry run pytest -q`
  - Type-checking: `./scripts/run_with_stubs.sh -- poetry run mypy . --show-error-codes`
  - Lint & format: `poetry run ruff . && poetry run black . && poetry run isort .`

- Node tooling (docs/front-end):
  - Enable corepack and pnpm: `corepack enable && corepack prepare pnpm@latest --activate`
  - Install workspace packages: `pnpm install --frozen-lockfile`

What files to change
- Prefer editing code under `firecrawl_demo/`, scripts in `scripts/`, CLI/automation under `apps/` and related tests under `tests/`.

Code standards & checks (acceptance criteria)
- New or changed code must include unit tests where appropriate and all tests must pass.
- Must satisfy type-checking (mypy), linting (ruff/black/isort), and project QA checks in `scripts/collect_problems.py` if applicable.
- Avoid changing generated files, lockfiles, or files under ignored directories: `node_modules`, `dist`, `.astro`, `data`, `artifacts`, `tmp`, `stubs/third_party`.

Tasks suitable for Copilot
- Small, well-scoped changes: bug fixes, unit-test additions, small refactors, documentation, and implementing clear feature requests with acceptance criteria.

Tasks NOT suitable for Copilot (do NOT assign these to the agent)
- Broad, cross-repository refactors and large architectural changes.
- Anything involving secrets, POPIA/PII/data removal, production-critical incident response, or legal/compliance remediation unless explicitly supervised.

Repository helpers and MCP
- An MCP server is available to drive local tooling: `poetry run python -m app.cli mcp-server` (see `AGENTS.md` for details).
- Evidence logging and change guardrails: updates to rows must append to `data/interim/evidence_log.csv` and follow the Plan→Commit artefact workflow. When proposing dataset changes, supply `.plan` and `.commit` artefacts and include RAG metrics.

How to present changes when creating PRs
- Include a short summary of the change, test evidence (what tests were added/updated and their results), and the QA/checklist (mypy/ruff/black/isort, unit tests, any DBT/SQLFluff outputs).
- For any external data or enrichment, document sources and reasoning in the PR description.

Useful commands (for Copilot's ephemeral environment)
- Run tests: `poetry run pytest -q`
- Run mypy: `./scripts/run_with_stubs.sh -- poetry run mypy . --show-error-codes`
- Run collector (regenerate problems report): `poetry run python scripts/collect_problems.py`

If you need to run interactive iterations on a PR, a human reviewer with write access can `@copilot` in PR comments to request follow-ups.
