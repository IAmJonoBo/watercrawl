---
title: MCP Setup for GitHub Copilot
description: Configure the Model Context Protocol server for AI-assisted workflows
---

# Setting Up MCP for GitHub Copilot

The Model Context Protocol (MCP) server enables GitHub Copilot to interact with Watercrawl's enrichment pipeline, validation tools, and evidence logging.

## What is MCP?

MCP (Model Context Protocol) is a standardized interface for AI assistants to interact with external tools and systems. Watercrawl's MCP server exposes enrichment workflows as JSON-RPC methods that GitHub Copilot can call.

```mermaid
%%{init: {'theme':'base', 'themeVariables': { 'primaryColor':'#f6f8fa','primaryTextColor':'#24292f'}}}%%
sequenceDiagram
    participant Copilot as GitHub Copilot
    participant MCP as MCP Server
    participant Pipeline as Enrichment Pipeline
    participant Evidence as Evidence Log
    
    Copilot->>MCP: enrich_dataset(csv_path, plan)
    MCP->>Pipeline: run_enrichment()
    Pipeline-->>MCP: PipelineReport
    MCP->>Evidence: log_evidence()
    MCP-->>Copilot: Success + Results
```

## Prerequisites

- ✅ Watercrawl installed and configured
- ✅ GitHub Copilot extension installed in VS Code
- ✅ Poetry environment activated

## Installation

### Step 1: Start the MCP Server

```bash
poetry run python -m app.cli mcp-server
```

The server starts on `http://localhost:3000` by default.

### Step 2: Configure GitHub Copilot

Add MCP server to VS Code settings:

```json
// .vscode/settings.json
{
  "github.copilot.mcp.servers": [
    {
      "name": "watercrawl",
      "url": "http://localhost:3000",
      "description": "Watercrawl data enrichment toolkit"
    }
  ]
}
```

### Step 3: Verify Connection

Test the connection from VS Code terminal:

```bash
curl http://localhost:3000/health
# Expected: {"status": "healthy", "version": "1.0.0"}
```

## Available MCP Methods

### 1. enrich_dataset

Enrich a dataset with research findings.

**Request:**

```json
{
  "jsonrpc": "2.0",
  "method": "enrich_dataset",
  "params": {
    "input_path": "data/sample.csv",
    "output_path": "data/enriched.csv",
    "evidence_log_path": "data/evidence_log.csv",
    "plan_artifacts": ["tmp/plans/enrich.plan"],
    "commit_artifacts": ["tmp/plans/enrich.commit"],
    "if_match": "sha256:abc123..."
  },
  "id": 1
}
```

**Response:**

```json
{
  "jsonrpc": "2.0",
  "result": {
    "total_rows": 50,
    "rows_updated": 35,
    "rows_rejected": 5,
    "evidence_records": 87,
    "execution_time_seconds": 12.5
  },
  "id": 1
}
```

### 2. validate_dataset

Validate dataset without enrichment.

**Request:**

```json
{
  "jsonrpc": "2.0",
  "method": "validate_dataset",
  "params": {
    "input_path": "data/sample.csv"
  },
  "id": 2
}
```

### 3. list_profiles

List available refinement profiles.

**Request:**

```json
{
  "jsonrpc": "2.0",
  "method": "list_profiles",
  "params": {},
  "id": 3
}
```

### 4. get_sanity_issues

Retrieve data quality issues.

**Request:**

```json
{
  "jsonrpc": "2.0",
  "method": "get_sanity_issues",
  "params": {
    "input_path": "data/enriched.csv"
  },
  "id": 4
}
```

## Plan→Commit Workflow

The MCP server enforces a **plan→commit workflow** for destructive operations:

```mermaid
%%{init: {'theme':'base', 'themeVariables': { 'primaryColor':'#f6f8fa','primaryTextColor':'#24292f'}}}%%
flowchart TD
    A[GitHub Copilot] -->|Requests enrichment| B{Plan Artifacts?}
    B -->|Missing| C[Rejected]
    B -->|Present| D[Validate Plan]
    D -->|Invalid| C
    D -->|Valid| E{Commit Artifacts?}
    E -->|Missing| C
    E -->|Present| F[Validate Commit]
    F -->|Invalid| C
    F -->|Valid| G[Execute]
    G --> H[Log Audit]
    H --> I[Return Results]
    
    style C fill:#d73a4a,color:#fff
    style G fill:#2ea44f,color:#fff
```

### Creating Plan Artifacts

Generate a plan before enrichment:

```bash
poetry run python -m apps.automation.cli qa plan \
  --write-plan tmp/plans/enrich.plan
```

**Plan artifact example:**

```json
{
  "operation": "enrich_dataset",
  "input": "data/sample.csv",
  "output": "data/enriched.csv",
  "intended_changes": [
    {
      "row_id": "001",
      "field": "Website URL",
      "old_value": null,
      "new_value": "https://example.aero",
      "sources": ["https://official.gov", "https://secondary.com"],
      "confidence": 90
    }
  ],
  "timestamp": "2025-10-21T15:30:00Z"
}
```

### Creating Commit Artifacts

After reviewing the plan, create a commit artifact:

```bash
poetry run python -m apps.automation.cli qa commit \
  --plan tmp/plans/enrich.plan \
  --write-commit tmp/plans/enrich.commit
```

**Commit artifact example:**

