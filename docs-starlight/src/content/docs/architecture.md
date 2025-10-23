---
title: Architecture Overview
description: System design, component relationships, and data flow
---

# Architecture Overview

Watercrawl follows a **hexagonal (ports and adapters) architecture** with clear separation of concerns, enabling testability, extensibility, and maintainability.

## High-Level System Architecture

```mermaid
%%{init: {'theme':'base', 'themeVariables': { 'primaryColor':'#f6f8fa','primaryTextColor':'#24292f','primaryBorderColor':'#d1d9e0','lineColor':'#656d76','secondaryColor':'#0969da','tertiaryColor':'#ffffff'}}}%%
graph TB
    subgraph "External Systems"
        CLI[CLI Users]
        UI[Analyst UI]
        Copilot[GitHub Copilot]
        Firecrawl[Firecrawl API]
        Regulators[Regulator APIs]
    end
    
    subgraph "Interfaces Layer"
        MCPS[MCP Server]
        CLIS[CLI Service]
        UIS[Streamlit UI]
    end
    
    subgraph "Application Layer"
        Pipeline[Pipeline Orchestrator]
        QualityGate[Quality Gate]
        EvidenceSink[Evidence Sink Interface]
    end
    
    subgraph "Domain Layer"
        Validation[Validators]
        Compliance[Compliance Rules]
        Models[Domain Models]
    end
    
    subgraph "Integrations Layer"
        Adapters[Research Adapters]
        Lineage[Lineage Tracking]
        Lakehouse[Lakehouse Writer]
        Contracts[Data Contracts]
    end
    
    subgraph "Infrastructure Layer"
        EvidenceImpl[Evidence Sinks]
        Planning[Infrastructure Planning]
        Secrets[Secrets Management]
    end
    
    CLI --> CLIS
    UI --> UIS
    Copilot --> MCPS
    CLIS --> Pipeline
    UIS --> Pipeline
    MCPS --> Pipeline
    Pipeline --> QualityGate
    Pipeline --> Validation
    QualityGate --> Compliance
    Pipeline --> EvidenceSink
    EvidenceSink --> EvidenceImpl
    Pipeline --> Adapters
    Adapters --> Firecrawl
    Adapters --> Regulators
    Pipeline --> Lineage
    Pipeline --> Lakehouse
    Pipeline --> Contracts
    
    style Pipeline fill:#0969da,stroke:#0969da,color:#fff
    style QualityGate fill:#d73a4a,stroke:#d73a4a,color:#fff
    style Models fill:#1f6feb,stroke:#1f6feb,color:#fff
```

## Layered Architecture

Watercrawl is organized into six distinct layers, each with specific responsibilities:

### 1. Interfaces Layer (`firecrawl_demo.interfaces`)

**Purpose**: External entry points for humans and AI agents

**Components**:
- **CLI** (`interfaces.cli`): Analyst-facing commands for validation, enrichment, and contracts
- **MCP Server** (`interfaces.mcp`): Model Context Protocol server for GitHub Copilot integration
- **Analyst UI** (`interfaces.ui`): Streamlit-based web interface (optional dependency)

**Key Principle**: Interfaces depend on the application layer but never directly on infrastructure

```mermaid
%%{init: {'theme':'base', 'themeVariables': { 'primaryColor':'#f6f8fa','primaryTextColor':'#24292f'}}}%%
graph LR
    A[User] --> B[CLI Command]
    B --> C[Pipeline.run]
    C --> D[Results]
    D --> A
    
    style B fill:#0969da,color:#fff
    style C fill:#1f6feb,color:#fff
```

### Crawlkit Modules (`crawlkit`)

Feature-flagged Crawlkit fetch, distill, extract, and Celery orchestrators replace the legacy Firecrawl demos. Enable `FEATURE_ENABLE_CRAWLKIT` to exercise the adapters locally; set `FEATURE_ENABLE_FIRECRAWL_SDK` only when you are ready to run the optional SDK. The compatibility shim exposes `/crawlkit/crawl`, `/crawlkit/markdown`, and `/crawlkit/entities` via FastAPI (`firecrawl_demo.interfaces.cli:create_app`) so automation clients can reuse the same surfaces.

### 2. Application Layer (`firecrawl_demo.application`)

**Purpose**: Orchestrate workflows and enforce business rules

**Components**:
- **Pipeline** (`application.pipeline`): Main enrichment orchestrator
- **Quality Gate** (`application.quality`): Validates changes before applying them
- **Interfaces** (`application.interfaces`): Abstract interfaces for evidence sinks, research adapters

**Key Principle**: Application layer coordinates domain logic without knowing about persistence details

