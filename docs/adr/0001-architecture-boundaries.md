---
title: ADR 0001 - Segmented Package Boundaries
description: Package organization and sdist bundling strategy
---

# ADR 0001: Segmented Package Boundaries

- **Status:** Accepted
- **Date:** 2025-10-17
- **Decision Makers:** Platform Architecture Guild
- **Context:**
  - The monolithic `firecrawl_demo` package blended crawler orchestration, external integrations, governance controls, and Copilot orchestration in a single namespace.
  - Production wheels unintentionally bundled workspace tooling (`codex/`, `apps/`, `platform/`, `tools/`) because Poetry defaulted to including the full repository in sdists.
  - Copilot/MCP orchestration imports risked leaking into crawler runtime contexts, complicating dependency reasoning.
- **Decision:**
  - Introduce four first-class packages: `firecrawl_demo.core`, `firecrawl_demo.integrations`, `firecrawl_demo.governance`, and `firecrawl_demo.interfaces`.
  - Rehome pipeline, validation, compliance, and shared models under `core`.
  - Move adapters, lineage, lakehouse, drift, and Firecrawl client bindings into `integrations`.
  - Isolate safety, evaluation, and secrets providers under `governance`.
  - Restrict CLI, analyst UI, and MCP entrypoints to `interfaces`.
  - Configure Poetry exclusions so only `firecrawl_demo` is packaged, leaving dev artefacts outside production distributions.
- **Consequences:**
  - Imports clearly communicate context: crawler code consumes `core`, optional systems live in `integrations`, and human/agent entrypoints call into `interfaces`.
  - Tests and docs now refer to the new modules, keeping Copilot logic behind the MCP boundary.
  - Future adapters can live in `integrations` without touching the pipeline core, simplifying dependency analysis and reviews.
  - Existing automation scripts must update module paths (e.g., `python -m firecrawl_demo.interfaces.cli`).
