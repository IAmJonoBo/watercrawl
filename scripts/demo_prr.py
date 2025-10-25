#!/usr/bin/env python3
"""Demo script to show Production Readiness Review functionality.

This script demonstrates the PRR system without requiring all dependencies.
It shows the expected structure and outputs.
"""


def demo_prr():
    """Demonstrate PRR structure and expected output."""
    print("=" * 70)
    print("Production Readiness Review (PRR) - Demo Output")
    print("=" * 70)
    print()
    print("Project: watercrawl")
    print("Review Date: 2025-10-24T00:00:00Z")
    print()

    # Define check categories
    categories = [
        (
            "Quality & Functionality",
            [
                (
                    "Unit/Integration/E2E Tests",
                    "Pass",
                    "Tests configured in pyproject.toml",
                ),
                ("Coverage Thresholds", "Pass", "Coverage tool configured"),
                (
                    "Linting Configuration",
                    "Pass",
                    "Linters configured: ruff, black, isort",
                ),
                (
                    "Static Analysis",
                    "Pass",
                    "Static analysis tools configured: mypy, bandit",
                ),
            ],
        ),
        (
            "Reliability & Performance",
            [
                ("Load/Stress Tests", "Warn", "No performance test files found"),
                ("SLOs/Error Budgets", "Skip", "Skipped (optional check)"),
                ("Capacity Limits", "Skip", "Skipped (optional check)"),
                ("Chaos/DR Tests (RPO/RTO)", "Pass", "Found 1 chaos tests, 0 DR docs"),
            ],
        ),
        (
            "Security & Privacy",
            [
                ("Threat Model", "Pass", "Security/threat documentation found"),
                (
                    "Secrets/Least Privilege",
                    "Pass",
                    "Secrets management tools: .env.example template, bandit",
                ),
                (
                    "SAST/DAST/Dependency Scans",
                    "Pass",
                    "Security scanning tools: bandit (SAST), safety (dependency scan)",
                ),
                (
                    "Vulnerability SLAs",
                    "Pass",
                    "Vulnerability response SLAs documented in SECURITY.md",
                ),
                ("Data Protection & Retention", "Pass", "Found 0 docs, 2 modules"),
            ],
        ),
        (
            "Supply Chain",
            [
                (
                    "SBOM (SPDX/CycloneDX)",
                    "Warn",
                    "Lock files present (poetry.lock) but no SBOM",
                ),
                (
                    "Reproducible/Signed Builds",
                    "Pass",
                    "Build automation found: 2 files",
                ),
                ("Provenance Attestation (SLSA)", "Skip", "Skipped (optional check)"),
            ],
        ),
        (
            "Compliance & Licensing",
            [
                (
                    "Third-party License Obligations",
                    "Pass",
                    "Project license found: 1 files",
                ),
            ],
        ),
        (
            "Observability & Ops",
            [
                (
                    "Metrics/Logs/Traces",
                    "Pass",
                    "Telemetry configured: OpenTelemetry, Prometheus, structlog",
                ),
                ("Actionable Alerts", "Pass", "Found 0 configs, 1 tests"),
                ("Runbooks", "Skip", "Skipped (optional check)"),
                ("On-call/Rollback", "Skip", "Skipped (optional check)"),
            ],
        ),
        (
            "Deployment & Change",
            [
                ("IaC Validated", "Pass", "Found 2 IaC files"),
                (
                    "Config Pinned",
                    "Pass",
                    "Dependencies pinned: poetry.lock, pnpm-lock.yaml",
                ),
                ("Blue/Green or Canary Plan", "Skip", "Skipped (optional check)"),
                (
                    "Schema/Data Migrations",
                    "N/A",
                    "No migration system found (may not be needed)",
                ),
                (
                    "Feature Flags",
                    "Pass",
                    "Feature flags found: 5 files, env_example=yes",
                ),
            ],
        ),
        (
            "Docs & Comms",
            [
                ("Release Notes", "Pass", "Found 1 release documentation files"),
                ("User/Admin Docs", "Pass", "Found 50+ documentation files"),
                ("Support Handover", "Pass", "Found 1 support documentation files"),
            ],
        ),
    ]

    # Print results by category
    for category_name, checks in categories:
        print(f"\n{category_name}")
        print("-" * 70)
        for check_name, status, proof in checks:
            status_symbol = {
                "Pass": "✓",
                "Fail": "✗",
                "Warn": "⚠",
                "N/A": "-",
                "Skip": "⊘",
            }.get(status, "?")

            status_color = {
                "Pass": "\033[92m",  # Green
                "Fail": "\033[91m",  # Red
                "Warn": "\033[93m",  # Yellow
                "N/A": "\033[90m",  # Gray
                "Skip": "\033[90m",  # Gray
            }.get(status, "")

            reset = "\033[0m"

            print(f"  {status_symbol} {status_color}{status:8}{reset} | {check_name}")
            print(f"             {proof}")

    # Summary
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)

    total_checks = sum(len(checks) for _, checks in categories)
    pass_count = sum(
        1 for _, checks in categories for _, status, _ in checks if status == "Pass"
    )
    fail_count = sum(
        1 for _, checks in categories for _, status, _ in checks if status == "Fail"
    )
    warn_count = sum(
        1 for _, checks in categories for _, status, _ in checks if status == "Warn"
    )
    na_count = sum(
        1 for _, checks in categories for _, status, _ in checks if status == "N/A"
    )
    skip_count = sum(
        1 for _, checks in categories for _, status, _ in checks if status == "Skip"
    )

    print(f"  Total Checks: {total_checks}")
    print(f"  \033[92m✓ Pass: {pass_count}\033[0m")
    print(f"  \033[91m✗ Fail: {fail_count}\033[0m")
    print(f"  \033[93m⚠ Warn: {warn_count}\033[0m")
    print(f"  - N/A: {na_count}")
    print(f"  ⊘ Skip: {skip_count}")

    print("\n" + "=" * 70)
    if fail_count == 0:
        print("\033[92m✓ GO - Release Approved\033[0m")
        if warn_count > 0:
            print(f"\nRelease permitted with {warn_count} warnings.")
            print("Review residual risks and consider remediation.")
    else:
        print("\033[91m✗ NO-GO - Release Blocked\033[0m")
        print(f"\nRelease BLOCKED by {fail_count} critical failures.")
        print("Address all FAIL checks before proceeding to production.")

    print("=" * 70)
    print()
    print(
        "Evidence bundle saved: artifacts/prr/evidence/prr_report_20251024T000000Z.json"
    )
    print()

    # Show example usage
    print("=" * 70)
    print("Usage Examples")
    print("=" * 70)
    print()
    print("# Run full PRR (includes optional checks)")
    print("poetry run python -m apps.automation.cli qa prr")
    print()
    print("# Run PRR skipping optional checks (faster)")
    print("poetry run python -m apps.automation.cli qa prr --skip-optional")
    print()
    print("# Save report to specific file")
    print(
        "poetry run python -m apps.automation.cli qa prr --output artifacts/prr/report.json"
    )
    print()
    print("# Run PRR without failing on NO-GO (for CI reporting)")
    print("poetry run python -m apps.automation.cli qa prr --no-fail-on-no-go")
    print()


if __name__ == "__main__":
    demo_prr()
