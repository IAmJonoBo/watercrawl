# Copilot instructions for Watercrawl

This repository contains the Watercrawl / Firecrawl demo enrichment toolkit (Python 3.13+).

When Copilot coding agent is asked to make changes in this repository, follow these guidelines to produce useful, auditable, and testable pull requests.

Project quick-start (what Copilot should use when running or testing locally)
- Build & dependencies (Poetry):
  - Install dependencies: `PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 poetry install --no-root --with dev`
  - Tests: `poetry run pytest -q`
  - Type-checking: `./scripts/run_with_stubs.sh -- poetry run mypy . --show-error-codes`
  - Lint & format: `poetry run ruff . && poetry run black . && poetry run isort .`
  - Quick autofix: `python3 scripts/autofix.py --poetry` or `python3 scripts/autofix.py ruff --poetry`

- Node tooling (docs/front-end):
  - Enable corepack and pnpm: `corepack enable && corepack prepare pnpm@latest --activate`
  - Install workspace packages: `pnpm install --frozen-lockfile`

What files to change
- Prefer editing code under `firecrawl_demo/`, scripts in `scripts/`, CLI/automation under `apps/` and related tests under `tests/`.

Code standards & checks (acceptance criteria)
- New or changed code must include unit tests where appropriate and all tests must pass.
- Must satisfy type-checking (mypy), linting (ruff/black/isort), and the automation QA entry points (`poetry run python -m apps.automation.cli qa lint`, `qa typecheck`, `qa mutation`) when relevant.
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
- Run QA lint suite: `poetry run python -m apps.automation.cli qa lint --no-auto-bootstrap`
- Run QA type-check suite: `poetry run python -m apps.automation.cli qa typecheck --no-auto-bootstrap`
- Run QA mutation smoke: `poetry run python -m apps.automation.cli qa mutation --dry-run`
- Run autofix for all tools: `python3 scripts/autofix.py --dry-run` (inspect first), then `python3 scripts/autofix.py`
- Run autofix for specific tool: `python3 scripts/autofix.py ruff` or `python3 scripts/autofix.py black`

Copilot QA cadence
- At session start: `poetry run python -m apps.automation.cli qa lint --no-auto-bootstrap` to surface formatter and lint issues early.
- When Python types or core contracts change, run `poetry run python -m apps.automation.cli qa typecheck --no-auto-bootstrap`.
- Before opening or updating a PR, execute the relevant QA commands (`qa lint`, `qa typecheck`, `qa mutation --dry-run`) and address any failures locally.
- Optional: if Trunk is installed, `poetry run trunk check` provides an aggregated view of lint diagnostics; treat Trunk findings with the same priority as the standalone QA commands.

Remediation workflow
- Use `python3 scripts/autofix.py --dry-run` to preview fixers, then rerun without `--dry-run` for the desired tool (e.g., `python3 scripts/autofix.py ruff`).
- When QA commands surface blockers that cannot be resolved immediately, capture the debt in the PR description (or a follow-up issue) with owners and expected resolution.
- Append supporting evidence to `data/interim/evidence_log.csv` whenever a change affects enrichment data or QA guardrails.

Notes
- If a QA command fails because dependencies are missing, follow `ENVIRONMENT.md` setup guidance or escalate to a maintainer before continuing.
- When automation guardrails fail on CI but pass locally, include command output snippets in the PR discussion to help reviewers reproduce the issue.

If you need to run interactive iterations on a PR, a human reviewer with write access can `@copilot` in PR comments to request follow-ups.