```mermaid
%%{init: {'theme':'base', 'themeVariables': { 'primaryColor':'#f6f8fa','primaryTextColor':'#24292f'}}}%%
sequenceDiagram
    participant P as Pipeline
    participant V as Validator
    participant A as Research Adapter
    participant Q as Quality Gate
    participant E as Evidence Sink
    
    P->>V: Validate input
    V-->>P: ValidationReport
    P->>A: Lookup organisations
    A-->>P: ResearchFindings
    P->>Q: Evaluate findings
    Q-->>P: Approved changes
    P->>E: Log evidence
    E-->>P: Confirmation
```

### 3. Domain Layer (`firecrawl_demo.domain`)

**Purpose**: Core business logic and rules (framework-independent)

**Components**:
- **Models** (`domain.models`): Data classes for organisations, contacts, evidence
- **Validation** (`domain.validation`): Dataset validation rules
- **Compliance** (`domain.compliance`): POPIA, E.164, South African taxonomy rules

**Key Principle**: Pure business logic with no framework dependencies

```mermaid
%%{init: {'theme':'base', 'themeVariables': { 'primaryColor':'#f6f8fa','primaryTextColor':'#24292f'}}}%%
classDiagram
    class Organisation {
        +name: str
        +province: Province
        +website: URL
        +contacts: List~Contact~
        +validate()
    }
    
    class Contact {
        +name: str
        +phone: PhoneNumber
        +email: EmailAddress
        +validate_e164()
        +validate_mx_records()
    }
    
    class EvidenceRecord {
        +row_id: str
        +changes: Dict
        +sources: List~URL~
        +confidence: int
        +timestamp: datetime
    }
    
    Organisation "1" --> "*" Contact
    Organisation "1" --> "*" EvidenceRecord
```

### 4. Integrations Layer (`firecrawl_demo.integrations`)

**Purpose**: Connect to external systems and optional features

**Components**:
- **Research Adapters** (`integrations.adapters`): Firecrawl, press, regulator lookups
- **Lineage** (`integrations.lineage`): OpenLineage, PROV-O, DCAT tracking
- **Lakehouse** (`integrations.lakehouse`): Parquet snapshots, Delta Lake (optional)
- **Contracts** (`integrations.contracts`): Great Expectations + dbt integration
- **Plugin Registry** (`integrations.integration_plugins`): Centralized plugin discovery

**Key Principle**: All integrations are optional and feature-flagged

```mermaid
%%{init: {'theme':'base', 'themeVariables': { 'primaryColor':'#f6f8fa','primaryTextColor':'#24292f'}}}%%
graph TD
    A[Pipeline] --> B{Feature Flags}
    B -->|ENABLE_FIRECRAWL_SDK| C[Firecrawl Adapter]
    B -->|ENABLE_PRESS_RESEARCH| D[Press Adapter]
    B -->|ENABLE_REGULATOR_LOOKUP| E[Regulator Adapter]
    B -->|Offline Mode| F[Null Adapter]
    
    C --> G[Composite Adapter]
    D --> G
    E --> G
    F --> G
    
    G --> H[Research Findings]
    
    style B fill:#ffd33d
    style G fill:#0969da,color:#fff
```

### 5. Infrastructure Layer (`firecrawl_demo.infrastructure`)

**Purpose**: Implement persistence and deployment concerns

**Components**:
- **Evidence Sinks** (`infrastructure.evidence`): CSV, streaming, hybrid implementations
- **Planning** (`infrastructure.planning`): Infrastructure-as-code scaffolding
- **Secrets** (`infrastructure.secrets`): AWS, Azure, environment variable backends

**Key Principle**: Infrastructure adapts to application interfaces

### 6. Core Utilities (`firecrawl_demo.core`)

**Purpose**: Shared utilities and configuration

**Components**:
- **Configuration** (`core.config`): Environment variables, feature flags
- **Excel I/O** (`core.excel`): CSV/XLSX readers and writers
- **Constants** (`core.constants`): Shared enums and taxonomies

## Complete Data Flow

