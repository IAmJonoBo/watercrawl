# Production Readiness Review (PRR)

## Overview

The Production Readiness Review (PRR) is a comprehensive, evidence-backed release validation framework that ensures the Watercrawl system meets production standards before deployment. The PRR aligns with industry best practices and security frameworks:

- **Production Readiness Review (PRR)** framework
- **NIST SSDF** (Secure Software Development Framework)
- **OWASP ASVS v5** (Application Security Verification Standard)
- **SLSA** (Supply-chain Levels for Software Artifacts)
- **OpenSSF Scorecard** security best practices
- **SBOM** minimum elements (SPDX/CycloneDX)

## Running the PRR

### Basic Usage

```bash
# Full PRR with all checks (including optional)
poetry run python -m apps.automation.cli qa prr

# PRR skipping optional checks (recommended for faster validation)
poetry run python -m apps.automation.cli qa prr --skip-optional

# Save PRR report to specific file
poetry run python -m apps.automation.cli qa prr --output artifacts/prr/report.json

# Run PRR without failing on NO-GO (useful for CI reporting)
poetry run python -m apps.automation.cli qa prr --no-fail-on-no-go
```

### Integration with CI/CD

Add PRR to your release pipeline:

```yaml
# .github/workflows/release.yml
- name: Production Readiness Review
  run: |
    poetry run python -m apps.automation.cli qa prr --skip-optional --output artifacts/prr/report.json
  
- name: Upload PRR Evidence
  uses: actions/upload-artifact@v3
  if: always()
  with:
    name: prr-evidence
    path: artifacts/prr/
```

## Check Categories

The PRR validates 8 critical categories:

### 1. Quality & Functionality

Ensures code quality and functional correctness:

- **Unit/Integration/E2E Tests**: Validates test suite is configured and runnable
- **Coverage Thresholds**: Checks for test coverage configuration (optional)
- **Linting Configuration**: Verifies linters (ruff, black, isort) are configured
- **Static Analysis**: Confirms static analysis tools (mypy, bandit) are present

**Pass Criteria**: Tests configured, linters present, static analysis enabled

**Remediation**: Add pytest to dev dependencies, configure ruff/black/isort/mypy in pyproject.toml

### 2. Reliability & Performance

Validates system reliability and performance characteristics:

- **Load/Stress Tests**: Checks for performance test files (optional)
- **SLOs/Error Budgets**: Looks for SLO definitions (optional)
- **Capacity Limits**: Verifies capacity planning documentation (optional)
- **Chaos/DR Tests (RPO/RTO)**: Confirms chaos engineering and disaster recovery tests (optional)

**Pass Criteria**: Performance tests or documentation present (optional checks can be skipped)

**Remediation**: Add performance tests, document SLOs, create capacity planning docs, implement chaos tests

### 3. Security & Privacy

Ensures security posture and privacy compliance:

- **Threat Model**: Validates security documentation exists (SECURITY.md)
- **Secrets/Least Privilege**: Checks for secrets detection tools and secure configuration
- **SAST/DAST/Dependency Scans**: Confirms security scanning tools (bandit, safety, CodeQL)
- **Vulnerability SLAs**: Verifies vulnerability response time commitments
- **Data Protection & Retention**: Checks POPIA/GDPR compliance documentation and modules

**Pass Criteria**: SECURITY.md present, secrets tools configured, SAST/DAST enabled, data protection documented

**Remediation**: Create SECURITY.md with threat model, add detect-secrets to pre-commit hooks, configure bandit/safety, document POPIA compliance

### 4. Supply Chain

Validates supply chain security:

- **SBOM (SPDX/CycloneDX)**: Checks for Software Bill of Materials or dependency lock files
- **Reproducible/Signed Builds**: Verifies build automation (Dockerfile, CI workflows)
- **Provenance Attestation (SLSA)**: Confirms SLSA provenance generation (optional)

**Pass Criteria**: Lock files present (poetry.lock), build automation configured

**Remediation**: Generate SBOM using cyclonedx-python, add Dockerfile, configure SLSA provenance in CI

### 5. Compliance & Licensing

Ensures legal compliance:

- **Third-party License Obligations**: Validates LICENSE file and third-party license tracking

**Pass Criteria**: LICENSE file present

**Remediation**: Add LICENSE file, document third-party licenses

### 6. Observability & Ops

Validates operational readiness:

- **Metrics/Logs/Traces**: Checks for telemetry configuration (OpenTelemetry, Prometheus, structlog)
- **Actionable Alerts**: Verifies alert configurations and tests
- **Runbooks**: Confirms operational runbook documentation (optional)
- **On-call/Rollback**: Validates on-call and rollback procedures (optional)

**Pass Criteria**: Telemetry configured

**Remediation**: Add OpenTelemetry/Prometheus, create alert configurations, write runbooks, document on-call procedures

### 7. Deployment & Change

Ensures safe deployment practices:

- **IaC Validated**: Checks for Infrastructure as Code (Terraform, Dockerfile, K8s)
- **Config Pinned**: Verifies dependency lock files (poetry.lock, package-lock.json)
- **Blue/Green or Canary Plan**: Confirms deployment strategy documentation (optional)
- **Schema/Data Migrations**: Validates migration system (Alembic, etc.) if applicable
- **Feature Flags**: Checks for feature flag implementation

**Pass Criteria**: Lock files present, IaC configured

**Remediation**: Add Dockerfile, pin dependencies with poetry.lock, document deployment strategy, implement feature flags

