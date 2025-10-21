---
title: Advanced Configuration
description: Performance tuning, production deployment, and custom adapter development
---

# Advanced Configuration

This guide covers advanced configuration topics for production deployments, performance optimization, and extending Watercrawl with custom adapters.

## Production Deployment

### Environment Separation

Maintain separate configurations for development, staging, and production:

```bash
# Development (.env.development)
SECRETS_BACKEND=env
ALLOW_NETWORK_RESEARCH=0
LOG_LEVEL=DEBUG
FEATURE_ENABLE_CACHE=1

# Production (.env.production)
SECRETS_BACKEND=aws
AWS_REGION=us-east-1
AWS_SECRETS_PREFIX=prod/watercrawl/
ALLOW_NETWORK_RESEARCH=1
LOG_LEVEL=INFO
FEATURE_ENABLE_CACHE=1
```

Load environment-specific configuration:

```bash
# Use with environment variable
export ENV=production
poetry run python -m apps.analyst.cli enrich data/input.csv
```

### Secrets Management

#### AWS Secrets Manager

```bash
# Store secrets in AWS
aws secretsmanager create-secret \
  --name prod/watercrawl/FIRECRAWL_API_KEY \
  --secret-string "your_api_key_here" \
  --region us-east-1

# Configure Watercrawl
export SECRETS_BACKEND=aws
export AWS_REGION=us-east-1
export AWS_SECRETS_PREFIX=prod/watercrawl/
```

#### Azure Key Vault

```bash
# Store secrets in Azure
az keyvault secret set \
  --vault-name watercrawl-vault \
  --name FIRECRAWL-API-KEY \
  --value "your_api_key_here"

# Configure Watercrawl
export SECRETS_BACKEND=azure
export AZURE_KEY_VAULT_URL=https://watercrawl-vault.vault.azure.net/
export AZURE_SECRETS_PREFIX=watercrawl-
```

### Docker Deployment

```dockerfile
# Dockerfile
FROM python:3.13-slim

WORKDIR /app

# Install Poetry
RUN pip install poetry==1.8.0

# Copy dependencies first for layer caching
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --only main

# Copy application code
COPY firecrawl_demo ./firecrawl_demo
COPY apps ./apps
COPY data_contracts ./data_contracts

# Run as non-root user
RUN useradd -m -u 1000 watercrawl
USER watercrawl

# Default command
CMD ["poetry", "run", "python", "-m", "apps.analyst.cli", "--help"]
```

Build and run:

```bash
# Build image
docker build -t watercrawl:latest .

# Run with environment file
docker run --env-file .env.production \
  -v $(pwd)/data:/app/data \
  watercrawl:latest \
  poetry run python -m apps.analyst.cli enrich /app/data/input.csv
```

### Docker Compose

```yaml
# docker-compose.yml
services:
  watercrawl:
    image: watercrawl:latest
    env_file: .env.production
    volumes:
      - ./data:/app/data:rw
      - ./artifacts:/app/artifacts:rw
    networks:
      - watercrawl-net
    restart: unless-stopped

  duckdb:
    image: duckdb/duckdb:latest
    volumes:
      - ./data/lakehouse:/data:rw
    networks:
      - watercrawl-net

networks:
  watercrawl-net:
    driver: bridge
```

Run with:

```bash
docker-compose up -d
```

## Performance Tuning

### Caching Configuration

Enable caching for research results to reduce API calls and improve performance:

```bash
FEATURE_ENABLE_CACHE=1
CACHE_TTL_SECONDS=3600  # 1 hour
CACHE_DIR=.cache/watercrawl
```

Customize caching behavior:

```python
from firecrawl_demo.core.config import CacheConfig

config = CacheConfig(
    enabled=True,
    ttl_seconds=7200,  # 2 hours
    cache_dir=".cache/research",
    max_size_mb=500  # Maximum cache size
)
```

### Parallel Processing

Process large datasets in parallel using profile-based configuration:

```bash
# Enable parallel processing
export ENABLE_PARALLEL=1
export MAX_WORKERS=4

# Run with parallel processing
poetry run python -m apps.analyst.cli enrich \
  data/large_dataset.csv \
  --parallel \
  --workers 4
```

### Batch Processing

Process datasets in batches to manage memory:

```bash
poetry run python -m apps.analyst.cli enrich \
  data/input.csv \
  --batch-size 100 \
  --output data/enriched.csv
```

### Database Optimization

For DuckDB lakehouse exports:

```sql
-- Optimize table with compression
COPY (SELECT * FROM curated_dataset) 
TO 'data/lakehouse/curated.parquet' 
(FORMAT PARQUET, COMPRESSION ZSTD);

-- Create indexes for faster queries
CREATE INDEX idx_org_name ON curated_dataset(organisation_name);
CREATE INDEX idx_province ON curated_dataset(province);
```

## Scaling Strategies

### Horizontal Scaling

Run multiple instances for different dataset partitions:

```bash
# Instance 1: Process provinces 1-3
poetry run python -m apps.analyst.cli enrich \
  data/partition_1.csv \
  --filter-province "Eastern Cape,Free State,Gauteng"

# Instance 2: Process provinces 4-6
poetry run python -m apps.analyst.cli enrich \
  data/partition_2.csv \
  --filter-province "KwaZulu-Natal,Limpopo,Mpumalanga"
```

### Load Balancing

Use a task queue for distributed processing:

```python
# tasks.py using Celery
from celery import Celery
from apps.analyst.cli import enrich_record

app = Celery('watercrawl', broker='redis://localhost:6379/0')

@app.task
def enrich_organisation(org_data):
    return enrich_record(org_data)

# Dispatch tasks
for org in organisations:
    enrich_organisation.delay(org)
```

