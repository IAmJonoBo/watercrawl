---
title: Architecture Overview
description: System design, layered architecture, and component relationships
---

# Architecture Overview

## Layered Design

1. **Core Utilities** (`firecrawl_demo.core`)
   - Provides configuration, Excel I/O helpers, and shared constants used across the stack.
   - Normalises sheet naming, preserves canonical column order, and exposes deterministic file paths for artefact export.
2. **Domain Layer** (`firecrawl_demo.domain`)
   - Owns canonical models (`models`), validation rules (`validation`), and compliance heuristics (`compliance`).
   - Emits structured `ValidationReport`, `EvidenceRecord`, and `QualityIssue` objects that can be consumed without referencing persistence concerns.
3. **Application Layer** (`firecrawl_demo.application`)
   - Coordinates orchestration through the `pipeline`, `quality`, and `progress` modules.
   - Defines interfaces in `application.interfaces` so pipelines and evidence sinks can be swapped or decorated without touching domain logic.
4. **Integrations** (`firecrawl_demo.integrations`)
   - Adapter, telemetry, storage, and contract integrations register themselves with the shared plugin registry.
   - External systems plug into the application layer via protocols so deterministic offline adapters continue to drive the QA suite.
5. **Infrastructure** (`firecrawl_demo.infrastructure`)
   - Implements persistence for the application interfaces, including CSV/streaming evidence sinks and the infrastructure planning scaffold.
   - Keeps storage and deployment details decoupled from the pipeline so alternative sinks (e.g., Kafka, REST) can be introduced without disturbing core orchestration.
6. **Interfaces** (`firecrawl_demo.interfaces`)
   - CLI, analyst UI, and MCP surfaces build on the application layer to expose validated enrichment workflows to humans and GitHub Copilot.

> **Package boundaries.** `firecrawl_demo.domain` captures business invariants, `firecrawl_demo.application` orchestrates workflows against those invariants, `firecrawl_demo.infrastructure` persists artefacts, and `firecrawl_demo.integrations` houses optional systems (lineage, lakehouse, contracts, research). Production wheels still exclude workspace directories (`codex/`, `apps/`, `platform/`, `tools/`) so deployments remain lean.

## Data Contracts

The `firecrawl_demo.domain.contracts` module provides **versioned Pydantic contracts** for all domain models, enabling:

- **JSON Schema export** for contract testing and API documentation
- **Runtime validation** with detailed error messages
- **Semantic versioning** (currently v1.0.0) to track breaking changes
- **Schema URIs** for registry integration and backward compatibility tracking

### Contract Models

All core domain dataclasses have corresponding Pydantic contract equivalents:

- `SchoolRecordContract` - Organisation enrichment records with field validation
- `EvidenceRecordContract` - Audit log entries with confidence scoring
- `QualityIssueContract` - Quality gate findings with severity levels
- `ValidationIssueContract` - Schema validation errors
- `ValidationReportContract` - Aggregated validation results
- `SanityCheckFindingContract` - Data consistency checks
- `PipelineReportContract` - Complete pipeline execution reports

### Adapter Functions

Bidirectional adapters in `firecrawl_demo.domain.models` convert between legacy dataclasses and contract models:

```python
# Convert legacy to contract
contract = school_record_to_contract(legacy_record)

# Convert contract to legacy
legacy = school_record_from_contract(contract)
```

This ensures **backward compatibility** during migration while new code can use contracts for validation.

### Schema Export

```python
from firecrawl_demo.domain.contracts import export_all_schemas

# Export all schemas for documentation/testing
schemas = export_all_schemas()
# Returns: {"SchoolRecord": {...}, "EvidenceRecord": {...}, ...}
```

### Contract Registry

All contracts include metadata for schema registry integration:

- **Version**: Semantic version (e.g., "1.0.0")
- **Schema URI**: Canonical identifier (e.g., "https://watercrawl.acesaero.co.za/schemas/v1/school-record")

Future integration points:
- MCP responses will embed contract versions and schema URIs
- Evidence sinks will validate entries against contracts before persistence
- Plan→commit artefacts will reference contract versions for compatibility checking

## Data Flow

```mermaid
flowchart LR
    A[Raw CSV/XLSX] --> B[core.excel.Dataset Reader]
    B --> C[domain.validation.DatasetValidator]
    C -->|Issues| D[Validation Report]
    C -->|Curated frame| E[application.pipeline.Pipeline]
    E --> F[Research Adapters]
    F --> E
    E --> G[domain.compliance Normalisers]
    E --> H[application.interfaces.EvidenceSink]
    H --> I[infrastructure.evidence Implementations]
    E --> J[Enriched DataFrame]
    J --> K[Exports & Lakehouse]
```

