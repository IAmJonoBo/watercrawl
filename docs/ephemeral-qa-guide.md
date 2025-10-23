---
title: QA on Ephemeral Runners
description: Quick-start guide for running QA tools on ephemeral environments
---

# QA on Ephemeral Runners

This guide helps Copilot agents and CI systems run QA checks on ephemeral runners (GitHub Actions, sandboxes, containers) where full project dependencies may not be available.

## Quick Start

The problems reporter is designed to work with minimal setup:

```bash
# 1. Only QA tools need to be installed (not full project dependencies)
pip install mypy ruff yamllint

# 2. Run the problems reporter
python scripts/collect_problems.py --output problems_report.json

# 3. Check results
python -m json.tool problems_report.json | less
```

## Offline Node.js Runtime Support

For environments with restricted internet access, Node.js tooling (markdownlint, biome) can run from cached tarballs:

### Staging Node.js Tarballs

```bash
# Download and verify official Node.js release tarball
python -m scripts.stage_node_tarball --version v20.19.5

# The tarball is staged under artifacts/cache/node/ with checksum verification
# Optionally verify GPG signature (requires gpg in PATH)
python -m scripts.stage_node_tarball --version v20.19.5 --verify-signature
```

The staging script:
- Downloads the official Node.js tarball from nodejs.org
- Verifies SHA256 checksum against SHASUMS256.txt
- Optionally verifies GPG signature for supply-chain security
- Stages the tarball under `artifacts/cache/node/`

### Using Cached Node Runtime

The bootstrap environment automatically detects and validates cached Node.js tarballs:

```bash
# Bootstrap with offline mode (requires pre-staged tarballs)
python -m scripts.bootstrap_env --offline

# The bootstrap will fail if tarballs are missing or invalid
# Run the staging script first to seed the cache
```

When `--offline` is enabled:
- Bootstrap validates the pip wheel cache (`artifacts/cache/pip/`) and fails fast if no wheels or `mirror_state.json` are present
- Playwright browser archives must exist under `artifacts/cache/playwright/` for Chromium, Firefox, and WebKit
- The tldextract suffix cache (`artifacts/cache/tldextract/publicsuffix.org-tlds/`) must contain at least one JSON snapshot
- Node tarballs are verified against `SHASUMS256.txt`; validation failures raise actionable errors
- Dependencies install exclusively from local caches, so seed them before cutting the network cord

### Seeding Offline Caches

Use the wheelhouse downloader to prime the pip cache (defaults to `artifacts/cache/pip/`):

```bash
# Download the latest wheelhouse artifact and stage it into the pip cache
python -m scripts.download_wheelhouse_artifact --seed-pip-cache
```

If your cache lives elsewhere, pass a path (e.g. `--seed-pip-cache /mnt/cache/pip`). The same script continues to support CI usage without the flag when you just need the unpacked wheelhouse directory.

Playwright browsers can be cached ahead of time by running `poetry run playwright install --with-deps`, and tldextract seeds itself during a network-enabled bootstrap or by executing `python -m scripts.bootstrap_env --dry-run` without `--offline`.

### Running QA with Cached Node

```bash
# Run problems collector (includes markdownlint via pre-commit)
poetry run python -m apps.automation.cli qa problems --summary

# Run full QA suite with offline bootstrap
poetry run python -m apps.automation.cli qa all --offline

# Run just linting (includes markdownlint)
poetry run python -m apps.automation.cli qa lint
```

The `qa problems` command aggregates findings from all configured tools including Node-based linters.

## What Works Without Full Dependencies

The problems reporter (`scripts/collect_problems.py`) has several features that make it resilient on ephemeral runners:

### Automatic Stub Configuration

Type checking with mypy automatically works because:
- The script detects the `stubs/` directory in the repository
- MYPYPATH is automatically configured to include both `stubs/` and `stubs/third_party/`
- No manual wrapper scripts or environment setup required

### Graceful Degradation

When project dependencies aren't available:
- The collector skips modules it can't import (e.g., `firecrawl_demo`)
- QA tools run independently without needing project code
- Tools that aren't installed are marked as "not_installed" rather than failing
- Partial results are still useful for triage

### Performance Tracking

Every tool run includes execution time metrics:
- Identify slow tools that may timeout on constrained runners
- Optimize CI time by focusing on bottlenecks
- Compare performance across different runner types

