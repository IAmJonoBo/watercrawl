# Architecture Overview

## Layered Design

1. **Dataset Ingestion** (`firecrawl_demo.excel`)
   - Handles CSV/XLSX parity with a unified reader/writer.
   - Normalises sheet naming and preserves canonical column order.
2. **Validation Layer** (`firecrawl_demo.validation`)
   - Enforces South African provincial lists and ACES status taxonomy.
   - Emits structured `ValidationIssue` instances for UI/automation consumption.
3. **Research Adapter Layer** (`firecrawl_demo.research`)
   - Provides a protocol-driven interface so tests can inject deterministic findings while production can swap in Firecrawl or OSINT clients.
   - `TriangulatingResearchAdapter` merges Firecrawl, regulator, press, and directory intelligence governed by feature toggles.
4. **Compliance Utilities** (`firecrawl_demo.compliance`)
   - Normalises phone numbers to +27 E.164, verifies email domains against official websites, and calculates confidence scores.
5. **Pipeline Orchestrator** (`firecrawl_demo.pipeline`)
   - Applies validation, enrichment, evidence logging, and metrics collection.
   - Generates `PipelineReport` objects for CLI/MCP consumers.
6. **Interfaces**
   - **CLI** (`firecrawl_demo.cli`): human-friendly commands for validation and enrichment.
   - **MCP Server** (`firecrawl_demo.mcp.server`): JSON-RPC surface for GitHub Copilot automation.

## Data Flow

```mermaid
flowchart LR
    A[Raw CSV/XLSX] --> B[DatasetValidator]
    B -->|Issues| C[Validation Report]
    B -->|Clean frame| D[Pipeline]
    D --> E[Research Adapter]
    E --> D
    D --> F[Compliance Normalisers]
    D --> G[Enriched DataFrame]
    D --> H[Evidence Log]
    G --> I[Export]
```

## Extensibility Points

- Implement a new `ResearchAdapter` to integrate different data sources (e.g., SACAA APIs, LinkedIn scraping, commercial datasets).
- Override `Pipeline.run_task` to expose additional automation tasks (e.g., province-only audits).
- Extend MkDocs with ADRs to capture decision history as the stack evolves.
