# Analyst Application Surface

`apps/analyst/` contains the human-facing entry points that wrap the enrichment
stack. Everything here must already satisfy lineage, lakehouse, and versioning
gates so analysts receive production-grade outputs.

Guardrails:

- Depend on shared primitives from `watercrawl/` rather than duplicating
  logic or policy decisions.
- Surface reproducible dataset details (manifests, lineage bundles, evidence
  logs) in any response emitted by this surface.
- Keep environment overrides in configuration, not code—automation relies on the
  same modules.
- Changes require regression coverage in `tests/test_app_cli.py` or associated UI
  tests before merging.