```mermaid
%%{init: {'theme':'base', 'themeVariables': { 'primaryColor':'#f6f8fa','primaryTextColor':'#24292f','primaryBorderColor':'#d1d9e0','lineColor':'#656d76','secondaryColor':'#0969da'}}}%%
flowchart TD
    A[Raw CSV/XLSX] --> B[Excel Reader]
    B --> C[DatasetValidator]
    C -->|Has Issues?| D{Validation Report}
    D -->|Yes| E[Return Errors]
    D -->|No| F[Pipeline Orchestrator]
    
    F --> G[Research Adapter Registry]
    G --> H{Enabled Adapters}
    H -->|Firecrawl| I[Firecrawl API]
    H -->|Press| J[Press Intelligence]
    H -->|Regulator| K[Regulator Lookup]
    H -->|Offline| L[Null Adapter]
    
    I --> M[Composite Findings]
    J --> M
    K --> M
    L --> M
    
    M --> N[Quality Gate]
    N --> O{Meets Criteria?}
    O -->|No| P[Reject with Remediation]
    O -->|Yes| Q[Apply Changes]
    
    Q --> R[Compliance Normalizers]
    R --> S[Evidence Sink]
    S --> T[CSV Evidence Log]
    S --> U[Streaming Sink]
    
    Q --> V[Lineage Tracker]
    V --> W[OpenLineage Events]
    V --> X[PROV-O Graphs]
    V --> Y[DCAT Metadata]
    
    Q --> Z[Lakehouse Writer]
    Z --> AA[Parquet Snapshots]
    Z --> AB[Delta Lake Tables]
    Z --> AC[Version Manifests]
    
    Q --> AD[Data Contracts]
    AD --> AE[Great Expectations]
    AD --> AF[dbt Tests]
    
    Q --> AG[Enriched DataFrame]
    AG --> AH[Export CSV/XLSX]
    
    style F fill:#0969da,color:#fff
    style N fill:#d73a4a,color:#fff
    style S fill:#1f6feb,color:#fff
    style E fill:#d73a4a,color:#fff
    style P fill:#ffd33d
    style AH fill:#2ea44f,color:#fff
```

## Extensibility Points

Watercrawl is designed for extension at multiple levels:

### 1. Research Adapters

Implement the `ResearchAdapter` protocol to add new data sources:

```python
from firecrawl_demo.integrations.adapters.research import (
    ResearchAdapter, 
    ResearchFinding
)

class CustomAdapter(ResearchAdapter):
    async def lookup(
        self, 
        organisation: str, 
        province: str
    ) -> ResearchFinding | None:
        # Your implementation
        return ResearchFinding(
            website="https://example.com",
            sources=["https://official.source", "https://secondary.source"],
            confidence=85
        )

# Register with the plugin system
from firecrawl_demo.integrations.adapters.research.registry import register_adapter
register_adapter("custom", lambda ctx: CustomAdapter())
```

### 2. Evidence Sinks

Implement `EvidenceSink` interface for custom logging:

```python
from firecrawl_demo.application.interfaces import EvidenceSink, EvidenceRecord

class KafkaEvidenceSink(EvidenceSink):
    async def log_evidence(self, record: EvidenceRecord) -> None:
        # Send to Kafka topic
        await self.producer.send("evidence", record.to_dict())
```

### 3. Validation Rules

Extend domain validators for custom compliance:

```python
from firecrawl_demo.domain.validation import DatasetValidator

class CustomValidator(DatasetValidator):
    def validate_custom_field(self, df: pd.DataFrame) -> List[ValidationIssue]:
        # Custom validation logic
        return issues
```

## Component Communication

### Synchronous Flow (CLI/Direct)

```mermaid
%%{init: {'theme':'base', 'themeVariables': { 'primaryColor':'#f6f8fa','primaryTextColor':'#24292f'}}}%%
sequenceDiagram
    participant CLI
    participant Pipeline
    participant Validator
    participant Adapter
    participant QualityGate
    participant EvidenceSink
    
    CLI->>Pipeline: run_enrichment(df)
    Pipeline->>Validator: validate(df)
    Validator-->>Pipeline: ValidationReport
    
    loop For each organisation
        Pipeline->>Adapter: lookup(org, province)
        Adapter-->>Pipeline: ResearchFinding
    end
    
    Pipeline->>QualityGate: evaluate_findings(findings)
    QualityGate-->>Pipeline: ApprovedChanges
    
    Pipeline->>EvidenceSink: log_evidence(records)
    EvidenceSink-->>Pipeline: Success
    
    Pipeline-->>CLI: PipelineReport
```

### Asynchronous Flow (MCP/AI-Assisted)

```mermaid
%%{init: {'theme':'base', 'themeVariables': { 'primaryColor':'#f6f8fa','primaryTextColor':'#24292f'}}}%%
sequenceDiagram
    participant Copilot as GitHub Copilot
    participant MCP as MCP Server
    participant Policy as Plan→Commit Guard
    participant Pipeline
    participant Audit as Audit Log
    
    Copilot->>MCP: enrich_dataset(plan, commit, if_match)
    MCP->>Policy: validate_plan_commit(artifacts)
    
    alt Plan/Commit Valid
        Policy-->>MCP: Approved
        MCP->>Pipeline: run_enrichment(df)
        Pipeline-->>MCP: PipelineReport
        MCP->>Audit: log_operation(metadata)
        MCP-->>Copilot: Success + Evidence
    else Missing Artifacts
        Policy-->>MCP: Rejected
        MCP-->>Copilot: Error + Remediation
    end
```

