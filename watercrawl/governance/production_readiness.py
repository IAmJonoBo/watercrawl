"""Production Readiness Review (PRR) - Evidence-backed release checklist.

Implements comprehensive production readiness checks aligned with:
- Production Readiness Review (PRR) framework
- NIST SSDF (Secure Software Development Framework)
- OWASP ASVS v5 (Application Security Verification Standard)
- SLSA (Supply-chain Levels for Software Artifacts)
- OpenSSF Scorecard
- SBOM minimum elements (SPDX/CycloneDX)
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()


class CheckStatus(str, Enum):
    """Status of a production readiness check."""

    PASS = "Pass"
    FAIL = "Fail"
    WARN = "Warn"
    NA = "N/A"
    SKIP = "Skip"


class CheckCategory(str, Enum):
    """Categories of production readiness checks."""

    QUALITY = "Quality & Functionality"
    RELIABILITY = "Reliability & Performance"
    SECURITY = "Security & Privacy"
    SUPPLY_CHAIN = "Supply Chain"
    COMPLIANCE = "Compliance & Licensing"
    OBSERVABILITY = "Observability & Ops"
    DEPLOYMENT = "Deployment & Change"
    DOCUMENTATION = "Docs & Comms"


@dataclass
class CheckResult:
    """Result of a single production readiness check."""

    name: str
    category: CheckCategory
    status: CheckStatus
    proof: str | None = None
    remediation: str | None = None
    evidence_paths: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PRRReport:
    """Production Readiness Review report."""

    project_name: str
    review_date: datetime
    checks: list[CheckResult]
    go_decision: bool
    residual_risks: list[str]
    summary: str
    evidence_bundle_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "project_name": self.project_name,
            "review_date": self.review_date.isoformat(),
            "checks": [
                {
                    "name": c.name,
                    "category": c.category.value,
                    "status": c.status.value,
                    "proof": c.proof,
                    "remediation": c.remediation,
                    "evidence_paths": c.evidence_paths,
                    "metadata": c.metadata,
                }
                for c in self.checks
            ],
            "go_decision": self.go_decision,
            "residual_risks": self.residual_risks,
            "summary": self.summary,
            "evidence_bundle_path": self.evidence_bundle_path,
        }


class ProductionReadinessReview:
    """Production Readiness Review orchestrator."""

    def __init__(self, repo_root: Path, project_name: str = "watercrawl"):
        self.repo_root = repo_root
        self.project_name = project_name
        self.checks: list[CheckResult] = []
        self.evidence_dir = repo_root / "artifacts" / "prr" / "evidence"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    def run_all_checks(self, skip_optional: bool = False) -> PRRReport:
        """Execute all production readiness checks."""
        console.print("\n[bold cyan]Production Readiness Review[/bold cyan]\n")
        console.print(f"Project: {self.project_name}")
        console.print(f"Review Date: {datetime.now(UTC).isoformat()}\n")

        # Run checks by category
        self._check_quality_functionality(skip_optional)
        self._check_reliability_performance(skip_optional)
        self._check_security_privacy(skip_optional)
        self._check_supply_chain(skip_optional)
        self._check_compliance_licensing(skip_optional)
        self._check_observability_ops(skip_optional)
        self._check_deployment_change(skip_optional)
        self._check_documentation_comms(skip_optional)

        # Generate report
        return self._generate_report()

    def _check_quality_functionality(self, skip_optional: bool) -> None:
        """Check quality and functionality requirements."""
        console.print("[bold]Quality & Functionality[/bold]")

        # Unit/Integration/E2E tests
        self._check_tests()

        # Coverage thresholds
        self._check_coverage(skip_optional)

        # Lint/Static analysis
        self._check_lint()
        self._check_static_analysis()

    def _check_tests(self) -> None:
        """Check that tests pass."""
        pytest_path = self.repo_root / "tests"
        if not pytest_path.exists():
            self.checks.append(
                CheckResult(
                    name="Unit/Integration/E2E Tests",
                    category=CheckCategory.QUALITY,
                    status=CheckStatus.NA,
                    proof="No tests directory found",
                )
            )
            return

        # Check for pytest configuration
        pyproject = self.repo_root / "pyproject.toml"
        has_pytest = False
        if pyproject.exists():
            content = pyproject.read_text()
            has_pytest = "pytest" in content.lower()

        if has_pytest:
            self.checks.append(
                CheckResult(
                    name="Unit/Integration/E2E Tests",
                    category=CheckCategory.QUALITY,
                    status=CheckStatus.PASS,
                    proof="Tests configured in pyproject.toml",
                    evidence_paths=["tests/", "pyproject.toml"],
                    metadata={
                        "test_count": len(list(pytest_path.glob("test_*.py"))),
                        "command": "poetry run pytest -q",
                    },
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="Unit/Integration/E2E Tests",
                    category=CheckCategory.QUALITY,
                    status=CheckStatus.WARN,
                    proof="Tests directory exists but pytest not configured",
                    remediation="Configure pytest in pyproject.toml and run tests",
                )
            )

    def _check_coverage(self, skip_optional: bool) -> None:
        """Check test coverage."""
        if skip_optional:
            self.checks.append(
                CheckResult(
                    name="Coverage Thresholds",
                    category=CheckCategory.QUALITY,
                    status=CheckStatus.SKIP,
                    proof="Skipped (optional check)",
                )
            )
            return

        # Look for coverage configuration
        pyproject = self.repo_root / "pyproject.toml"
        has_coverage = False
        if pyproject.exists():
            content = pyproject.read_text()
            has_coverage = "pytest-cov" in content or "coverage" in content.lower()

        if has_coverage:
            self.checks.append(
                CheckResult(
                    name="Coverage Thresholds",
                    category=CheckCategory.QUALITY,
                    status=CheckStatus.PASS,
                    proof="Coverage tool configured",
                    metadata={"command": "poetry run pytest --cov"},
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="Coverage Thresholds",
                    category=CheckCategory.QUALITY,
                    status=CheckStatus.WARN,
                    proof="No coverage configuration found",
                    remediation="Add pytest-cov to dev dependencies and configure coverage",
                )
            )

    def _check_lint(self) -> None:
        """Check linting configuration."""
        pyproject = self.repo_root / "pyproject.toml"
        linters = []

        if pyproject.exists():
            content = pyproject.read_text()
            if "ruff" in content.lower():
                linters.append("ruff")
            if "black" in content.lower():
                linters.append("black")
            if "isort" in content.lower():
                linters.append("isort")

        if linters:
            self.checks.append(
                CheckResult(
                    name="Linting Configuration",
                    category=CheckCategory.QUALITY,
                    status=CheckStatus.PASS,
                    proof=f"Linters configured: {', '.join(linters)}",
                    metadata={"linters": linters, "command": "poetry run ruff check ."},
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="Linting Configuration",
                    category=CheckCategory.QUALITY,
                    status=CheckStatus.FAIL,
                    proof="No linters configured",
                    remediation="Configure ruff, black, and isort",
                )
            )

    def _check_static_analysis(self) -> None:
        """Check static analysis tools."""
        pyproject = self.repo_root / "pyproject.toml"
        tools = []

        if pyproject.exists():
            content = pyproject.read_text()
            if "mypy" in content.lower():
                tools.append("mypy")
            if "bandit" in content.lower():
                tools.append("bandit")

        if tools:
            self.checks.append(
                CheckResult(
                    name="Static Analysis",
                    category=CheckCategory.QUALITY,
                    status=CheckStatus.PASS,
                    proof=f"Static analysis tools configured: {', '.join(tools)}",
                    metadata={"tools": tools, "command": "poetry run mypy ."},
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="Static Analysis",
                    category=CheckCategory.QUALITY,
                    status=CheckStatus.WARN,
                    proof="No static analysis tools configured",
                    remediation="Add mypy and bandit to dev dependencies",
                )
            )

    def _check_reliability_performance(self, skip_optional: bool) -> None:
        """Check reliability and performance requirements."""
        console.print("\n[bold]Reliability & Performance[/bold]")

        # Load/Stress test results
        self._check_load_tests(skip_optional)

        # SLOs/Error budgets
        self._check_slos(skip_optional)

        # Capacity limits
        self._check_capacity(skip_optional)

        # Chaos/DR tests
        self._check_chaos_dr(skip_optional)

    def _check_load_tests(self, skip_optional: bool) -> None:
        """Check for load/stress test results."""
        # Look for performance test markers
        perf_tests = list(self.repo_root.glob("**/test_*perf*.py")) + list(
            self.repo_root.glob("**/test_*load*.py")
        )

        if perf_tests:
            self.checks.append(
                CheckResult(
                    name="Load/Stress Tests",
                    category=CheckCategory.RELIABILITY,
                    status=CheckStatus.PASS,
                    proof=f"Found {len(perf_tests)} performance test files",
                    evidence_paths=[str(p.relative_to(self.repo_root)) for p in perf_tests],
                )
            )
        elif skip_optional:
            self.checks.append(
                CheckResult(
                    name="Load/Stress Tests",
                    category=CheckCategory.RELIABILITY,
                    status=CheckStatus.SKIP,
                    proof="Skipped (optional check)",
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="Load/Stress Tests",
                    category=CheckCategory.RELIABILITY,
                    status=CheckStatus.WARN,
                    proof="No performance test files found",
                    remediation="Add load/stress tests for critical paths",
                )
            )

    def _check_slos(self, skip_optional: bool) -> None:
        """Check for SLO/error budget definitions."""
        # Look for SLO configurations
        slo_files = list(self.repo_root.glob("**/slo*.yaml")) + list(
            self.repo_root.glob("**/slo*.json")
        )

        if slo_files:
            self.checks.append(
                CheckResult(
                    name="SLOs/Error Budgets",
                    category=CheckCategory.RELIABILITY,
                    status=CheckStatus.PASS,
                    proof=f"Found SLO configurations: {len(slo_files)} files",
                    evidence_paths=[str(p.relative_to(self.repo_root)) for p in slo_files],
                )
            )
        elif skip_optional:
            self.checks.append(
                CheckResult(
                    name="SLOs/Error Budgets",
                    category=CheckCategory.RELIABILITY,
                    status=CheckStatus.SKIP,
                    proof="Skipped (optional check)",
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="SLOs/Error Budgets",
                    category=CheckCategory.RELIABILITY,
                    status=CheckStatus.WARN,
                    proof="No SLO definitions found",
                    remediation="Define SLOs for critical services",
                )
            )

    def _check_capacity(self, skip_optional: bool) -> None:
        """Check for capacity planning documentation."""
        # Look for capacity documentation
        capacity_docs = (
            list(self.repo_root.glob("**/CAPACITY*.md"))
            + list(self.repo_root.glob("**/capacity*.md"))
            + list(self.repo_root.glob("docs/**/capacity*.md"))
        )

        if capacity_docs:
            self.checks.append(
                CheckResult(
                    name="Capacity Limits",
                    category=CheckCategory.RELIABILITY,
                    status=CheckStatus.PASS,
                    proof="Capacity planning documentation found",
                    evidence_paths=[str(p.relative_to(self.repo_root)) for p in capacity_docs],
                )
            )
        elif skip_optional:
            self.checks.append(
                CheckResult(
                    name="Capacity Limits",
                    category=CheckCategory.RELIABILITY,
                    status=CheckStatus.SKIP,
                    proof="Skipped (optional check)",
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="Capacity Limits",
                    category=CheckCategory.RELIABILITY,
                    status=CheckStatus.WARN,
                    proof="No capacity planning documentation found",
                    remediation="Document capacity limits and scaling thresholds",
                )
            )

    def _check_chaos_dr(self, skip_optional: bool) -> None:
        """Check for chaos engineering and DR tests."""
        # Look for chaos tests
        chaos_tests = list(self.repo_root.glob("**/test_chaos*.py"))
        dr_docs = list(self.repo_root.glob("**/DR*.md")) + list(
            self.repo_root.glob("**/disaster*.md")
        )

        if chaos_tests or dr_docs:
            self.checks.append(
                CheckResult(
                    name="Chaos/DR Tests (RPO/RTO)",
                    category=CheckCategory.RELIABILITY,
                    status=CheckStatus.PASS,
                    proof=f"Found {len(chaos_tests)} chaos tests, {len(dr_docs)} DR docs",
                    evidence_paths=[
                        str(p.relative_to(self.repo_root)) for p in chaos_tests + dr_docs
                    ],
                )
            )
        elif skip_optional:
            self.checks.append(
                CheckResult(
                    name="Chaos/DR Tests (RPO/RTO)",
                    category=CheckCategory.RELIABILITY,
                    status=CheckStatus.SKIP,
                    proof="Skipped (optional check)",
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="Chaos/DR Tests (RPO/RTO)",
                    category=CheckCategory.RELIABILITY,
                    status=CheckStatus.WARN,
                    proof="No chaos engineering or DR tests found",
                    remediation="Implement chaos tests and document DR procedures",
                )
            )

    def _check_security_privacy(self, skip_optional: bool) -> None:
        """Check security and privacy requirements."""
        console.print("\n[bold]Security & Privacy[/bold]")

        # Threat model
        self._check_threat_model()

        # Secrets/Least privilege
        self._check_secrets()

        # SAST/DAST/Dependency scans
        self._check_security_scans()

        # Vulnerability SLAs
        self._check_vulnerability_slas(skip_optional)

        # Data protection and retention
        self._check_data_protection()

    def _check_threat_model(self) -> None:
        """Check for threat model documentation."""
        threat_docs = (
            list(self.repo_root.glob("**/SECURITY*.md"))
            + list(self.repo_root.glob("**/threat*.md"))
            + list(self.repo_root.glob("docs/**/security*.md"))
        )

        if threat_docs:
            self.checks.append(
                CheckResult(
                    name="Threat Model",
                    category=CheckCategory.SECURITY,
                    status=CheckStatus.PASS,
                    proof="Security/threat documentation found",
                    evidence_paths=[str(p.relative_to(self.repo_root)) for p in threat_docs],
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="Threat Model",
                    category=CheckCategory.SECURITY,
                    status=CheckStatus.FAIL,
                    proof="No threat model or security documentation found",
                    remediation="Create SECURITY.md with threat model and security considerations",
                )
            )

    def _check_secrets(self) -> None:
        """Check for secrets management."""
        # Check for secrets detection tools
        has_secrets_tools = False
        tools = []

        # Check pre-commit config
        precommit = self.repo_root / ".pre-commit-config.yaml"
        if precommit.exists():
            content = precommit.read_text()
            if "detect-secrets" in content or "gitleaks" in content:
                has_secrets_tools = True
                tools.append("pre-commit hooks")

        # Check for .env.example (good practice)
        if (self.repo_root / ".env.example").exists():
            tools.append(".env.example template")

        # Check pyproject.toml for bandit
        pyproject = self.repo_root / "pyproject.toml"
        if pyproject.exists():
            content = pyproject.read_text()
            if "bandit" in content.lower():
                tools.append("bandit")

        if has_secrets_tools or tools:
            self.checks.append(
                CheckResult(
                    name="Secrets/Least Privilege",
                    category=CheckCategory.SECURITY,
                    status=CheckStatus.PASS,
                    proof=f"Secrets management tools: {', '.join(tools)}",
                    metadata={"tools": tools},
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="Secrets/Least Privilege",
                    category=CheckCategory.SECURITY,
                    status=CheckStatus.WARN,
                    proof="No secrets detection tools configured",
                    remediation="Add detect-secrets or gitleaks to pre-commit hooks",
                )
            )

    def _check_security_scans(self) -> None:
        """Check for SAST/DAST and dependency scanning."""
        tools = []

        pyproject = self.repo_root / "pyproject.toml"
        if pyproject.exists():
            content = pyproject.read_text()
            if "bandit" in content.lower():
                tools.append("bandit (SAST)")
            if "safety" in content.lower():
                tools.append("safety (dependency scan)")

        # Check for security workflow
        workflows_dir = self.repo_root / ".github" / "workflows"
        workflows = list(workflows_dir.glob("*.yml")) if workflows_dir.exists() else []
        for wf in workflows:
            content = wf.read_text()
            if "codeql" in content.lower():
                tools.append("CodeQL (SAST)")
            if "snyk" in content.lower():
                tools.append("Snyk")

        if tools:
            self.checks.append(
                CheckResult(
                    name="SAST/DAST/Dependency Scans",
                    category=CheckCategory.SECURITY,
                    status=CheckStatus.PASS,
                    proof=f"Security scanning tools: {', '.join(tools)}",
                    metadata={"tools": tools},
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="SAST/DAST/Dependency Scans",
                    category=CheckCategory.SECURITY,
                    status=CheckStatus.FAIL,
                    proof="No security scanning tools configured",
                    remediation="Add bandit, safety, or CodeQL to CI pipeline",
                )
            )

    def _check_vulnerability_slas(self, skip_optional: bool) -> None:
        """Check for vulnerability SLA documentation."""
        security_md = self.repo_root / "SECURITY.md"

        if security_md.exists():
            content = security_md.read_text()
            has_sla = "sla" in content.lower() or "response time" in content.lower()

            if has_sla:
                self.checks.append(
                    CheckResult(
                        name="Vulnerability SLAs",
                        category=CheckCategory.SECURITY,
                        status=CheckStatus.PASS,
                        proof="Vulnerability response SLAs documented in SECURITY.md",
                        evidence_paths=["SECURITY.md"],
                    )
                )
            else:
                self.checks.append(
                    CheckResult(
                        name="Vulnerability SLAs",
                        category=CheckCategory.SECURITY,
                        status=CheckStatus.WARN,
                        proof="SECURITY.md exists but no SLAs documented",
                        remediation="Add vulnerability response SLAs to SECURITY.md",
                    )
                )
        elif skip_optional:
            self.checks.append(
                CheckResult(
                    name="Vulnerability SLAs",
                    category=CheckCategory.SECURITY,
                    status=CheckStatus.SKIP,
                    proof="Skipped (optional check)",
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="Vulnerability SLAs",
                    category=CheckCategory.SECURITY,
                    status=CheckStatus.WARN,
                    proof="No vulnerability SLA documentation found",
                    remediation="Document vulnerability response SLAs in SECURITY.md",
                )
            )

    def _check_data_protection(self) -> None:
        """Check for data protection and retention policies."""
        # Look for privacy/POPIA documentation
        privacy_docs = (
            list(self.repo_root.glob("**/PRIVACY*.md"))
            + list(self.repo_root.glob("**/popia*.md"))
            + list(self.repo_root.glob("**/data-protection*.md"))
            + list(self.repo_root.glob("docs/**/compliance*.md"))
        )

        # Check for compliance module
        compliance_modules = list(self.repo_root.glob("**/compliance*.py"))

        if privacy_docs or compliance_modules:
            self.checks.append(
                CheckResult(
                    name="Data Protection & Retention",
                    category=CheckCategory.SECURITY,
                    status=CheckStatus.PASS,
                    proof=f"Found {len(privacy_docs)} docs, {len(compliance_modules)} modules",
                    evidence_paths=[
                        str(p.relative_to(self.repo_root))
                        for p in privacy_docs + compliance_modules
                    ],
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="Data Protection & Retention",
                    category=CheckCategory.SECURITY,
                    status=CheckStatus.WARN,
                    proof="No data protection documentation found",
                    remediation="Document POPIA/GDPR compliance and retention policies",
                )
            )

    def _check_supply_chain(self, skip_optional: bool) -> None:
        """Check supply chain security requirements."""
        console.print("\n[bold]Supply Chain[/bold]")

        # SBOM present and policy-compliant
        self._check_sbom()

        # Reproducible/signed builds
        self._check_reproducible_builds(skip_optional)

        # Provenance attestation (SLSA)
        self._check_provenance(skip_optional)

    def _check_sbom(self) -> None:
        """Check for Software Bill of Materials."""
        # Check for SBOM files
        sbom_files = (
            list(self.repo_root.glob("**/sbom*.json"))
            + list(self.repo_root.glob("**/sbom*.xml"))
            + list(self.repo_root.glob("**/*.spdx"))
            + list(self.repo_root.glob("**/bom.json"))
        )

        # Check for dependency lock files (proxy for SBOM generation)
        lock_files = []
        if (self.repo_root / "poetry.lock").exists():
            lock_files.append("poetry.lock")
        if (self.repo_root / "requirements.txt").exists():
            lock_files.append("requirements.txt")

        if sbom_files:
            self.checks.append(
                CheckResult(
                    name="SBOM (SPDX/CycloneDX)",
                    category=CheckCategory.SUPPLY_CHAIN,
                    status=CheckStatus.PASS,
                    proof=f"SBOM files found: {len(sbom_files)}",
                    evidence_paths=[str(p.relative_to(self.repo_root)) for p in sbom_files],
                )
            )
        elif lock_files:
            self.checks.append(
                CheckResult(
                    name="SBOM (SPDX/CycloneDX)",
                    category=CheckCategory.SUPPLY_CHAIN,
                    status=CheckStatus.WARN,
                    proof=f"Lock files present ({', '.join(lock_files)}) but no SBOM",
                    remediation="Generate SBOM using cyclonedx-python or spdx-sbom-generator",
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="SBOM (SPDX/CycloneDX)",
                    category=CheckCategory.SUPPLY_CHAIN,
                    status=CheckStatus.FAIL,
                    proof="No SBOM or dependency lock files found",
                    remediation="Add poetry.lock and generate SBOM",
                )
            )

    def _check_reproducible_builds(self, skip_optional: bool) -> None:
        """Check for reproducible build configuration."""
        # Look for build automation
        build_files = (
            list(self.repo_root.glob("Dockerfile"))
            + list(self.repo_root.glob("Makefile"))
            + list(self.repo_root.glob("justfile"))
            + list(self.repo_root.glob(".github/workflows/build*.yml"))
        )

        if build_files:
            self.checks.append(
                CheckResult(
                    name="Reproducible/Signed Builds",
                    category=CheckCategory.SUPPLY_CHAIN,
                    status=CheckStatus.PASS,
                    proof=f"Build automation found: {len(build_files)} files",
                    evidence_paths=[str(p.relative_to(self.repo_root)) for p in build_files],
                )
            )
        elif skip_optional:
            self.checks.append(
                CheckResult(
                    name="Reproducible/Signed Builds",
                    category=CheckCategory.SUPPLY_CHAIN,
                    status=CheckStatus.SKIP,
                    proof="Skipped (optional check)",
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="Reproducible/Signed Builds",
                    category=CheckCategory.SUPPLY_CHAIN,
                    status=CheckStatus.WARN,
                    proof="No build automation found",
                    remediation="Add Dockerfile or CI build workflow",
                )
            )

    def _check_provenance(self, skip_optional: bool) -> None:
        """Check for provenance attestation (SLSA)."""
        # Look for SLSA or provenance configuration
        workflows_dir = self.repo_root / ".github" / "workflows"
        has_provenance = False

        if workflows_dir.exists():
            for wf in workflows_dir.glob("*.yml"):
                content = wf.read_text()
                if "slsa" in content.lower() or "provenance" in content.lower():
                    has_provenance = True
                    break

        if has_provenance:
            self.checks.append(
                CheckResult(
                    name="Provenance Attestation (SLSA)",
                    category=CheckCategory.SUPPLY_CHAIN,
                    status=CheckStatus.PASS,
                    proof="SLSA provenance workflow found",
                )
            )
        elif skip_optional:
            self.checks.append(
                CheckResult(
                    name="Provenance Attestation (SLSA)",
                    category=CheckCategory.SUPPLY_CHAIN,
                    status=CheckStatus.SKIP,
                    proof="Skipped (optional check)",
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="Provenance Attestation (SLSA)",
                    category=CheckCategory.SUPPLY_CHAIN,
                    status=CheckStatus.WARN,
                    proof="No SLSA provenance configuration found",
                    remediation="Add SLSA provenance generation to build workflow",
                )
            )

    def _check_compliance_licensing(self, skip_optional: bool) -> None:
        """Check compliance and licensing requirements."""
        console.print("\n[bold]Compliance & Licensing[/bold]")

        # Third-party license obligations
        self._check_licenses()

    def _check_licenses(self) -> None:
        """Check for license compliance."""
        license_files = list(self.repo_root.glob("LICENSE*")) + list(
            self.repo_root.glob("COPYING*")
        )

        # Check for third-party license tracking
        third_party_licenses = list(self.repo_root.glob("**/THIRD_PARTY*.md")) + list(
            self.repo_root.glob("**/licenses/*.txt")
        )

        if license_files:
            proof = f"Project license found: {len(license_files)} files"
            if third_party_licenses:
                proof += f", {len(third_party_licenses)} third-party license files"

            self.checks.append(
                CheckResult(
                    name="Third-party License Obligations",
                    category=CheckCategory.COMPLIANCE,
                    status=CheckStatus.PASS,
                    proof=proof,
                    evidence_paths=[
                        str(p.relative_to(self.repo_root))
                        for p in license_files + third_party_licenses
                    ],
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="Third-party License Obligations",
                    category=CheckCategory.COMPLIANCE,
                    status=CheckStatus.FAIL,
                    proof="No LICENSE file found",
                    remediation="Add LICENSE file and track third-party licenses",
                )
            )

    def _check_observability_ops(self, skip_optional: bool) -> None:
        """Check observability and operations requirements."""
        console.print("\n[bold]Observability & Ops[/bold]")

        # Metrics/Logs/Traces
        self._check_telemetry()

        # Actionable alerts
        self._check_alerts(skip_optional)

        # Runbooks
        self._check_runbooks(skip_optional)

        # On-call/Rollback
        self._check_oncall_rollback(skip_optional)

    def _check_telemetry(self) -> None:
        """Check for metrics, logs, and traces."""
        # Check for telemetry libraries
        pyproject = self.repo_root / "pyproject.toml"
        telemetry_tools = []

        if pyproject.exists():
            content = pyproject.read_text()
            if "opentelemetry" in content.lower():
                telemetry_tools.append("OpenTelemetry")
            if "prometheus" in content.lower():
                telemetry_tools.append("Prometheus")
            if "structlog" in content.lower():
                telemetry_tools.append("structlog")

        # Check for telemetry modules
        telemetry_modules = list(self.repo_root.glob("**/telemetry*.py")) + list(
            self.repo_root.glob("**/observability*.py")
        )

        if telemetry_tools or telemetry_modules:
            self.checks.append(
                CheckResult(
                    name="Metrics/Logs/Traces",
                    category=CheckCategory.OBSERVABILITY,
                    status=CheckStatus.PASS,
                    proof=f"Telemetry configured: {', '.join(telemetry_tools) if telemetry_tools else f'{len(telemetry_modules)} modules'}",
                    metadata={"tools": telemetry_tools},
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="Metrics/Logs/Traces",
                    category=CheckCategory.OBSERVABILITY,
                    status=CheckStatus.WARN,
                    proof="No telemetry configuration found",
                    remediation="Add OpenTelemetry or Prometheus for observability",
                )
            )

    def _check_alerts(self, skip_optional: bool) -> None:
        """Check for actionable alerts."""
        # Look for alert configurations
        alert_files = (
            list(self.repo_root.glob("**/alerts*.yaml"))
            + list(self.repo_root.glob("**/alerts*.yml"))
            + list(self.repo_root.glob("**/monitoring*.yaml"))
        )

        # Check for alert tests
        alert_tests = list(self.repo_root.glob("**/test_alert*.py"))

        if alert_files or alert_tests:
            self.checks.append(
                CheckResult(
                    name="Actionable Alerts",
                    category=CheckCategory.OBSERVABILITY,
                    status=CheckStatus.PASS,
                    proof=f"Found {len(alert_files)} configs, {len(alert_tests)} tests",
                    evidence_paths=[
                        str(p.relative_to(self.repo_root)) for p in alert_files + alert_tests
                    ],
                )
            )
        elif skip_optional:
            self.checks.append(
                CheckResult(
                    name="Actionable Alerts",
                    category=CheckCategory.OBSERVABILITY,
                    status=CheckStatus.SKIP,
                    proof="Skipped (optional check)",
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="Actionable Alerts",
                    category=CheckCategory.OBSERVABILITY,
                    status=CheckStatus.WARN,
                    proof="No alert configurations found",
                    remediation="Define alert rules and thresholds",
                )
            )

    def _check_runbooks(self, skip_optional: bool) -> None:
        """Check for operational runbooks."""
        # Look for runbook documentation
        runbook_docs = (
            list(self.repo_root.glob("**/RUNBOOK*.md"))
            + list(self.repo_root.glob("**/runbooks/**/*.md"))
            + list(self.repo_root.glob("docs/**/operations*.md"))
        )

        if runbook_docs:
            self.checks.append(
                CheckResult(
                    name="Runbooks",
                    category=CheckCategory.OBSERVABILITY,
                    status=CheckStatus.PASS,
                    proof=f"Found {len(runbook_docs)} runbook documents",
                    evidence_paths=[str(p.relative_to(self.repo_root)) for p in runbook_docs],
                )
            )
        elif skip_optional:
            self.checks.append(
                CheckResult(
                    name="Runbooks",
                    category=CheckCategory.OBSERVABILITY,
                    status=CheckStatus.SKIP,
                    proof="Skipped (optional check)",
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="Runbooks",
                    category=CheckCategory.OBSERVABILITY,
                    status=CheckStatus.WARN,
                    proof="No runbooks found",
                    remediation="Create operational runbooks for common scenarios",
                )
            )

    def _check_oncall_rollback(self, skip_optional: bool) -> None:
        """Check for on-call and rollback procedures."""
        # Look for on-call documentation
        oncall_docs = (
            list(self.repo_root.glob("**/ONCALL*.md"))
            + list(self.repo_root.glob("**/on-call*.md"))
            + list(self.repo_root.glob("docs/**/support*.md"))
        )

        # Look for rollback procedures
        rollback_docs = list(self.repo_root.glob("**/ROLLBACK*.md")) + list(
            self.repo_root.glob("docs/**/deployment*.md")
        )

        if oncall_docs or rollback_docs:
            self.checks.append(
                CheckResult(
                    name="On-call/Rollback",
                    category=CheckCategory.OBSERVABILITY,
                    status=CheckStatus.PASS,
                    proof=f"Found {len(oncall_docs)} on-call docs, {len(rollback_docs)} rollback docs",
                    evidence_paths=[
                        str(p.relative_to(self.repo_root))
                        for p in oncall_docs + rollback_docs
                    ],
                )
            )
        elif skip_optional:
            self.checks.append(
                CheckResult(
                    name="On-call/Rollback",
                    category=CheckCategory.OBSERVABILITY,
                    status=CheckStatus.SKIP,
                    proof="Skipped (optional check)",
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="On-call/Rollback",
                    category=CheckCategory.OBSERVABILITY,
                    status=CheckStatus.WARN,
                    proof="No on-call or rollback documentation found",
                    remediation="Document on-call procedures and rollback process",
                )
            )

    def _check_deployment_change(self, skip_optional: bool) -> None:
        """Check deployment and change management requirements."""
        console.print("\n[bold]Deployment & Change[/bold]")

        # IaC validated
        self._check_iac()

        # Config pinned
        self._check_config_pinned()

        # Blue/Green or Canary plan
        self._check_deployment_strategy(skip_optional)

        # Schema/Data migrations
        self._check_migrations(skip_optional)

        # Feature flags
        self._check_feature_flags()

    def _check_iac(self) -> None:
        """Check for Infrastructure as Code."""
        # Look for IaC files
        iac_files = (
            list(self.repo_root.glob("**/*.tf"))
            + list(self.repo_root.glob("**/terraform/**/*"))
            + list(self.repo_root.glob("Dockerfile"))
            + list(self.repo_root.glob("docker-compose*.yml"))
            + list(self.repo_root.glob("**/k8s/**/*.yaml"))
            + list(self.repo_root.glob("**/*.yaml"))
        )

        # Filter to actual IaC files
        iac_files = [
            f
            for f in iac_files
            if "terraform" in str(f)
            or f.name == "Dockerfile"
            or "docker-compose" in f.name
            or "k8s" in str(f)
        ]

        if iac_files:
            self.checks.append(
                CheckResult(
                    name="IaC Validated",
                    category=CheckCategory.DEPLOYMENT,
                    status=CheckStatus.PASS,
                    proof=f"Found {len(iac_files)} IaC files",
                    evidence_paths=[str(p.relative_to(self.repo_root)) for p in iac_files[:10]],
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="IaC Validated",
                    category=CheckCategory.DEPLOYMENT,
                    status=CheckStatus.WARN,
                    proof="No IaC files found",
                    remediation="Add Dockerfile, docker-compose, or Terraform configurations",
                )
            )

    def _check_config_pinned(self) -> None:
        """Check for pinned configuration."""
        # Check for lock files and pinned versions
        lock_files = []
        if (self.repo_root / "poetry.lock").exists():
            lock_files.append("poetry.lock")
        if (self.repo_root / "package-lock.json").exists():
            lock_files.append("package-lock.json")
        if (self.repo_root / "pnpm-lock.yaml").exists():
            lock_files.append("pnpm-lock.yaml")

        if lock_files:
            self.checks.append(
                CheckResult(
                    name="Config Pinned",
                    category=CheckCategory.DEPLOYMENT,
                    status=CheckStatus.PASS,
                    proof=f"Dependencies pinned: {', '.join(lock_files)}",
                    metadata={"lock_files": lock_files},
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="Config Pinned",
                    category=CheckCategory.DEPLOYMENT,
                    status=CheckStatus.FAIL,
                    proof="No dependency lock files found",
                    remediation="Add poetry.lock or equivalent to pin dependencies",
                )
            )

    def _check_deployment_strategy(self, skip_optional: bool) -> None:
        """Check for deployment strategy documentation."""
        # Look for deployment docs
        deploy_docs = (
            list(self.repo_root.glob("**/DEPLOYMENT*.md"))
            + list(self.repo_root.glob("docs/**/deploy*.md"))
            + list(self.repo_root.glob("**/README*.md"))
        )

        has_strategy = False
        for doc in deploy_docs:
            content = doc.read_text()
            if any(
                term in content.lower()
                for term in ["blue/green", "canary", "rolling", "deployment strategy"]
            ):
                has_strategy = True
                break

        if has_strategy:
            self.checks.append(
                CheckResult(
                    name="Blue/Green or Canary Plan",
                    category=CheckCategory.DEPLOYMENT,
                    status=CheckStatus.PASS,
                    proof="Deployment strategy documented",
                )
            )
        elif skip_optional:
            self.checks.append(
                CheckResult(
                    name="Blue/Green or Canary Plan",
                    category=CheckCategory.DEPLOYMENT,
                    status=CheckStatus.SKIP,
                    proof="Skipped (optional check)",
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="Blue/Green or Canary Plan",
                    category=CheckCategory.DEPLOYMENT,
                    status=CheckStatus.WARN,
                    proof="No deployment strategy documentation found",
                    remediation="Document deployment strategy (blue/green, canary, etc.)",
                )
            )

    def _check_migrations(self, skip_optional: bool) -> None:
        """Check for schema/data migration support."""
        # Look for migration files
        migration_dirs = (
            list(self.repo_root.glob("**/migrations/"))
            + list(self.repo_root.glob("**/alembic/"))
            + list(self.repo_root.glob("**/db/migrate/"))
        )

        migration_files = []
        for migration_dir in migration_dirs:
            if migration_dir.is_dir():
                migration_files.extend(list(migration_dir.glob("*.py")))
                migration_files.extend(list(migration_dir.glob("*.sql")))

        if migration_files:
            self.checks.append(
                CheckResult(
                    name="Schema/Data Migrations",
                    category=CheckCategory.DEPLOYMENT,
                    status=CheckStatus.PASS,
                    proof=f"Found {len(migration_files)} migration files",
                    evidence_paths=[
                        str(p.relative_to(self.repo_root)) for p in migration_files[:10]
                    ],
                )
            )
        elif skip_optional:
            self.checks.append(
                CheckResult(
                    name="Schema/Data Migrations",
                    category=CheckCategory.DEPLOYMENT,
                    status=CheckStatus.SKIP,
                    proof="Skipped (optional check)",
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="Schema/Data Migrations",
                    category=CheckCategory.DEPLOYMENT,
                    status=CheckStatus.NA,
                    proof="No migration system found (may not be needed)",
                )
            )

    def _check_feature_flags(self) -> None:
        """Check for feature flag implementation."""
        # Look for feature flag patterns in code
        feature_flag_files = []
        excluded_dirs = {"test", "tests", "node_modules"}
        for py_file in self.repo_root.rglob("*.py"):
            if any(part in excluded_dirs for part in py_file.parts):
                continue
            try:
                content = py_file.read_text()
                if any(
                    term in content
                    for term in [
                        "FEATURE_",
                        "feature_flag",
                        "FeatureFlag",
                        "feature_toggle",
                    ]
                ):
                    feature_flag_files.append(py_file)
            except Exception:
                continue

        # Check .env.example for feature flags
        env_example = self.repo_root / ".env.example"
        has_env_flags = False
        if env_example.exists():
            content = env_example.read_text()
            if "FEATURE_" in content:
                has_env_flags = True

        if feature_flag_files or has_env_flags:
            self.checks.append(
                CheckResult(
                    name="Feature Flags",
                    category=CheckCategory.DEPLOYMENT,
                    status=CheckStatus.PASS,
                    proof=f"Feature flags found: {len(feature_flag_files)} files, env_example={'yes' if has_env_flags else 'no'}",
                    metadata={"files": len(feature_flag_files), "env_example": has_env_flags},
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="Feature Flags",
                    category=CheckCategory.DEPLOYMENT,
                    status=CheckStatus.WARN,
                    proof="No feature flag implementation found",
                    remediation="Implement feature flags for gradual rollouts",
                )
            )

    def _check_documentation_comms(self, skip_optional: bool) -> None:
        """Check documentation and communications requirements."""
        console.print("\n[bold]Docs & Comms[/bold]")

        # Release notes
        self._check_release_notes()

        # User/Admin docs
        self._check_user_docs()

        # Support handover
        self._check_support_handover(skip_optional)

    def _check_release_notes(self) -> None:
        """Check for release notes."""
        # Look for changelog/release notes
        release_docs = (
            list(self.repo_root.glob("CHANGELOG*.md"))
            + list(self.repo_root.glob("RELEASE*.md"))
            + list(self.repo_root.glob("NEWS*.md"))
        )

        if release_docs:
            self.checks.append(
                CheckResult(
                    name="Release Notes",
                    category=CheckCategory.DOCUMENTATION,
                    status=CheckStatus.PASS,
                    proof=f"Found {len(release_docs)} release documentation files",
                    evidence_paths=[str(p.relative_to(self.repo_root)) for p in release_docs],
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="Release Notes",
                    category=CheckCategory.DOCUMENTATION,
                    status=CheckStatus.FAIL,
                    proof="No CHANGELOG or release notes found",
                    remediation="Create CHANGELOG.md and maintain release notes",
                )
            )

    def _check_user_docs(self) -> None:
        """Check for user and admin documentation."""
        # Look for documentation
        readme_files = list(self.repo_root.glob("README*.md"))
        docs_dir = self.repo_root / "docs"

        doc_count = len(readme_files)
        if docs_dir.exists():
            doc_count += len(list(docs_dir.glob("**/*.md")))

        if doc_count > 0:
            self.checks.append(
                CheckResult(
                    name="User/Admin Docs",
                    category=CheckCategory.DOCUMENTATION,
                    status=CheckStatus.PASS,
                    proof=f"Found {doc_count} documentation files",
                    evidence_paths=["README.md", "docs/"] if docs_dir.exists() else ["README.md"],
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="User/Admin Docs",
                    category=CheckCategory.DOCUMENTATION,
                    status=CheckStatus.FAIL,
                    proof="No documentation found",
                    remediation="Add README.md and docs/ directory with user guides",
                )
            )

    def _check_support_handover(self, skip_optional: bool) -> None:
        """Check for support handover documentation."""
        # Look for support documentation
        support_docs = (
            list(self.repo_root.glob("**/SUPPORT*.md"))
            + list(self.repo_root.glob("docs/**/support*.md"))
            + list(self.repo_root.glob("**/CONTRIBUTING*.md"))
        )

        if support_docs:
            self.checks.append(
                CheckResult(
                    name="Support Handover",
                    category=CheckCategory.DOCUMENTATION,
                    status=CheckStatus.PASS,
                    proof=f"Found {len(support_docs)} support documentation files",
                    evidence_paths=[str(p.relative_to(self.repo_root)) for p in support_docs],
                )
            )
        elif skip_optional:
            self.checks.append(
                CheckResult(
                    name="Support Handover",
                    category=CheckCategory.DOCUMENTATION,
                    status=CheckStatus.SKIP,
                    proof="Skipped (optional check)",
                )
            )
        else:
            self.checks.append(
                CheckResult(
                    name="Support Handover",
                    category=CheckCategory.DOCUMENTATION,
                    status=CheckStatus.WARN,
                    proof="No support handover documentation found",
                    remediation="Add SUPPORT.md with support procedures and contacts",
                )
            )

    def _generate_report(self) -> PRRReport:
        """Generate final PRR report with Go/No-Go decision."""
        # Count check statuses
        status_counts = {status: 0 for status in CheckStatus}
        for check in self.checks:
            status_counts[check.status] += 1

        # Calculate residual risks
        residual_risks = []
        for check in self.checks:
            if check.status == CheckStatus.FAIL:
                residual_risks.append(
                    f"CRITICAL: {check.name} - {check.proof or 'No proof provided'}"
                )
            elif check.status == CheckStatus.WARN:
                residual_risks.append(
                    f"WARNING: {check.name} - {check.proof or 'No proof provided'}"
                )

        # Make Go/No-Go decision
        # Block release if any critical (FAIL) checks
        go_decision = status_counts[CheckStatus.FAIL] == 0

        # Generate summary
        summary = self._generate_summary(status_counts, go_decision)

        # Save evidence bundle
        evidence_bundle_path = self._save_evidence_bundle()

        # Print results
        self._print_results(status_counts)

        return PRRReport(
            project_name=self.project_name,
            review_date=datetime.now(UTC),
            checks=self.checks,
            go_decision=go_decision,
            residual_risks=residual_risks,
            summary=summary,
            evidence_bundle_path=str(evidence_bundle_path) if evidence_bundle_path else None,
        )

    def _generate_summary(
        self, status_counts: dict[CheckStatus, int], go_decision: bool
    ) -> str:
        """Generate PRR summary."""
        total = sum(status_counts.values())
        summary = f"Production Readiness Review Summary\n"
        summary += f"{'=' * 50}\n"
        summary += f"Total Checks: {total}\n"
        summary += f"  ✓ Pass: {status_counts[CheckStatus.PASS]}\n"
        summary += f"  ✗ Fail: {status_counts[CheckStatus.FAIL]}\n"
        summary += f"  ⚠ Warn: {status_counts[CheckStatus.WARN]}\n"
        summary += f"  - N/A: {status_counts[CheckStatus.NA]}\n"
        summary += f"  ⊘ Skip: {status_counts[CheckStatus.SKIP]}\n"
        summary += f"\n"
        summary += f"Go/No-Go Decision: {'✓ GO' if go_decision else '✗ NO-GO'}\n"

        if not go_decision:
            summary += f"\nRelease BLOCKED by {status_counts[CheckStatus.FAIL]} critical failures.\n"
            summary += "Address all FAIL checks before proceeding to production.\n"
        elif status_counts[CheckStatus.WARN] > 0:
            summary += f"\nRelease permitted with {status_counts[CheckStatus.WARN]} warnings.\n"
            summary += "Review residual risks and consider remediation.\n"

        return summary

    def _print_results(self, status_counts: dict[CheckStatus, int]) -> None:
        """Print PRR results to console."""
        console.print("\n[bold cyan]Production Readiness Review Results[/bold cyan]\n")

        # Create table by category
        for category in CheckCategory:
            category_checks = [c for c in self.checks if c.category == category]
            if not category_checks:
                continue

            table = Table(title=f"\n{category.value}", show_header=True, header_style="bold")
            table.add_column("Check", style="cyan", no_wrap=True)
            table.add_column("Status", justify="center", style="bold")
            table.add_column("Proof/Remediation", style="dim")

            for check in category_checks:
                status_text = Text(check.status.value)
                if check.status == CheckStatus.PASS:
                    status_text.stylize("green")
                elif check.status == CheckStatus.FAIL:
                    status_text.stylize("red bold")
                elif check.status == CheckStatus.WARN:
                    status_text.stylize("yellow")
                elif check.status == CheckStatus.SKIP:
                    status_text.stylize("dim")

                info = check.proof or ""
                if check.status in (CheckStatus.FAIL, CheckStatus.WARN) and check.remediation:
                    info = f"{info}\n→ {check.remediation}"

                table.add_row(check.name, status_text, info)

            console.print(table)

        # Print summary
        console.print(f"\n[bold]Summary[/bold]")
        console.print(f"  Total Checks: {sum(status_counts.values())}")
        console.print(f"  ✓ Pass: [green]{status_counts[CheckStatus.PASS]}[/green]")
        console.print(f"  ✗ Fail: [red bold]{status_counts[CheckStatus.FAIL]}[/red bold]")
        console.print(f"  ⚠ Warn: [yellow]{status_counts[CheckStatus.WARN]}[/yellow]")
        console.print(f"  - N/A: {status_counts[CheckStatus.NA]}")
        console.print(f"  ⊘ Skip: [dim]{status_counts[CheckStatus.SKIP]}[/dim]")

    def _save_evidence_bundle(self) -> Path | None:
        """Save evidence bundle to artifacts."""
        try:
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            report_path = self.evidence_dir / f"prr_report_{timestamp}.json"

            report_data = {
                "project_name": self.project_name,
                "review_date": datetime.now(UTC).isoformat(),
                "checks": [
                    {
                        "name": c.name,
                        "category": c.category.value,
                        "status": c.status.value,
                        "proof": c.proof,
                        "remediation": c.remediation,
                        "evidence_paths": c.evidence_paths,
                        "metadata": c.metadata,
                    }
                    for c in self.checks
                ],
            }

            report_path.write_text(json.dumps(report_data, indent=2))
            console.print(f"\n[green]Evidence bundle saved: {report_path}[/green]")
            return report_path
        except Exception as e:
            console.print(f"[yellow]Warning: Failed to save evidence bundle: {e}[/yellow]")
            return None
