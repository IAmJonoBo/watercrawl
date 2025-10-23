---
title: Troubleshooting Guide
description: Solutions to common problems and error messages
---

This guide helps you diagnose and resolve common issues when working with Watercrawl.

## Installation Issues

### Poetry Command Not Found

**Symptom**: Running `poetry` returns "command not found"

**Solution**:

```bash
# Install Poetry via official installer
curl -sSL https://install.python-poetry.org | python3 -

# Add to PATH (add to ~/.bashrc or ~/.zshrc for persistence)
export PATH="$HOME/.local/bin:$PATH"

# Verify installation
poetry --version
```

### Python Version Incompatibility

**Symptom**: Error messages about Python version mismatch

**Solution**:

```bash
# Check current Python version
python --version

# Install Python 3.13 via pyenv (recommended)
curl https://pyenv.run | bash
pyenv install 3.13.0
pyenv local 3.13.0

# Or via apt (Ubuntu/Debian)
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.13 python3.13-venv
```

### Dependency Installation Failures

**Symptom**: `poetry install` fails with wheel build errors

**Solution**:

```bash
# Clear Poetry cache
poetry cache clear --all .

# Update Poetry itself
poetry self update

# Try installing without cache
poetry install --no-root --with dev --no-cache

# If specific package fails, check Python 3.14 compatibility
poetry run python -m scripts.wheel_status
```

:::tip[Known Python 3.14 Issues]
Some packages (PyArrow, Delta Lake) don't yet support Python 3.14. Install from Python 3.13 if you need UI or lakehouse features:

```bash
poetry env use 3.13
poetry install --with ui --with lakehouse
```
:::

## Runtime Errors

### Import Errors

**Symptom**: `ModuleNotFoundError` or `ImportError`

**Solution**:

```bash
# Verify virtual environment is activated
poetry env info

# Ensure dependencies are installed
poetry install --no-root --with dev

# Check for missing optional dependencies
poetry install --with ui --with lakehouse

# Verify Python path
poetry run python -c "import sys; print(sys.path)"
```

### Evidence Log Errors

**Symptom**: `PermissionError` or file not found when writing evidence log

**Solution**:

```bash
# Ensure directory exists
mkdir -p data/interim

# Check file permissions
ls -la data/interim/

# Set appropriate permissions
chmod 755 data/interim/
```

**Symptom**: Evidence log has incorrect format

**Solution**:

```bash
# Validate evidence log structure
poetry run python -c "
import pandas as pd
df = pd.read_csv('data/interim/evidence_log.csv')
print(df.columns.tolist())
"

# Expected columns: RowID, Organisation, Changes, Sources, Notes, Timestamp, Confidence
```

### Validation Failures

**Symptom**: Dataset validation fails with unclear errors

**Solution**:

```bash
# Run validation with verbose output
poetry run python -m apps.analyst.cli validate data/input.csv \
  --format json \
  --progress

# Check for common issues:
# 1. Province names not in South African taxonomy
# 2. Phone numbers not in E.164 format (+27...)
# 3. Email domains without MX records
# 4. Missing required columns

# View detailed validation report
cat validation_report.json | jq '.issues'
```

### Enrichment Pipeline Errors

**Symptom**: Pipeline crashes during enrichment

**Solution**:

```bash
# Check for feature flag misconfigurations
echo "ALLOW_NETWORK_RESEARCH=${ALLOW_NETWORK_RESEARCH}"
echo "FEATURE_ENABLE_FIRECRAWL_SDK=${FEATURE_ENABLE_FIRECRAWL_SDK}"

# Run with offline adapters (safest)
export FEATURE_ENABLE_FIRECRAWL_SDK=0
export ALLOW_NETWORK_RESEARCH=0

# Check adapter failures in pipeline metrics
poetry run python -m apps.analyst.cli enrich data/sample.csv \
  --output /tmp/test_output.csv \
  2>&1 | grep "adapter_failures"

# Review problems report
poetry run python scripts/collect_problems.py
cat problems_report.json
```

## Data Contract Failures

### Great Expectations Failures

**Symptom**: Data contracts fail with expectation violations

**Solution**:

