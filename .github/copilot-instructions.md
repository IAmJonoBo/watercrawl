# Copilot instructions for Watercrawl

This repository contains the Watercrawl / Firecrawl demo enrichment toolkit (Python 3.13+).

When Copilot coding agent is asked to make changes in this repository, follow these guidelines to produce useful, auditable, and testable pull requests.

Project quick-start (what Copilot should use when running or testing locally)
- Build & dependencies (Poetry):
  - Install dependencies: `poetry install --no-root --with dev`
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
- Run collector (regenerate problems report): `poetry run python scripts/collect_problems.py` or `python3 scripts/collect_problems.py --summary`
- Run autofix for all tools: `python3 scripts/autofix.py --dry-run` (inspect first), then `python3 scripts/autofix.py`
- Run autofix for specific tool: `python3 scripts/autofix.py ruff` or `python3 scripts/autofix.py black`

Copilot-specific workflow: run-and-triage the problems reporter
- Run the problems reporter at the start of any fresh session and before opening or updating a PR. This keeps the Problems pane and `problems_report.json` up to date and avoids noisy or surprise failures in CI.
- The problems reporter now includes:
  - Early detection of unavailable tools with setup guidance
  - Performance metrics showing which tools are slowest
  - Actionable autofix commands for supported tools
  - Human-readable summary output with `--summary` flag
- Recommended cadence:
  - At session start: `python3 scripts/collect_problems.py --summary` (works without Poetry)
  - Before creating/updating a PR: run the collector and address any new or bumped issues shown in `problems_report.json`.
  - After making a set of edits locally (especially to workflows, linters, type stubs, or packaging): re-run the collector and ensure the report does not introduce new high-severity items.

Triage steps for issues returned by the collector
- Classify each issue in `problems_report.json` as one of: ` blocker ` (must fix before PR), ` fix-later ` (documented technical debt), or ` informational ` (low/no action).
- For `blocker` items, create a short plan in the PR description and either fix them in the same branch or open a follow-up PR referencing the blocker and why it was deferred.
- For `fix-later` items, add an entry to the repository problems tracker (or an issue) with a short justification, an owner, and ETA.
- Record triage decisions in the PR description and append the relevant evidence to `data/interim/evidence_log.csv` where applicable.

Commands and quick workflow
- Regenerate problems and show a compact summary on the terminal:

```bash
poetry run python scripts/collect_problems.py --output problems_report.json && jq '.summary' problems_report.json || true
```

- Open the full report locally (pretty JSON):

```bash
python -m json.tool problems_report.json | less -R
```

- If a session or CI run reports a previously unseen `blocker`, stop and either fix the blocker locally or create an explicit follow-up `*.plan`/`*.commit` artefact before proceeding (see `AGENTS.md` for Plan→Commit workflow).

Notes
- The collector is the canonical source of repo QA state for Copilot sessions. Copilot must not make large cross-cutting changes without first running and triaging the collector results.
- If the collector cannot run locally because of environment constraints (missing system deps, network, etc.), document the blocker in the PR and escalate to a maintainer for guidance.
  - Troubleshooting: if `scripts/collect_problems.py` fails with import errors like "No module named 'firecrawl_demo'", ensure dev dependencies are installed in the local environment and the command is run from the repository root. Example:

```bash
poetry install --no-root --with dev
poetry run python scripts/collect_problems.py --output problems_report.json
```

If you need to run interactive iterations on a PR, a human reviewer with write access can `@copilot` in PR comments to request follow-ups.
