# Infrastructure Guardrails

This folder documents the hardened distribution footprint for crawlers and
enrichment services. Only automation-ready, policy-compliant assets should be
promoted into production environments.

Operational rules:

- Codex integrations stay **disabled** in runtime images. Enforce manual review
  and Promptfoo guardrails before migrating tooling from automation sandboxes.
- Mirror crawler runbooks, OpenLineage transports, and deployment manifests so
  production rebuilds remain reproducible.
- Capture dist-specific feature flags (crawler throttles, evidence sinks,
  lakehouse endpoints) separately from development defaults to preserve
  auditability.
