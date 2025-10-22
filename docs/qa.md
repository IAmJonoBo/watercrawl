---
title: QA Runbooks
description: Procedures for regenerating fixtures and diagnosing gate failures
---

# QA Runbooks

This document provides step-by-step procedures for maintaining test fixtures and diagnosing CI gate failures.

## Regenerating Test Fixtures

### Sample Dataset Fixtures

To regenerate test fixtures for system integration tests:

```bash
# Create minimal sample dataset
poetry run python << 'EOF'
import pandas as pd
from pathlib import Path

# Create tests/data if it doesn't exist
Path("tests/data").mkdir(exist_ok=True)

# Generate minimal dataset
data = pd.DataFrame([
    {
        "Name of Organisation": "Test Flight School",
        "Province": "Gauteng",
        "Status": "Candidate",
        "Website URL": "",
        "Contact Person": "",
        "Contact Number": "",
        "Contact Email Address": "",
    }
])
data.to_csv("tests/data/sample_minimal.csv", index=False)
print("✓ Created tests/data/sample_minimal.csv")

# Generate multi-row dataset
data_multi = pd.DataFrame([
    {
        "Name of Organisation": f"Test School {i}",
        "Province": "Gauteng" if i % 2 == 0 else "Western Cape",
        "Status": "Candidate",
        "Website URL": "",
        "Contact Person": "",
        "Contact Number": "",
        "Contact Email Address": "",
    }
    for i in range(10)
])
data_multi.to_csv("tests/data/sample_multi_row.csv", index=False)
print("✓ Created tests/data/sample_multi_row.csv")
EOF
```

### Contract Schema Fixtures

To regenerate contract schema JSON fixtures:

```bash
# Export all schemas
poetry run python << 'EOF'
from pathlib import Path
import json
from firecrawl_demo.domain.contracts import export_all_schemas

# Create fixtures directory
Path("tests/fixtures/schemas").mkdir(parents=True, exist_ok=True)

# Export schemas
schemas = export_all_schemas()
for name, schema in schemas.items():
    output_path = Path(f"tests/fixtures/schemas/{name}.json")
    output_path.write_text(json.dumps(schema, indent=2))
    print(f"✓ Exported {name} schema")

print(f"✓ Exported {len(schemas)} schemas to tests/fixtures/schemas/")
EOF
```

### Evidence Log Fixtures

To generate evidence log fixtures for contract tests:

```bash
# Create sample evidence logs
poetry run python << 'EOF'
import pandas as pd
from pathlib import Path

Path("tests/fixtures/evidence").mkdir(parents=True, exist_ok=True)

# Sample evidence with valid structure
evidence_data = {
    "RowID": [1, 2],
    "Organisation": ["School 1", "School 2"],
    "What changed": ["Status -> Verified", "Contact Person -> John Doe"],
    "Sources": ["https://school1.co.za", "https://school2.co.za"],
    "Notes": ["Quality gate passed", "Enriched from research"],
    "Timestamp": ["2025-01-01T00:00:00+00:00", "2025-01-01T00:01:00+00:00"],
    "Confidence": [95, 90],
}

df = pd.DataFrame(evidence_data)
df.to_csv("tests/fixtures/evidence/sample_valid.csv", index=False)
print("✓ Created tests/fixtures/evidence/sample_valid.csv")
EOF
```

### Performance Baseline Fixtures

To regenerate performance baseline measurements:

```bash
# Run performance tests and capture baselines
poetry run pytest -m performance -v -s | tee tests/fixtures/performance_baseline.txt

# Extract key metrics for threshold validation
grep "Throughput:" tests/fixtures/performance_baseline.txt
grep "Speedup:" tests/fixtures/performance_baseline.txt
```

## Diagnosing Gate Failures

### Contract Consumer Test Failures

**Symptom:** `tests/test_contract_consumers.py` fails with validation errors

**Diagnosis:**
```bash
# Run contract tests with verbose output
poetry run pytest tests/test_contract_consumers.py -v -s

# Check schema export
poetry run python -c "from firecrawl_demo.domain.contracts import export_all_schemas; print(list(export_all_schemas.keys()))"

# Validate specific contract
poetry run python << 'EOF'
from firecrawl_demo.domain.contracts import EvidenceRecordContract

try:
    record = EvidenceRecordContract(
        row_id=1,
        organisation="Test",
        changes="Status -> Verified",
        sources=["https://test.co.za"],
        notes="Test",
        timestamp="2025-01-01T00:00:00+00:00",
        confidence=90
    )
    print("✓ Contract validates")
except Exception as e:
    print(f"✗ Validation failed: {e}")
EOF
```

**Resolution:**
1. Check if contract model definitions changed in `firecrawl_demo/domain/contracts.py`
2. Verify test data matches current contract schema
3. Update contract version if schema changed
4. Regenerate fixtures if needed

### Performance Smoke Test Failures

**Symptom:** `test_performance_smoke.py` fails with threshold violations

**Diagnosis:**
```bash
# Run performance tests with detailed timing
poetry run pytest -m performance -v -s --tb=short

# Profile specific slow test
poetry run pytest tests/test_performance_smoke.py::test_pipeline_throughput_10_rows -v -s --profile

# Check system resources
free -h
cat /proc/cpuinfo | grep "model name" | head -1
```

**Resolution:**
1. Verify CI runner has sufficient resources (check Actions logs)
2. Check for regression in recent commits:
   ```bash
   git log --oneline -10 firecrawl_demo/application/pipeline.py
   ```
3. Compare timing with baseline in `tests/fixtures/performance_baseline.txt`
4. If legitimate slowdown, adjust thresholds in test file
5. If regression, revert changes or optimize