## Extensibility Points

- Implement a new `ResearchAdapter` to integrate additional data sources (SACAA APIs, commercial datasets, etc.).
- Provide an alternate `EvidenceSink` implementation in `firecrawl_demo.infrastructure.evidence` to stream audit events to Kafka, REST endpoints, or other telemetry systems.
- Override `Pipeline.run_task` to expose additional automation actions (province-only audits, contract summaries, etc.).
- Extend MkDocs with new ADRs to document architectural decisions as the stack evolves.

### Research Adapter Registry

The `firecrawl_demo.integrations.adapters.research.registry` module centralises adapter discovery so new intelligence sources can be added without editing the pipeline.

1. Author an adapter that implements the `ResearchAdapter` protocol (expose a `lookup(organisation, province)` method returning a `ResearchFinding`).
2. Register it during import with `register_adapter("my-adapter", my_factory)`. Factories receive an `AdapterContext` and should return a new adapter instance (or `None` when disabled).
3. Declare the execution order with configuration:
   - `RESEARCH_ADAPTERS="firecrawl,my-adapter,null"` for quick overrides.
   - Point `RESEARCH_ADAPTERS_FILE` to a YAML/TOML file containing an `adapters` list for more complex stacks.
4. When `load_enabled_adapters()` runs, the registry handles deduplication and feature-flag checks; the plugin registry defaults to the composite adapter while ensuring a Null adapter is used if every factory opts out.

### Integration Plugin Registry

`firecrawl_demo.integrations.integration_plugins` provides a shared registry that groups plugins by category (`adapters`, `telemetry`, `storage`, `contracts`) and exposes discovery helpers used by the pipeline and CLIs. Built-in plugins register themselves on import and describe their required feature flags, environment variables, optional dependencies, and health probes. Third-party packages can contribute additional plugins via Python entry points or by calling `register_plugin()` during import.

- **Adapters**: Composite research adapter stack that honours feature flags for Firecrawl and offline triangulation.
- **Telemetry**: Drift, graph semantics, and lineage surfaces, each with a health probe that verifies optional transports (HTTP/Kafka) or baseline prerequisites.
- **Storage**: Lakehouse and versioning writers that expose their root directories and feature toggles through the config schema.
- **Contracts**: A `ContractsToolkit` exposing Great Expectations + dbt execution helpers, wiring contract artefact persistence and evidence capture behind optional dependencies.

- `instantiate_plugin(category, name)` replaces ad-hoc import factories inside the pipeline, ensuring research adapters, lineage managers, lakehouse writers, and versioning managers are all resolved consistently.
- Plugin health probes capture QA readiness for optional transports (e.g., Kafka lineage exporters) so CI can surface missing dependencies before runtime.
- Registrations are intentionally idempotent and test fixtures can snapshot/reset the registry through `reset_registry()` when isolation is required.

This registry keeps `build_research_adapter()` thin while allowing optional modules (press intelligence, regulator lookups, ML enrichers) to live in their own packages.

### Infrastructure Plan Scaffold

The `firecrawl_demo.infrastructure.planning` module provides an `InfrastructurePlan` dataclass that aggregates crawler, observability, policy, and plan→commit expectations into a single contract.

- **CrawlerPlan** captures the frontier backend, scheduling policy, politeness delays, depth limits, trap-rule file, and user agent.
- **ObservabilityPlan** defines probe paths, SLO thresholds, and alert routes.
- **PolicyPlan** records the OPA bundle path, decision namespace, and enforcement mode.
- **PlanCommitContract** encodes the plan→commit guardrails for automation, including required plan/commit artefacts, `If-Match`/RAG thresholds, append-only audit log paths, and optional force-commit escape hatches.

Call `build_infrastructure_plan()` to obtain a frozen snapshot suitable for documentation exports, MCP tool manifests, or CI assertions before agents are allowed to crawl.

### Lineage & Lakehouse Services

- `firecrawl_demo.integrations.lineage` captures OpenLineage, PROV-O, and DCAT artefacts so provenance bundles accompany enriched datasets.
- `firecrawl_demo.integrations.lakehouse` snapshots curated tables to Parquet with manifest metadata, forming the foundation for future Delta Lake/Iceberg and DVC/lakeFS integrations.
