---
title: Promote Domain/Application Boundaries
status: accepted
date: 2025-10-18
---

Extends [ADR 0001](0001-architecture-boundaries.md).

## Context

`watercrawl.core` had evolved into a grab bag of domain entities and orchestration utilities. Business invariants (models, validation, compliance) were tightly coupled to persistence concerns (pipeline services, evidence sinks), making it difficult to substitute infrastructure or expose alternative front-ends.

## Decision

- Move models, validation, and compliance helpers into `watercrawl.domain`.
- Introduce `watercrawl.application` for orchestration (`pipeline`, `quality`, `progress`) and shared interfaces (`application.interfaces`).
- Relocate evidence sink implementations to `watercrawl.infrastructure.evidence`, keeping persistence behind the application interface.
- Update CLIs, MCP server, and tests to depend on the new packages and explicit evidence sink wiring.
- Refresh the architecture documentation to describe the new layering.

## Consequences

- Imports now reflect intent (`watercrawl.domain.models`, `watercrawl.application.pipeline`, `watercrawl.infrastructure.evidence`).
- Persistence adapters can evolve independently while staying reachable through `application.interfaces.EvidenceSink`.
- Pipelines can be reused in other contexts without dragging along infrastructure concerns.
- Consumers must update imports; the migration intentionally avoids compatibility shims to surface stale usage.
