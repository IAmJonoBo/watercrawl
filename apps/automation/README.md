# Automation Surface

`apps/automation/` houses scheduled and CI-oriented entry points (for example the
QA helper CLI). Use this space for tooling that enforces the same quality gates as
production pipelines.

Guardrails:

- Treat this directory as promotion staging—anything promoted into runtime
  images must graduate through these automation flows first.
- Codex/agent usage requires Promptfoo smoke tests to pass
  (`promptfoo eval codex/evals/promptfooconfig.yaml`).
- Document Crawlkit feature flags (`FEATURE_ENABLE_CRAWLKIT`, `FEATURE_ENABLE_FIRECRAWL_SDK`) and ensure QA evidence references the `/crawlkit/markdown` and `/crawlkit/entities` endpoints exposed by `firecrawl_demo.interfaces.cli:create_app`.
- Capture assumptions, toggles, and pending migrations so the Platform team can
  trace changes during hand-offs.
- Keep notebooks and experiments in dedicated sandboxes; only checked-in code
  with regression coverage belongs here.