**Threshold adjustment process:**
1. Run tests locally 10 times to get consistent baseline
2. Set threshold to 2x mean time (allows for CI variance)
3. Document reason for adjustment in commit message

### System Integration Test Failures

**Symptom:** `tests/system/test_cli_enrichment.py` fails

**Diagnosis:**
```bash
# Run system tests with full output
poetry run pytest tests/system/ -v -s

# Test CLI directly
poetry run python -m firecrawl_demo.interfaces.cli enrich \
  tests/data/sample_minimal.csv \
  --output /tmp/test_output.csv \
  --evidence-log /tmp/test_evidence.csv

# Check outputs
ls -lh /tmp/test_*.csv
head /tmp/test_evidence.csv
```

**Resolution:**
1. Verify sample dataset exists: `tests/data/sample_minimal.csv`
2. Check CLI module import path is correct
3. Review CLI error output in test logs
4. Ensure evidence sink is properly configured
5. Regenerate fixtures if data format changed

### Evidence Sink Write Failures

**Symptom:** Tests fail with "Evidence log not created" or empty evidence

**Diagnosis:**
```bash
# Check evidence sink configuration
poetry run python << 'EOF'
from firecrawl_demo.infrastructure.evidence import CSVEvidenceSink
from pathlib import Path
import tempfile

with tempfile.TemporaryDirectory() as tmpdir:
    log_path = Path(tmpdir) / "evidence.csv"
    sink = CSVEvidenceSink(log_path)
    
    # Try writing
    from firecrawl_demo.domain.models import EvidenceRecord
    from datetime import datetime, UTC
    
    record = EvidenceRecord(
        row_id=1,
        organisation="Test",
        changes="Status -> Verified",
        sources=["https://test.co.za"],
        notes="Test note",
        confidence=90,
        timestamp=datetime.now(UTC)
    )
    
    sink.record([record])
    
    if log_path.exists():
        print(f"✓ Evidence written to {log_path}")
        print(log_path.read_text())
    else:
        print("✗ Evidence not written")
EOF
```

**Resolution:**
1. Verify output directory exists and is writable
2. Check evidence sink initialization in pipeline
3. Ensure evidence records are being generated (check `pipeline.evidence_log`)
4. Review evidence sink implementation for file I/O errors

### Telemetry Output Failures

**Symptom:** Prometheus/whylogs outputs not generated

**Diagnosis:**
```bash
# Check telemetry configuration
echo "DRIFT_PROMETHEUS_OUTPUT: ${DRIFT_PROMETHEUS_OUTPUT}"
echo "DRIFT_WHYLOGS_OUTPUT: ${DRIFT_WHYLOGS_OUTPUT}"

# Test drift tooling
poetry run python << 'EOF'
from firecrawl_demo.integrations.telemetry.drift import (
    compare_to_baseline,
    log_whylogs_profile,
)
import pandas as pd
from pathlib import Path
import tempfile

# Create test data
df = pd.DataFrame([{"Status": "Verified", "Province": "Gauteng"}])

with tempfile.TemporaryDirectory() as tmpdir:
    profile_path = Path(tmpdir) / "test.whylogs"
    info = log_whylogs_profile(df, profile_path)
    print(f"✓ Profile written: {info.profile_path}")
    print(f"  Metadata: {info.metadata_path}")
EOF
```

**Resolution:**
1. Verify drift tools are properly installed
2. Check environment variables are set correctly
3. Ensure baseline files exist if `DRIFT_REQUIRE_BASELINE=1`
4. Review drift configuration in `firecrawl_demo/core/config.py`

## CI Dashboard Interpretation

### Coverage Delta

Coverage delta shows in PR checks:
- **Green:** Coverage increased or stayed same
- **Yellow:** Minor coverage decrease (< 2%)
- **Red:** Significant coverage decrease (≥ 2%)

**Action for red coverage:**
1. Review uncovered lines in PR diff
2. Add tests for new code paths
3. Or add `# pragma: no cover` with justification

### Test Results Summary

CI summary includes:
- Unit tests: Pass/fail count
- Contract tests: Schema validation status
- Performance tests: Threshold violations
- System tests: Integration workflow status

**Action for failures:**
1. Click "Details" link in PR checks
2. Review specific test failure
3. Follow diagnostic runbook above
4. Fix and push update

### Performance Metrics

Performance tests log throughput metrics:
```
Throughput: 45.2 rows/sec (10 rows in 0.22s)
Speedup: 2.1x (0.24s vs 0.50s expected sequential)
```

**Interpretation:**
- Throughput should be ≥ 40 rows/sec (null adapter)
- Speedup should be ≥ 1.5x for concurrent tests
- If below threshold, test fails

## Maintenance Schedule

### Weekly
- Review CI failure patterns
- Update performance baselines if environment changed
- Check coverage trends

### Monthly
- Regenerate all test fixtures
- Update contract schemas if models changed
- Review and adjust performance thresholds

### Quarterly
- Full fixture refresh from production dataset
- Performance baseline recalibration
- Contract versioning audit

## Emergency Procedures

### All Tests Failing

1. Check CI system status
2. Verify dependencies are installable:
   ```bash
   poetry install --no-root
   ```
3. Run locally to isolate CI vs code issue
4. Check recent commits for breaking changes

### Intermittent Failures

1. Re-run failed jobs (flaky test indicator)
2. Check for timing-dependent tests
3. Add retry logic if external dependencies involved
4. Report persistent flakes as issues

### Performance Regression

1. Bisect to find regression commit:
   ```bash
   git bisect start
   git bisect bad HEAD
   git bisect good <last_known_good_commit>
   # Test each commit with performance suite
   ```
2. Review changes in regression commit
3. Optimize or adjust thresholds with justification