### 8. Docs & Comms

Ensures adequate documentation:

- **Release Notes**: Validates CHANGELOG.md or release documentation
- **User/Admin Docs**: Checks for README.md and docs/ directory
- **Support Handover**: Verifies support documentation (SUPPORT.md, CONTRIBUTING.md)

**Pass Criteria**: CHANGELOG.md and README.md present

**Remediation**: Create CHANGELOG.md, add comprehensive docs/, write SUPPORT.md

## Go/No-Go Decision

The PRR makes a binary Go/No-Go decision:

### GO Decision

Release is approved when:
- **All critical checks PASS** (no FAIL status)
- Warnings are acceptable (WARN status doesn't block)
- N/A and Skip statuses are documented

**Output**:
```
✓ GO - Release Approved

Release permitted with X warnings.
Review residual risks and consider remediation.
```

### NO-GO Decision

Release is blocked when:
- **One or more critical checks FAIL**
- Critical failures must be remediated before release

**Output**:
```
✗ NO-GO - Release Blocked

Release BLOCKED by X critical failures.
Address all FAIL checks before proceeding to production.
```

## Evidence Bundle

Every PRR run generates an evidence bundle saved to:

```
artifacts/prr/evidence/prr_report_<timestamp>.json
```

The evidence bundle contains:
- All check results with status, proof, and remediation
- Evidence file paths for audit trails
- Metadata for each check
- Timestamp and project information

Example evidence bundle structure:

```json
{
  "project_name": "watercrawl",
  "review_date": "2025-10-24T00:00:00Z",
  "checks": [
    {
      "name": "Unit/Integration/E2E Tests",
      "category": "Quality & Functionality",
      "status": "Pass",
      "proof": "Tests configured in pyproject.toml",
      "remediation": null,
      "evidence_paths": ["tests/", "pyproject.toml"],
      "metadata": {
        "test_count": 50,
        "command": "poetry run pytest -q"
      }
    }
  ]
}
```

## Residual Risk Management

The PRR identifies and tracks residual risks:

### Critical Risks (FAIL status)
- Block release immediately
- Require remediation before deployment
- Example: No SECURITY.md, no LICENSE file

### Warning Risks (WARN status)
- Allow release with documentation
- Should be addressed in follow-up work
- Example: No load tests, missing SBOM

### Risk Documentation

All residual risks are:
1. Listed in the PRR summary output
2. Saved in the evidence bundle
3. Should be tracked in issue tracker
4. Reviewed in post-release retrospective

## Best Practices

### Before Release
1. Run full PRR: `poetry run python -m apps.automation.cli qa prr`
2. Address all FAIL checks
3. Document acceptance of WARN checks
4. Save evidence bundle for compliance
5. Update CHANGELOG.md with fixes

### During Development
1. Run quick PRR: `poetry run python -m apps.automation.cli qa prr --skip-optional`
2. Keep SECURITY.md updated
3. Maintain test coverage
4. Document new features in docs/

### In CI/CD
1. Gate releases on PRR: `qa prr --skip-optional`
2. Upload evidence bundles as artifacts
3. Require manual approval for warnings
4. Block on any failures

### Audit Trail
1. Archive PRR evidence bundles
2. Link to release tags
3. Include in compliance reports
4. Review quarterly for trends

## Troubleshooting

### Common Issues

**Issue**: PRR fails with "No LICENSE file found"
**Solution**: Add LICENSE file to repository root

**Issue**: PRR warns "No SBOM found"
**Solution**: Generate SBOM: `cyclonedx-py -o sbom.json`

**Issue**: PRR fails with "No threat model documentation"
**Solution**: Create SECURITY.md with threat model and security considerations

**Issue**: PRR skips too many checks
**Solution**: Run without `--skip-optional` for comprehensive validation

### Getting Help

- Review this documentation
- Check evidence bundle for specific remediation steps
- Consult CONTRIBUTING.md for setup guidance
- Open issue for PRR framework bugs

## Extending the PRR

To add new checks to the PRR:

1. Identify the category (Quality, Security, etc.)
2. Add check method to `ProductionReadinessReview` class
3. Call from appropriate `_check_*` category method
4. Add unit tests for the new check
5. Document in this file

Example new check:

```python
def _check_api_documentation(self) -> None:
    """Check for API documentation."""
    api_docs = list(self.repo_root.glob("**/openapi*.yaml"))
    
    if api_docs:
        self.checks.append(
            CheckResult(
                name="API Documentation",
                category=CheckCategory.DOCUMENTATION,
                status=CheckStatus.PASS,
                proof=f"Found {len(api_docs)} API spec files",
                evidence_paths=[str(p.relative_to(self.repo_root)) for p in api_docs],
            )
        )
    else:
        self.checks.append(
            CheckResult(
                name="API Documentation",
                category=CheckCategory.DOCUMENTATION,
                status=CheckStatus.WARN,
                proof="No API documentation found",
                remediation="Add OpenAPI/Swagger spec files",
            )
        )
```

## References

- [NIST SSDF](https://csrc.nist.gov/Projects/ssdf) - Secure Software Development Framework
- [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/) - Application Security Verification Standard
- [SLSA](https://slsa.dev/) - Supply-chain Levels for Software Artifacts
- [OpenSSF Scorecard](https://github.com/ossf/scorecard) - Security health metrics
- [SPDX](https://spdx.dev/) - Software Package Data Exchange
- [CycloneDX](https://cyclonedx.org/) - Software Bill of Materials standard