## Deployment Architecture

```mermaid
%%{init: {'theme':'base', 'themeVariables': { 'primaryColor':'#f6f8fa','primaryTextColor':'#24292f'}}}%%
graph TB
    subgraph "Development"
        Dev[Developer Workstation]
        DevCLI[Local CLI]
        DevTests[Test Suite]
    end
    
    subgraph "CI/CD Pipeline"
        GHA[GitHub Actions]
        QA[Quality Gates]
        SBOM[SBOM Generation]
        Signing[Sigstore Signing]
    end
    
    subgraph "Production"
        Analyst[Analyst Workstation]
        AnalystCLI[CLI Tools]
        AnalystUI[Streamlit UI]
        MCPServer[MCP Server]
    end
    
    subgraph "Data Storage"
        CSV[CSV Files]
        Lakehouse[Lakehouse/Delta]
        Evidence[Evidence Logs]
        Lineage[Lineage Bundles]
    end
    
    subgraph "External Services"
        Secrets[Secrets Manager]
        APIs[External APIs]
        Monitoring[Observability]
    end
    
    Dev --> GHA
    GHA --> QA
    QA --> SBOM
    SBOM --> Signing
    Signing --> Analyst
    
    AnalystCLI --> CSV
    AnalystCLI --> Lakehouse
    AnalystCLI --> Evidence
    AnalystCLI --> Lineage
    
    MCPServer --> AnalystCLI
    AnalystUI --> AnalystCLI
    
    AnalystCLI --> Secrets
    AnalystCLI --> APIs
    AnalystCLI --> Monitoring
    
    style QA fill:#d73a4a,color:#fff
    style SBOM fill:#0969da,color:#fff
    style Signing fill:#2ea44f,color:#fff
```

## Design Principles

1. **Separation of Concerns**: Each layer has a single, well-defined responsibility
2. **Dependency Inversion**: High-level modules don't depend on low-level modules
3. **Interface Segregation**: Clients depend only on interfaces they use
4. **Feature Flags**: Optional functionality is gated by environment variables
5. **Evidence-First**: All changes require ≥2 sources, including ≥1 official
6. **Compliance by Default**: POPIA, E.164, and SACAA rules are enforced automatically
7. **Testability**: Pure functions and dependency injection enable comprehensive testing
8. **Observability**: Lineage, metrics, and audit logs for all operations

## Technology Decisions

See [Architecture Decision Records (ADRs)](/adr/) for detailed rationales:

- [ADR 0001: Architecture Boundaries](/adr/0001-architecture-boundaries/) - Package structure
- [ADR 0002: Domain/Application Separation](/adr/0002-domain-application-separation/) - Layer boundaries
- [ADR 0003: Threat Model & STRIDE/MITRE](/adr/0003-threat-model-stride-mitre/) - Security design

## Next Steps

- **Developers**: Review [CLI Guide](/cli/) for available commands
- **Architects**: Study [Data Quality](/data-quality/) methodology
- **Security**: Examine [Operations](/operations/) for hardening procedures
- **Contributors**: Check [CONTRIBUTING.md](https://github.com/IAmJonoBo/watercrawl/blob/main/CONTRIBUTING.md)
    F --> E
    E --> G[domain.compliance Normalisers]
    E --> H[application.interfaces EvidenceSink]
    H --> I[infrastructure.evidence Implementations]
    E --> J[Enriched DataFrame]
    J --> K[Exports & Lakehouse]
```

## Extensibility

- Implement new `ResearchAdapter` factories for additional data sources.
- Provide alternative `EvidenceSink` implementations (Kafka, REST, etc.).
- Extend `Pipeline.run_task` with automation shortcuts.
- Capture decisions in ADRs as the architecture evolves.

### Research Adapter Registry

The registry (`firecrawl_demo.integrations.research.registry`) discovers adapters without editing the pipeline:

1. Implement the `ResearchAdapter` protocol.
2. Register the factory with `register_adapter()`.
3. Configure execution order via `RESEARCH_ADAPTERS` or an adapters file.
4. `load_enabled_adapters()` resolves factories with feature-flag checks and falls back to a Null adapter when every factory opts out.

### Infrastructure Plan Scaffold

`firecrawl_demo.infrastructure.planning` assembles crawler, observability, policy, and plan→commit expectations. Use `build_infrastructure_plan()` to produce a frozen snapshot for documentation, CI assertions, or MCP tooling.

### Lineage & Lakehouse Services

- `firecrawl_demo.integrations.lineage` records OpenLineage, PROV-O, and DCAT artefacts.
- `firecrawl_demo.integrations.lakehouse` snapshots curated tables to Parquet with manifest metadata, paving the way for Delta Lake/Iceberg or DVC/lakeFS integrations.
