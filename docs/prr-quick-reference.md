# Production Readiness Review (PRR) - Quick Reference

## Quick Start

```bash
# Run PRR (recommended for releases)
poetry run python -m apps.automation.cli qa prr --skip-optional

# Full PRR with all checks
poetry run python -m apps.automation.cli qa prr

# Save evidence bundle
poetry run python -m apps.automation.cli qa prr --output artifacts/prr/report.json
```

## Check Categories

| Category | Checks | Critical? |
|----------|--------|-----------|
| **Quality & Functionality** | Tests, Coverage, Lint, Static Analysis | ✓ Yes |
| **Reliability & Performance** | Load Tests, SLOs, Capacity, Chaos/DR | Optional |
| **Security & Privacy** | Threat Model, Secrets, SAST/DAST, Vulnerabilities | ✓ Yes |
| **Supply Chain** | SBOM, Reproducible Builds, Provenance | Partial |
| **Compliance & Licensing** | License Files | ✓ Yes |
| **Observability & Ops** | Metrics, Logs, Alerts, Runbooks | Partial |
| **Deployment & Change** | IaC, Config Pinning, Feature Flags | ✓ Yes |
| **Docs & Comms** | Release Notes, User Docs, Support | ✓ Yes |

## Status Legend

| Symbol | Status | Meaning |
|--------|--------|---------|
| ✓ | Pass | Check passed, requirement met |
| ✗ | Fail | Critical failure, blocks release |
| ⚠ | Warn | Warning, doesn't block but should address |
| - | N/A | Not applicable to this project |
| ⊘ | Skip | Skipped (optional check not run) |

## Go/No-Go Decision

**GO** - Release approved when:
- Zero FAIL checks
- Warnings documented and accepted

**NO-GO** - Release blocked when:
- One or more FAIL checks
- Must remediate before release

## Common Remediations

### FAIL: No SECURITY.md
```bash
# Create threat model documentation
touch SECURITY.md
# Add: Threat model, vulnerability reporting, security policies
```

### FAIL: No LICENSE
```bash
# Add license file
touch LICENSE
# Copy appropriate license text (MIT, Apache, etc.)
```

### WARN: No SBOM
```bash
# Generate SBOM from poetry.lock
pip install cyclonedx-bom
cyclonedx-py -o sbom.json
```

### WARN: No load tests
```bash
# Create performance tests
touch tests/test_performance.py
# Add: Load/stress test cases
```

## CI/CD Integration

### GitHub Actions
```yaml
- name: Production Readiness Review
  run: poetry run python -m apps.automation.cli qa prr --skip-optional
```

### GitLab CI
```yaml
prr:
  script:
    - poetry run python -m apps.automation.cli qa prr --skip-optional
  artifacts:
    paths:
      - artifacts/prr/
```

## Evidence Bundle Location

All PRR runs save evidence to:
```
artifacts/prr/evidence/prr_report_<timestamp>.json
```

## Getting Help

- Full docs: `docs/production-readiness-review.md`
- Implementation summary: `docs/closeout-implementation-summary.md`
- Demo output: `python3 scripts/demo_prr.py`
- Contributing guide: `CONTRIBUTING.md`

## Quick Checklist

Before running PRR, ensure:

- [ ] Tests are passing: `poetry run pytest -q`
- [ ] Linters clean: `poetry run ruff check .`
- [ ] Type checks pass: `poetry run mypy .`
- [ ] CHANGELOG.md updated
- [ ] README.md current
- [ ] SECURITY.md exists
- [ ] LICENSE file present
- [ ] Dependencies pinned (poetry.lock)

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | GO decision - release approved |
| 1 | NO-GO decision - release blocked |

Use `--no-fail-on-no-go` to always exit 0 (useful for reporting).

## Framework Alignment

✓ PRR (Production Readiness Review)
✓ NIST SSDF (Secure Software Development)
✓ OWASP ASVS v5 (Application Security Verification)
✓ SLSA (Supply-chain Levels)
✓ SBOM (Software Bill of Materials)
✓ OpenSSF Scorecard (Security best practices)
