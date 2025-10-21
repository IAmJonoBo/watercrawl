# Service Documentation

Welcome to your new service documentation. Replace this page with runbooks, quality gates, and evidence logging expectations.

## Getting Started

- Update `catalog-info.yaml` with the owning team and domain.
- Register the component in Backstage.
- Run `techdocs-cli generate --no-docker --source-dir . --output-dir site/techdocs` to verify output locally.

## Quality Gates

| Gate | Command |
|------|---------|
| QA plan | `poetry run python -m apps.automation.cli qa plan` |
| QA all | `poetry run python -m apps.automation.cli qa all` |
| Mutation pilot | `poetry run python -m apps.automation.cli qa mutation --dry-run` |

## Evidence Logging

Document how this service records plan→commit artefacts (`*.plan`/`*.commit`) and where audit logs are stored.

## Incident Response

Outline runbook steps and include a link to the chaos/FMEA register for this service.