```json
{
  "plan_sha256": "abc123...",
  "if_match": "sha256:abc123...",
  "approved_changes": [...],
  "reviewer": "analyst@example.com",
  "timestamp": "2025-10-21T15:35:00Z",
  "rag_metrics": {
    "faithfulness": 0.92,
    "context_precision": 0.88,
    "answer_relevancy": 0.95
  }
}
```

## Using MCP with Copilot

### Example 1: Enrich Dataset

In GitHub Copilot Chat:

```
@workspace Enrich the data/sample.csv dataset using the watercrawl MCP server.
Include evidence logging and use the default profile.
```

Copilot will:
1. Generate plan artifacts
2. Call `enrich_dataset` method
3. Parse results and summarize

### Example 2: Validate Before Enrichment

```
@workspace Validate data/input.csv using watercrawl before enriching it.
Show me any province or phone format issues.
```

### Example 3: Review Evidence

```
@workspace Using watercrawl MCP, show me evidence entries with confidence < 80.
```

## Security & Safety

### Plan→Commit Guardrails

The MCP server enforces safety checks:

- **Plan Artifacts Required**: All destructive operations need plans
- **Commit Artifacts Required**: Plans must be reviewed and committed
- **RAG Safety Checks**: Faithfulness, precision, and relevancy thresholds
- **Prompt Injection Detection**: Blocks suspicious patterns
- **Audit Logging**: All operations logged to `data/logs/plan_commit_audit.jsonl`

### Configuration

Tune safety thresholds:

```bash
# .env
PLAN_COMMIT_REQUIRED=1  # Enforce plan→commit workflow
PLAN_COMMIT_RAG_FAITHFULNESS=0.7  # Minimum RAG faithfulness
PLAN_COMMIT_RAG_CONTEXT_PRECISION=0.7
PLAN_COMMIT_RAG_ANSWER_RELEVANCY=0.7
PLAN_COMMIT_ALLOW_FORCE=0  # Disable force bypass
```

### Audit Logs

Review MCP operations:

```bash
cat data/logs/plan_commit_audit.jsonl | jq '.'
```

**Audit entry example:**

```json
{
  "timestamp": "2025-10-21T15:35:00Z",
  "method": "enrich_dataset",
  "user": "copilot",
  "plan_sha256": "abc123...",
  "if_match": "sha256:abc123...",
  "rag_metrics": {
    "faithfulness": 0.92,
    "context_precision": 0.88,
    "answer_relevancy": 0.95
  },
  "status": "success",
  "rows_affected": 35
}
```

## Testing MCP Integration

### Manual Testing

Test MCP methods directly:

```bash
# Test health endpoint
curl http://localhost:3000/health

# Test enrich_dataset
curl -X POST http://localhost:3000 \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "validate_dataset",
    "params": {"input_path": "data/sample.csv"},
    "id": 1
  }'
```

### Integration Testing

Run Promptfoo test suite:

```bash
cd codex/evals
promptfoo eval promptfooconfig.yaml
```

## Troubleshooting

### Server Won't Start

```bash
# Check port availability
lsof -i :3000

# Try different port
PORT=3001 poetry run python -m app.cli mcp-server
```

### Copilot Can't Connect

```bash
# Verify server is running
curl http://localhost:3000/health

# Check VS Code settings
cat .vscode/settings.json | jq '.["github.copilot.mcp"]'

# Restart VS Code
```

### Plan→Commit Errors

```bash
# Generate fresh plan
poetry run python -m apps.automation.cli qa plan \
  --write-plan tmp/plans/new_enrich.plan

# Review plan
cat tmp/plans/new_enrich.plan | jq '.'

# Create commit
poetry run python -m apps.automation.cli qa commit \
  --plan tmp/plans/new_enrich.plan \
  --write-commit tmp/plans/new_enrich.commit
```

## Advanced Configuration

### Custom MCP Methods

Extend the MCP server with custom methods:

```python
# firecrawl_demo/interfaces/mcp/custom_methods.py
from firecrawl_demo.interfaces.mcp.server import register_method

@register_method("my_custom_method")
async def my_custom_method(params: dict) -> dict:
    # Implementation
    return {"result": "success"}
```

### Authentication

Add API key authentication:

```bash
# .env
MCP_API_KEY=your_secret_key_here
MCP_REQUIRE_AUTH=1
```

```json
// Request with authentication
{
  "jsonrpc": "2.0",
  "method": "enrich_dataset",
  "params": {...},
  "headers": {
    "Authorization": "Bearer your_secret_key_here"
  },
  "id": 1
}
```

## Best Practices

1. **Always Use Plans**: Never bypass plan→commit workflow in production
2. **Review Plans**: Manually inspect plan artifacts before committing
3. **Monitor Audit Logs**: Set up alerts on `plan_commit_audit.jsonl`
4. **Test Locally First**: Run MCP methods locally before exposing to Copilot
5. **Keep Server Updated**: Pull latest MCP server updates regularly

## Next Steps

- **[Operations Guide](/operations/)** - Production deployment
- **[API Reference](/reference/api/)** - All MCP methods
- **[Troubleshooting](/guides/troubleshooting/)** - Common MCP issues

---

**Questions?** Check [MCP Integration](/mcp/) for more details or [create an issue](https://github.com/IAmJonoBo/watercrawl/issues).
