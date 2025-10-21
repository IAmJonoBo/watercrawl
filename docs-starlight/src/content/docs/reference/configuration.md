---
title: Configuration Reference
description: Complete reference for environment variables and feature flags
---

# Configuration Reference

Watercrawl is configured through environment variables and feature flags. This page documents all available configuration options.

## Environment Setup

Configuration can be provided via:

1. **`.env` file** in the project root (recommended for development)
2. **Shell environment variables** (recommended for production)
3. **Secrets managers** (AWS Secrets Manager, Azure Key Vault)

## Core Configuration

### Secrets Backend

```bash
SECRETS_BACKEND=env  # Options: env, aws, azure
```

Controls where sensitive configuration is loaded from:

- `env`: Load from environment variables or `.env` file (default)
- `aws`: Load from AWS Secrets Manager
- `azure`: Load from Azure Key Vault

**AWS Secrets Manager Configuration:**

```bash
AWS_REGION=us-east-1
AWS_DEFAULT_REGION=us-east-1
AWS_SECRETS_PREFIX=prod/watercrawl/  # Optional prefix for all secrets
```

**Azure Key Vault Configuration:**

```bash
AZURE_KEY_VAULT_URL=https://your-vault.vault.azure.net/
AZURE_SECRETS_PREFIX=watercrawl-  # Optional prefix
```

## Feature Flags

### Research & Enrichment

```bash
# Enable Firecrawl SDK for live web scraping
FEATURE_ENABLE_FIRECRAWL_SDK=0  # 0=disabled (default), 1=enabled

# Allow network-based research lookups
ALLOW_NETWORK_RESEARCH=0  # 0=offline only (default), 1=allow network

# Enable press intelligence research
FEATURE_ENABLE_PRESS_RESEARCH=1  # 0=disabled, 1=enabled (default)

# Enable regulator lookup (SACAA, etc.)
FEATURE_ENABLE_REGULATOR_LOOKUP=1  # 0=disabled, 1=enabled (default)

# Enable rebrand/ownership change detection
FEATURE_INVESTIGATE_REBRANDS=1  # 0=disabled, 1=enabled (default)

# Enable caching for research results
FEATURE_ENABLE_CACHE=0  # 0=disabled (default), 1=enabled
```

:::caution[Offline Mode]
By default, Watercrawl operates in **offline mode** (`ALLOW_NETWORK_RESEARCH=0`, `FEATURE_ENABLE_FIRECRAWL_SDK=0`) for reproducible, deterministic results. Enable network research only when you need live data.
:::

### API Keys

```bash
# Firecrawl API key (required if FEATURE_ENABLE_FIRECRAWL_SDK=1)
FIRECRAWL_API_KEY=your_api_key_here

# Custom API endpoints (optional)
FIRECRAWL_API_URL=https://api.firecrawl.dev  # Custom endpoint
```

## Profile Configuration

```bash
# Profile identifier (loads from profiles/ directory)
REFINEMENT_PROFILE=za_flight_schools  # Default profile

# Direct profile path (overrides REFINEMENT_PROFILE)
REFINEMENT_PROFILE_PATH=/path/to/custom_profile.yaml
```

**Profile Structure:**

Profiles define geography-specific rules, taxonomies, and compliance requirements. See `profiles/za_flight_schools.yaml` for an example.

## Data Quality & Contracts

```bash
# Minimum evidence confidence threshold (0-100)
EVIDENCE_MIN_CONFIDENCE=70  # Default: 70

# Minimum required sources per evidence record
EVIDENCE_MIN_SOURCES=2  # Default: 2

# Require at least one official/regulatory source
EVIDENCE_REQUIRE_OFFICIAL=1  # 0=disabled, 1=enabled (default)

# Fresh evidence requirement for high-risk changes
EVIDENCE_REQUIRE_FRESH=1  # 0=disabled, 1=enabled (default)

# Data contracts coverage threshold (%)
CONTRACTS_MIN_COVERAGE=95  # Default: 95%

# Canonical taxonomy JSON for contracts
CONTRACTS_CANONICAL_JSON=/path/to/canonical.json  # Auto-generated if not set
```

## Evidence Logging

```bash
# Evidence sink backend
EVIDENCE_SINK_BACKEND=csv  # Options: csv, stream, csv+stream

# CSV evidence log path
EVIDENCE_LOG_PATH=data/interim/evidence_log.csv

# Streaming configuration (if using stream or csv+stream)
EVIDENCE_STREAM_ENABLED=0  # 0=disabled, 1=enabled
EVIDENCE_STREAM_TRANSPORT=rest  # Options: rest, kafka
EVIDENCE_STREAM_REST_ENDPOINT=https://api.example.com/evidence
EVIDENCE_STREAM_KAFKA_TOPIC=watercrawl.evidence
EVIDENCE_STREAM_KAFKA_BOOTSTRAP=localhost:9092
```

