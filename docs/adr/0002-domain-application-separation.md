---
title: ADR 0002 - Promote Domain/Application Boundaries
description: Domain entity separation from orchestration code
---

# ADR 0002: Promote Domain/Application Boundaries

- **Status:** Accepted
- **Date:** 2025-10-18
- **Links:** Extends [ADR 0001](0001-architecture-boundaries.md)

## Context

ADR 0001 split the original `firecrawl_demo` monolith into core, integrations, governance, and interfaces. As the enrichment stack grew, the `firecrawl_demo.core` package accumulated both business entities (models, validation, compliance) and orchestration code (pipeline, progress listeners, quality gates, evidence sinks). This mingled the pure domain contract with persistence concerns, making it harder to reason about imports, add alternative front-ends, or ship infrastructure-specific evidence sinks.

## Decision

- Introduce a `firecrawl_demo.domain` package that owns canonical models, validation, and compliance helpers.
- Create a `firecrawl_demo.application` package that coordinates orchestration (pipeline, progress, quality) and publishes shared interfaces (`application.interfaces`) for pipelines and evidence sinks.
- Move evidence sink implementations into `firecrawl_demo.infrastructure.evidence`, keeping persistence behind the application interfaces.
- Update the CLI, MCP server, and tests to import the new packages and pass `EvidenceSink` implementations explicitly.
- Refresh the architecture documentation to describe the new layering.

## Consequences

- Imports now reflect intent (`firecrawl_demo.domain.models`, `firecrawl_demo.application.pipeline`, `firecrawl_demo.infrastructure.evidence`).
- Persistence adapters can evolve independently of the domain layer while remaining reachable through the application interfaces.
- Pipelines can be wrapped or replaced in other contexts (e.g., automation services) without pulling in infrastructure code.
- Consumers must update imports; backward-compatibility aliases were intentionally avoided to flush out stale references during the transition.
