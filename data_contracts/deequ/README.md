# Deequ Contracts

This directory houses Deequ configuration for JVM-based data quality checks
via PySpark. Deequ is optional and requires PySpark to be installed.

## Status

**Phase 1 (Current)**: Deterministic Deequ integration that enforces HTTPS,
duplicate detection, verified-contact completeness, and confidence thresholds
using pandas so contracts fail fast even without PySpark.

**Future**: Full Deequ integration with PySpark-based quality checks for
large-scale data validation.

## Usage

The Deequ runner executes automatically:

```python
from watercrawl.integrations.contracts import run_deequ_checks

result = run_deequ_checks(dataset_path)
if result.success:
    print(f"All {result.check_count} Deequ checks passed")
else:
    print(f"{result.failures} checks failed")
    for outcome in result.results:
        if not outcome["success"]:
            print(outcome["check"], outcome["details"])
```

## Configuration

Future Deequ checks will be configured in JSON files within this directory,
one per curated table:

- `sample.json` - Deequ checks for the sample dataset
- `enriched.json` - Deequ checks for enriched datasets

Each configuration file will specify:

- Completeness checks
- Uniqueness constraints
- Numeric range validations
- Custom PySpark SQL constraints

## Dependencies

Deequ requires:

- PySpark >= 3.0
- Amazon Deequ JVM library (via Maven coordinates)

These are optional dependencies and not required for the baseline pipeline.