```bash
# Run contracts with verbose output
poetry run python -m apps.analyst.cli contracts data/enriched.csv \
  --verbose \
  --format json

# Common failures and fixes:
# 1. Missing evidence_count >= 2: Re-enrich with proper sources
# 2. Province not in taxonomy: Fix province names in input
# 3. Confidence < 70: Review research adapter settings

# Inspect Great Expectations validation results
ls -la data/contracts/latest/great_expectations/
cat data/contracts/latest/great_expectations/validation_results.json | jq
```

### dbt Test Failures

**Symptom**: dbt tests fail during contract execution

**Solution**:

```bash
# Run dbt directly for detailed output
cd data_contracts/analytics
poetry run dbt test --profiles-dir . --target ci

# Check dbt logs
tail -f logs/dbt.log

# Common issues:
# 1. DuckDB version mismatch: poetry update duckdb
# 2. Missing curated_source_path variable
# 3. SQL syntax errors in custom tests

# Run specific test
poetry run dbt test --select tag:contracts
```

## MCP Server Issues

### Connection Errors

**Symptom**: MCP server won't start or GitHub Copilot can't connect

**Solution**:

```bash
# Check if server starts
poetry run python -m app.cli mcp-server --help

# Verify no port conflicts (default: 3000)
lsof -i :3000

# Start with debug logging
export MCP_LOG_LEVEL=debug
poetry run python -m app.cli mcp-server

# Test MCP endpoints manually
curl http://localhost:3000/health
```

### Plan→Commit Guard Failures

**Symptom**: MCP operations rejected due to missing plan artifacts

**Solution**:

```bash
# Create plan artifacts before destructive operations
mkdir -p tmp/plans

# Generate plan
poetry run python -m apps.automation.cli qa plan \
  --write-plan tmp/plans/enrich.plan

# Review plan
cat tmp/plans/enrich.plan

# Execute with plan reference
poetry run python -m apps.analyst.cli enrich data/sample.csv \
  --output data/enriched.csv \
  --plan tmp/plans/enrich.plan

# For emergency bypass (use sparingly)
export PLAN_COMMIT_ALLOW_FORCE=1
```

## Performance Issues

### Slow Enrichment

**Symptom**: Enrichment takes very long on large datasets

**Solutions**:

```bash
# Enable caching
export FEATURE_ENABLE_CACHE=1

# Use offline mode (fastest)
export FEATURE_ENABLE_FIRECRAWL_SDK=0
export ALLOW_NETWORK_RESEARCH=0

# Process in smaller batches
split -l 1000 data/large_input.csv data/batch_

# Profile to find bottlenecks
poetry run python -m cProfile -s cumtime -o profile.stats \
  -m apps.analyst.cli enrich data/sample.csv --output /tmp/out.csv

# View profiling results
poetry run python -c "
import pstats
p = pstats.Stats('profile.stats')
p.sort_stats('cumtime')
p.print_stats(20)
"
```

### High Memory Usage

**Symptom**: Process uses excessive RAM or crashes with OOM

**Solutions**:

```bash
# Monitor memory usage
poetry run mprof run python -m apps.analyst.cli enrich data/large.csv
poetry run mprof plot

# Process in chunks (planned feature - manual workaround)
head -n 1 data/large.csv > header.csv
tail -n +2 data/large.csv | split -l 500 - chunk_
for chunk in chunk_*; do
  cat header.csv "$chunk" > "temp_$chunk.csv"
  poetry run python -m apps.analyst.cli enrich "temp_$chunk.csv" \
    --output "enriched_$chunk.csv"
done

# Combine results
cat header.csv > data/final_enriched.csv
tail -q -n +2 enriched_chunk_*.csv >> data/final_enriched.csv
```

## Quality Gate Failures

### Linting Errors

**Symptom**: Pre-commit or CI linting failures

**Solution**:

```bash
# Run auto-fixers
poetry run ruff check . --fix
poetry run black .
poetry run isort .

# For Markdown issues
poetry run pre-commit run markdownlint-cli2 --all-files

# Generate problems report
poetry run python scripts/collect_problems.py
cat problems_report.json | jq '.tools[] | select(.status != "completed")'

# Fix specific tool issues
# Ruff: poetry run ruff check --show-source
# Mypy: poetry run mypy . --show-error-context
# Bandit: Review security warnings in output
```

### Type Check Failures

**Symptom**: mypy reports type errors

