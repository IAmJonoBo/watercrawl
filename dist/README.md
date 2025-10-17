# Distribution (dist) Guidance

The `dist/` tree represents the hardened distribution footprint for crawlers and enrichment services. Only automation-ready,
policy-compliant assets belong here.

Operational rules:

- Codex integrations are **disabled** in this environment. Enforce manual review and Promptfoo guardrails before migrating any
  tooling from `dev/` or `tools/`.
- Mirror crawler runbooks, OpenLineage transports, and deployment manifests here so production rebuilds remain reproducible.
- Capture any dist-specific feature flags (crawler throttles, evidence sinks, or lakehouse endpoints) separately from
  development defaults to preserve auditability.
