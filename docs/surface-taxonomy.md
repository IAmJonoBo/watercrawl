---
title: Surface Taxonomy
description: Code organization, ownership boundaries, and CODEOWNERS mapping
---

# Surface Taxonomy

The enrichment stack is organised into clearly owned surfaces. Each directory
maps to the CODEOWNERS responsibilities captured in `.github/CODEOWNERS`.

| Surface | Description | CODEOWNERS |
| --- | --- | --- |
| `watercrawl/core/` | Canonical business logic, validation, and shared models. | `@ACES-Aerodynamics/platform-team` |
| `watercrawl/integrations/` | Contracts, lineage, lakehouse, telemetry, and research adapters. | `@ACES-Aerodynamics/data-engineering` |
| `watercrawl/governance/` | Safety, evaluation, and secrets providers. | `@ACES-Aerodynamics/security` |
| `watercrawl/interfaces/` | CLI, MCP, and UI entry points. | `@ACES-Aerodynamics/automation` |
| `apps/analyst/` | Analyst-facing CLI surface used in runbooks. | `@ACES-Aerodynamics/automation` |
| `apps/automation/` | Automation and CI helper CLI surfaces. | `@ACES-Aerodynamics/automation` |
| `platform/infrastructure/` | Hardened deployment guardrails and operational runbooks. | `@ACES-Aerodynamics/platform-team` |
| `platform/scripts/` | Operational automation guidance (Python modules live in `scripts/`). | `@ACES-Aerodynamics/platform-team` |
| `docs/`, `mkdocs.yml` | MkDocs reference and architecture guides. | `@ACES-Aerodynamics/docs-team` |
| `tests/` | Regression and contract test suites. | `@ACES-Aerodynamics/qa` |

## Guardrail Summary

- Application surfaces (`apps/`) ship only after POPIA-compliant provenance
  artefacts are attached and regression tests are green.
- Platform guardrails (`platform/`) document escalation paths and deployment
  expectations so operations teams can reproduce production state.
- All directories listed above inherit the baseline QA gates (pytest, lint,
  typing, security, build, dbt contracts) before merge.