**Solution**:

```bash
# Sync type stubs
poetry run python -m scripts.sync_type_stubs --sync

# Set MYPYPATH
export MYPYPATH="$PWD/stubs/third_party:$PWD/stubs"

# Run with verbose output
poetry run mypy . --show-error-codes --show-error-context

# Common issues:
# 1. Missing stubs: Add to stubs/third_party/
# 2. Dynamic imports: Use TYPE_CHECKING guard
# 3. Pandas type issues: Update stubs
```

### Test Failures

**Symptom**: pytest failures in CI or locally

**Solution**:

```bash
# Run specific failing test with verbose output
poetry run pytest tests/test_specific.py::test_function -vvs

# Check for dependency conflicts
poetry show --tree | grep -A 5 -B 5 problematic_package

# Update test dependencies
poetry update --only test

# Run with coverage to identify untested paths
poetry run pytest --cov=watercrawl --cov-report=html
# Open htmlcov/index.html in browser

# For async test issues
poetry run pytest tests/ -v --log-cli-level=DEBUG
```

## Drift Detection Issues

### Missing Baselines

**Symptom**: `drift_baseline_missing` or `whylogs_baseline_missing` errors

**Solution**:

```bash
# Generate drift baseline
poetry run python -m tools.observability.seed_drift_baseline

# Verify baseline files exist
ls -la data/observability/whylogs/

# Set baseline paths
export DRIFT_BASELINE_PATH=data/observability/whylogs/drift_baseline.json
export DRIFT_WHYLOGS_BASELINE=data/observability/whylogs/whylogs_metadata.json

# Require baselines in validation
export DRIFT_REQUIRE_BASELINE=1
export DRIFT_REQUIRE_WHYLOGS_METADATA=1
```

### False Drift Alerts

**Symptom**: Drift alerts on expected distribution changes

**Solution**:

```bash
# Review drift thresholds
echo "DRIFT_THRESHOLD=${DRIFT_THRESHOLD:-0.15}"

# Adjust threshold (0.0 to 1.0)
export DRIFT_THRESHOLD=0.25

# Regenerate baseline after confirmed distribution shift
poetry run python -m tools.observability.seed_drift_baseline \
  --input data/latest_production.csv

# Review drift report
cat data/observability/whylogs/alerts.json | jq
```

## Diagnostic Commands

### System Health Check

```bash
# Full diagnostic suite
poetry run python -m apps.automation.cli qa all --dry-run

# Check environment
poetry env info
poetry check
python --version

# Verify dependencies
poetry show --tree

# Run problems collector
poetry run python scripts/collect_problems.py
```

### Generate Debug Bundle

```bash
# Create debug bundle for issue reports
mkdir -p /tmp/watercrawl-debug

# Collect system info
poetry env info > /tmp/watercrawl-debug/env_info.txt
python --version > /tmp/watercrawl-debug/python_version.txt
poetry show --tree > /tmp/watercrawl-debug/dependencies.txt

# Run diagnostics
poetry run python scripts/collect_problems.py
cp problems_report.json /tmp/watercrawl-debug/

# Collect logs
cp -r data/logs/*.log /tmp/watercrawl-debug/ 2>/dev/null || true

# Package
tar -czf watercrawl-debug.tar.gz -C /tmp watercrawl-debug/
echo "Debug bundle created: watercrawl-debug.tar.gz"
```

## Getting Additional Help

If you're still stuck after trying these solutions:

1. **Check Problems Report**: `cat problems_report.json | jq`
2. **Review CI Logs**: Look for similar failures in GitHub Actions
3. **Search Issues**: [GitHub Issues](https://github.com/IAmJonoBo/watercrawl/issues)
4. **Create New Issue**: Include your debug bundle and steps to reproduce

### Issue Template

When creating an issue, include:

- **Watercrawl version**: `git describe --tags`
- **Python version**: `python --version`
- **OS**: `uname -a` (Linux/macOS) or `ver` (Windows)
- **Error message**: Full error output
- **Steps to reproduce**: Minimal example
- **Debug bundle**: Attach `watercrawl-debug.tar.gz`

---

**Still having issues?** Join the discussion on [GitHub Discussions](https://github.com/IAmJonoBo/watercrawl/discussions) or check our [FAQ](/guides/faq/).
