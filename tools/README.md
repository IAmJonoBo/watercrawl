# Shared Tooling

Utilities, scripts, and reference configurations that support both development and distribution pipelines live in `tools/`.
This includes Promptfoo harnesses, MCP audit recipes, and QA helpers that must remain environment agnostic.

Usage expectations:

- Keep tooling documented with runnable examples and note any dependencies (Node, Poetry, dbt, etc.).
- When adding new quality gates (e.g., CSVW validators, drift alert fixtures), place reusable assets here and reference them
  from `apps/automation/` CLIs or `platform/scripts/` guardrails as appropriate.
- Update `/Next_Steps.md` with links back to relevant tool artefacts whenever a new gate becomes part of the release process.