## Understanding the Report

The generated `problems_report.json` includes diagnostic metadata:

```json
{
  "summary": {
    "stubs_available": true,
    "ephemeral_runner_notes": [
      "Type stubs are properly configured for mypy via MYPYPATH"
    ],
    "performance": {
      "total_duration_seconds": 12.456,
      "slowest_tools": [
        {"tool": "mypy", "duration_seconds": 7.123}
      ]
    },
    "tools_run": ["ruff", "mypy", "yamllint"],
    "tools_missing": ["bandit", "trunk"],
    "issue_count": 3,
    "fixable_count": 2
  }
}
```

Key fields for ephemeral environments:

- `stubs_available`: Confirms type stubs are present for accurate type checking
- `ephemeral_runner_notes`: Explains what's configured automatically
- `performance`: Helps identify slow tools that may need caching or optimization
- `tools_missing`: Lists which tools weren't available (informational)
- `issue_count` / `fixable_count`: Quick triage summary

## Tool Requirements

Minimum versions that work well on ephemeral runners:

- **mypy** ≥1.8.0 - Type checking with automatic stub discovery
- **ruff** ≥0.3.0 - Fast linting with JSON output
- **yamllint** ≥1.35.0 - YAML validation
- **bandit** ≥1.7.0 (Python < 3.14 only) - Security scanning
- **trunk** (optional) - Meta-linter aggregator
- **biome** (optional, requires Node.js) - JavaScript/TypeScript linting

## Common Scenarios

### GitHub Actions

```yaml
- name: Run QA checks
  run: |
    pip install mypy ruff yamllint
    python scripts/collect_problems.py
    
    # Fail if there are blocking issues
    if jq -e '.summary.issue_count > 0' problems_report.json; then
      echo "::error::QA issues found"
      exit 1
    fi
```

### Copilot Sandbox

When working in a Copilot sandbox without Poetry:

```bash
# Use system Python
python3 -m pip install --user mypy ruff

# Run collector (works without Poetry wrapper)
python3 scripts/collect_problems.py

# Check specific tool output
jq '.tools[] | select(.tool == "mypy")' problems_report.json
```

### Container/Docker

```dockerfile
FROM python:3.13-slim

# Install QA tools only
RUN pip install --no-cache-dir mypy ruff yamllint

# Copy repository
COPY . /app
WORKDIR /app

# Run QA
RUN python scripts/collect_problems.py && \
    python -c "import json; data=json.load(open('problems_report.json')); exit(0 if data['summary']['issue_count']==0 else 1)"
```

## Troubleshooting

### "No module named 'firecrawl_demo'"

**Expected behavior** - The collector handles this gracefully. It only needs the QA tools, not the project code.

### "MYPYPATH not set"

The collector sets this automatically if the `stubs/` directory exists. If you see false positives from mypy, verify:

```bash
ls -la stubs/third_party/  # Should contain type stub packages
```

### Slow execution times

Check the performance summary:

```bash
jq '.summary.performance.slowest_tools' problems_report.json
```

Consider:
- Using cached tool installs in CI
- Running slow tools (mypy, bandit) only on specific file changes
- Parallel tool execution if supported by CI platform

### Missing tools

The report lists unavailable tools:

```bash
jq '.summary.tools_missing' problems_report.json
```

These are informational - decide which tools are critical for your workflow.

## Integration with CI

The problems reporter is designed to be the canonical QA gate. In `.github/workflows/ci.yml`:

```yaml
- name: Aggregate QA Results
  if: always()  # Run even if earlier steps failed
  run: poetry run python scripts/collect_problems.py
  
- name: Upload Problems Report
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: problems-report
    path: problems_report.json
```

This ensures problems are visible even when earlier QA steps fail.

## Best Practices

1. **Run early and often** - The collector is fast enough to run on every commit
2. **Use performance data** - Optimize slow tools or cache their results
3. **Check stubs availability** - Ensures type checking is accurate
4. **Triage missing tools** - Decide which are required vs. nice-to-have
5. **Automate fixes** - Use `autofix_commands` from the report for quick remediation

## See Also

- [Full Operations Guide](operations.md) - Complete QA workflow
- [Architecture](architecture.md) - Project structure and design
- [Copilot Instructions](../.github/copilot-instructions.md) - Agent-specific guidance