## Lineage & Provenance

```bash
# OpenLineage configuration
OPENLINEAGE_TRANSPORT=file  # Options: file, http, kafka, logging
OPENLINEAGE_NAMESPACE=watercrawl  # Namespace for lineage events
OPENLINEAGE_URL=https://lineage.example.com/api/v1/lineage  # For HTTP transport
OPENLINEAGE_API_KEY=your_api_key  # Optional bearer token
OPENLINEAGE_KAFKA_TOPIC=openlineage.events
OPENLINEAGE_KAFKA_BOOTSTRAP=localhost:9092

# Lineage output directory (for file transport)
LINEAGE_OUTPUT_DIR=artifacts/lineage

# Enable PROV-O graph generation
LINEAGE_ENABLE_PROVO=1  # 0=disabled, 1=enabled (default)

# Enable DCAT metadata generation
LINEAGE_ENABLE_DCAT=1  # 0=disabled, 1=enabled (default)
```

## Lakehouse & Versioning

```bash
# Lakehouse root directory
LAKEHOUSE_ROOT=data/lakehouse

# Versioning metadata directory
VERSIONING_ROOT=data/versioning

# Enable Delta Lake (requires optional lakehouse dependency group)
LAKEHOUSE_ENABLE_DELTA=1  # 0=disabled, 1=enabled (default if available)

# Parquet compression
LAKEHOUSE_PARQUET_COMPRESSION=snappy  # Options: snappy, gzip, lz4, zstd
```

## Drift Detection

```bash
# Enable drift detection
DRIFT_ENABLED=1  # 0=disabled, 1=enabled (default)

# Drift threshold (0.0-1.0)
DRIFT_THRESHOLD=0.15  # Default: 15% change triggers alert

# Baseline paths
DRIFT_BASELINE_PATH=data/observability/whylogs/drift_baseline.json
DRIFT_WHYLOGS_BASELINE=data/observability/whylogs/whylogs_metadata.json

# Require baselines (fail if missing)
DRIFT_REQUIRE_BASELINE=0  # 0=optional (default), 1=required
DRIFT_REQUIRE_WHYLOGS_METADATA=0  # 0=optional (default), 1=required

# Output paths
DRIFT_WHYLOGS_OUTPUT=data/observability/whylogs/
DRIFT_ALERT_OUTPUT=data/observability/whylogs/alerts.json
DRIFT_PROMETHEUS_OUTPUT=data/observability/whylogs/metrics.prom

# Slack alerting (optional)
DRIFT_SLACK_WEBHOOK=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
DRIFT_DASHBOARD_URL=https://grafana.example.com/d/whylogs-drift
```

## Graph Semantics

```bash
# Enable graph validation
GRAPH_SEMANTICS_ENABLED=1  # 0=disabled, 1=enabled (default)

# Node count thresholds
GRAPH_MIN_PROVINCE_NODES=1  # Minimum province nodes
GRAPH_MAX_PROVINCE_NODES=9  # Maximum province nodes (SA has 9)
GRAPH_MIN_STATUS_NODES=1    # Minimum status nodes
GRAPH_MAX_STATUS_NODES=10   # Maximum status nodes

# Edge thresholds
GRAPH_MIN_EDGES=1           # Minimum total edges
GRAPH_MAX_EDGES=10000       # Maximum total edges
GRAPH_MIN_AVG_DEGREE=1.0    # Minimum average node degree
```

## Plan→Commit Workflow

```bash
# Require plan→commit artifacts for destructive operations
PLAN_COMMIT_REQUIRED=1  # 0=optional, 1=required (default)

# Diff format for commit artifacts
PLAN_COMMIT_DIFF_FORMAT=markdown  # Options: markdown, json

# Audit log path
PLAN_COMMIT_AUDIT_LOG_PATH=data/logs/plan_commit_audit.jsonl

# Audit topic (for streaming)
PLAN_COMMIT_AUDIT_TOPIC=watercrawl.plan_commit_audit

# RAG safety thresholds (0.0-1.0)
PLAN_COMMIT_RAG_FAITHFULNESS=0.7
PLAN_COMMIT_RAG_CONTEXT_PRECISION=0.7
PLAN_COMMIT_RAG_ANSWER_RELEVANCY=0.7

# Emergency force bypass (use sparingly)
PLAN_COMMIT_ALLOW_FORCE=0  # 0=enforced (default), 1=allow bypass
```