### Cloud Functions

Deploy as serverless functions for event-driven processing:

```yaml
# AWS Lambda (serverless.yml)
service: watercrawl-enrichment

provider:
  name: aws
  runtime: python3.13
  region: us-east-1
  environment:
    SECRETS_BACKEND: aws
    AWS_SECRETS_PREFIX: prod/watercrawl/

functions:
  enrich:
    handler: handler.enrich_handler
    events:
      - s3:
          bucket: watercrawl-input
          event: s3:ObjectCreated:*
          rules:
            - suffix: .csv
```

## Custom Adapter Development

### Creating a Research Adapter

Extend Watercrawl with custom research sources:

```python
# firecrawl_demo/integrations/adapters/custom_adapter.py
from typing import Dict, List, Optional
from firecrawl_demo.interfaces.adapters import ResearchAdapter, ResearchResult

class CustomDirectoryAdapter(ResearchAdapter):
    """Custom adapter for proprietary directory service."""
    
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url
    
    def search(
        self, 
        query: str, 
        filters: Optional[Dict] = None
    ) -> List[ResearchResult]:
        """Search custom directory for organisations."""
        response = self._make_request(query, filters)
        return [self._parse_result(r) for r in response.results]
    
    def _make_request(self, query: str, filters: Optional[Dict]) -> Dict:
        """Make API request to custom directory."""
        # Implementation details
        pass
    
    def _parse_result(self, raw_result: Dict) -> ResearchResult:
        """Parse directory result into ResearchResult."""
        return ResearchResult(
            source="CustomDirectory",
            confidence=0.85,
            data=raw_result,
            evidence_url=raw_result.get('profile_url')
        )
```

### Registering Custom Adapters

```python
# apps/analyst/cli.py
from firecrawl_demo.integrations.adapters.custom_adapter import CustomDirectoryAdapter

# Register adapter
adapter = CustomDirectoryAdapter(
    api_key=os.getenv('CUSTOM_DIR_API_KEY'),
    base_url='https://directory.example.com/api/v1'
)

# Use in enrichment pipeline
enricher.register_adapter('custom_directory', adapter)
```

### Adapter Configuration

```bash
# .env
CUSTOM_DIR_API_KEY=your_api_key_here
CUSTOM_DIR_BASE_URL=https://directory.example.com/api/v1
FEATURE_ENABLE_CUSTOM_DIRECTORY=1
```

### Testing Custom Adapters

```python
# tests/test_custom_adapter.py
import pytest
from firecrawl_demo.integrations.adapters.custom_adapter import CustomDirectoryAdapter

@pytest.fixture
def adapter():
    return CustomDirectoryAdapter(
        api_key='test_key',
        base_url='https://test.example.com'
    )

def test_search_returns_results(adapter):
    results = adapter.search('flight school')
    assert len(results) > 0
    assert all(r.source == 'CustomDirectory' for r in results)

def test_confidence_scoring(adapter):
    results = adapter.search('Test Organisation')
    assert all(0.0 <= r.confidence <= 1.0 for r in results)
```

## Monitoring & Observability

### Logging Configuration

```python
# Configure structured logging
import logging
from pythonjsonlogger import jsonlogger

logger = logging.getLogger()
handler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter()
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)
```

### Metrics Collection

```bash
# Export metrics for Prometheus
export ENABLE_METRICS=1
export METRICS_PORT=9090

# Expose metrics endpoint
poetry run python -m apps.analyst.cli serve-metrics
```

### Health Checks

```python
# health.py
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "services": {
            "cache": cache.is_healthy(),
            "database": db.is_connected()
        }
    }
```

## Advanced Features

### Profile-Based Configuration

Use profiles for different use cases:

```bash
# profiles/production.yml
environment: production
cache_enabled: true
parallel_workers: 8
research_adapters:
  - firecrawl
  - regulator
  - press

# Load profile
poetry run python -m apps.analyst.cli enrich \
  data/input.csv \
  --profile profiles/production.yml
```

### Feature Flag Management

Control features dynamically without code changes:

```python
# Feature flag configuration
from firecrawl_demo.core.feature_flags import FeatureFlags

flags = FeatureFlags.from_env()
if flags.is_enabled('PRESS_RESEARCH'):
    results.extend(press_adapter.search(query))
```

### Rate Limiting

Protect external APIs with rate limiting:

```python
from ratelimit import limits, sleep_and_retry

@sleep_and_retry
@limits(calls=100, period=60)  # 100 calls per minute
def call_external_api(query):
    return api.search(query)
```

## Troubleshooting

### Debug Mode

```bash
export LOG_LEVEL=DEBUG
poetry run python -m apps.analyst.cli enrich data/input.csv
```

### Performance Profiling

```bash
# Profile CPU usage
poetry run python -m cProfile -o profile.stats \
  -m apps.analyst.cli enrich data/input.csv

# View results
poetry run python -m pstats profile.stats
```

### Memory Profiling

```bash
# Install memory profiler
poetry add memory-profiler

# Profile memory usage
poetry run python -m memory_profiler apps/analyst/cli.py
```

## See Also

- [Configuration Reference](/reference/configuration/) - Environment variables and feature flags
- [CLI Commands](/cli/) - Command-line interface documentation
- [Architecture](/architecture/) - System design and component relationships
- [Operations](/operations/) - Day-to-day operational procedures

---

**Last Updated**: 2025-10-21  
**Configuration Version**: 1.0.0
