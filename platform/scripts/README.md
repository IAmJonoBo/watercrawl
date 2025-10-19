# Script Operations Guardrails

This directory documents operational automation used by the Platform team. The
Python modules live in the repository root under `scripts/`; this folder
explains purpose, ownership, and escalation paths.

Guidelines:

- Each script must declare required environment variables and describe expected
  side effects before execution.
- Regenerate `problems_report.json` with `scripts/collect_problems.py` after
  modifying lint/type configurations.
- Prefer idempotent operations and add dry-run modes to new utilities.