## Infrastructure Planning

### Crawler Configuration

```bash
CRAWLER_FRONTIER_BACKEND=memory  # Options: memory, redis, postgres
CRAWLER_SCHEDULER_MODE=breadth_first  # Options: breadth_first, depth_first, priority
CRAWLER_POLITENESS_DELAY_SECONDS=1  # Delay between requests
CRAWLER_MAX_DEPTH=3  # Maximum crawl depth
CRAWLER_MAX_PAGES=1000  # Maximum pages per domain
CRAWLER_USER_AGENT=Watercrawl/1.0 (+https://github.com/IAmJonoBo/watercrawl)
CRAWLER_TRAP_RULES_PATH=/path/to/trap_rules.txt  # Optional URL trap rules
```

### Observability

```bash
OBSERVABILITY_PORT=8080  # Health probe port
OBSERVABILITY_ALERT_ROUTES=slack,pagerduty  # Comma-separated or JSON array

# SLO targets
SLO_AVAILABILITY_TARGET=0.999  # 99.9% uptime
SLO_LATENCY_P95_MS=500  # 95th percentile latency
SLO_ERROR_BUDGET_PERCENT=0.1  # 0.1% error budget
```

### Policy Enforcement

```bash
OPA_BUNDLE_PATH=/path/to/opa/bundle.tar.gz
OPA_DECISION_PATH=watercrawl/allow  # Decision namespace
OPA_ENFORCEMENT_MODE=enforce  # Options: enforce, dry-run
OPA_CACHE_SECONDS=300  # Policy cache TTL
```

## Logging & Debugging

```bash
# Log level
LOG_LEVEL=INFO  # Options: DEBUG, INFO, WARNING, ERROR, CRITICAL

# Enable verbose output
VERBOSE=0  # 0=normal, 1=verbose

# MCP server log level
MCP_LOG_LEVEL=INFO  # Options: DEBUG, INFO, WARNING, ERROR
```

## Performance Tuning

```bash
# Batch size for processing
BATCH_SIZE=1000  # Number of rows per batch

# Worker threads for parallel processing
MAX_WORKERS=4  # Number of concurrent workers

# Request timeout (seconds)
REQUEST_TIMEOUT=30

# Retry configuration
MAX_RETRIES=3
RETRY_BACKOFF_FACTOR=2
```

## Testing & Development

```bash
# Enable test mode (uses deterministic adapters)
TEST_MODE=0  # 0=normal, 1=test mode

# Problems report configuration
PROBLEMS_MAX_ISSUES=100  # Maximum issues per tool in problems_report.json

# Enable Pylint in problems report
ENABLE_PYLINT=0  # 0=disabled (default), 1=enabled

# VS Code problems export path
VSCODE_PROBLEMS_EXPORT=/path/to/vscode_problems.json
```

## Configuration Validation

Validate your configuration:

```bash
# Check current configuration
poetry run python -c "
from firecrawl_demo.core.config import get_config
config = get_config()
print(config)
"

# Verify secrets backend
poetry run python -c "
from firecrawl_demo.governance.secrets import SecretsProvider
provider = SecretsProvider()
print(f'Backend: {provider.backend}')
"
```

## Example Configurations

### Development (Offline)

```bash
# .env.development
SECRETS_BACKEND=env
FEATURE_ENABLE_FIRECRAWL_SDK=0
ALLOW_NETWORK_RESEARCH=0
REFINEMENT_PROFILE=za_flight_schools
LOG_LEVEL=DEBUG
VERBOSE=1
```

### Production (Online)

```bash
# .env.production
SECRETS_BACKEND=aws
AWS_REGION=us-east-1
AWS_SECRETS_PREFIX=prod/watercrawl/
FEATURE_ENABLE_FIRECRAWL_SDK=1
ALLOW_NETWORK_RESEARCH=1
PLAN_COMMIT_REQUIRED=1
DRIFT_ENABLED=1
DRIFT_SLACK_WEBHOOK=https://hooks.slack.com/services/YOUR/WEBHOOK
LOG_LEVEL=INFO
```

### Testing (Deterministic)

```bash
# .env.test
TEST_MODE=1
FEATURE_ENABLE_FIRECRAWL_SDK=0
ALLOW_NETWORK_RESEARCH=0
EVIDENCE_SINK_BACKEND=csv
OPENLINEAGE_TRANSPORT=logging
LOG_LEVEL=WARNING
```

## Next Steps

- [Getting Started](/guides/getting-started/) - Initial setup
- [CLI Guide](/cli/) - Command usage
- [Troubleshooting](/guides/troubleshooting/) - Configuration issues
