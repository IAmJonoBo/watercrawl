# Platform Surfaces

The `platform/` tree captures operational guardrails for infrastructure and
supporting scripts. These folders document how runtime environments are
provisioned and how automation tooling is deployed across the stack.

## Guardrails

- Keep this area documentation-first—runtime code lives under
  `watercrawl/`, `apps/`, or dedicated infrastructure repositories.
- Record ownership and escalation paths for every artefact so operations teams
  can respond quickly.
- Any executable added here must include usage instructions, dependencies, and
  rollback guidance.

## Subdirectories

- `infrastructure/` – deployment guardrails, hardened distribution policies, and
  platform-specific runbooks.
- `scripts/` – operational automation descriptions, pointing to the maintained
  Python modules in `scripts/`.
