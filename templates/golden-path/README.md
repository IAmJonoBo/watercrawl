# Golden-Path Starter Template

This template seeds new services that integrate with the ACES Aerodynamics Enrichment Stack. It captures the mandatory quality gates, plan→commit guardrails, and TechDocs metadata so projects stay compliant from the first commit.

## Contents

```
.
├── catalog-info.yaml      # Backstage System/Component skeleton
├── docs/                  # MkDocs/TechDocs starter content
├── scripts/bootstrap_env.sh
├── templates/
└── README.md              # Getting started checklist
```

## Quick Start

1. Copy this directory to your new repository root and rename as needed.
2. Run `scripts/bootstrap_env.sh --dry-run` to inspect the bootstrap plan, then run without `--dry-run` to provision Python 3.13, Poetry, Node tooling, and pre-commit hooks.
3. Commit the generated `.plan` and `.commit` artefacts alongside code changes:

   ```bash
   poetry run python -m apps.automation.cli qa plan --write-plan artifacts/setup.plan --write-commit artifacts/setup.commit
   poetry run python -m apps.automation.cli qa all --plan artifacts/setup.plan --commit artifacts/setup.commit
   ```

4. Update `catalog-info.yaml` with the owning team, domain, and component metadata; the TechDocs workflow automatically publishes the documentation when the template is used inside this repository.

5. Fill out `docs/index.md` with service-specific runbooks, evidence logging expectations, and guardrail references.

## Plan→Commit Guard

Every write operation (CLI, MCP, automation workflow) must capture plan and commit artefacts before modifying data or infrastructure. The template includes helper scripts that fail fast when artefacts are missing or stale.

- `artifacts/setup.plan` documents the intended changes.
- `artifacts/setup.commit` records the approved diff with `If-Match` headers and RAG metrics.
- `data/logs/plan_commit_audit.jsonl` receives append-only audit events.

## Quality Gates

- `poetry run python -m apps.automation.cli qa plan`
- `poetry run python -m apps.automation.cli qa all`
- Optional: `poetry run python -m apps.automation.cli qa mutation` once the codebase contains business logic.

## Documentation

MkDocs configuration (`docs/mkdocs.yml`) is compatible with Backstage TechDocs. Running `techdocs-cli generate --no-docker --source-dir . --output-dir site/techdocs` produces the static site published by the CI workflow.

## Next Steps

- Register the generated `catalog-info.yaml` in Backstage.
- Configure signed artefact promotion jobs if the service builds distributables.
- Add chaos/FMEA scenarios to the service runbook to align with SRE drills.
