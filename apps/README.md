# Application Surfaces

The `apps/` namespace contains automation-ready entry points that sit on top of the
`firecrawl_demo` packages. Each surface enforces evidence-backed workflows and is
guarded by the same POPIA-compliant controls as the core library.

## Guardrails

- Do not introduce business logic here—pull validated behaviour from
  `firecrawl_demo` modules instead.
- Keep every entry point deterministic and covered by regression tests so CI can
  gate releases without manual review.
- Prefer feature flags and configuration files over hard-coded policy switches to
  preserve reproducibility across analyst laptops and automation runners.
- Capture provenance (lineage, manifests, audit trails) for anything exported by
  these surfaces.

## Subdirectories

- `analyst/` – human-facing CLI and UI hooks used by the analyst playbooks.
- `automation/` – scheduled or CI-triggered command surfaces that mirror the
  production guardrails.
