"""Tests for Production Readiness Review (PRR) module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from watercrawl.governance.production_readiness import (
    CheckCategory,
    CheckResult,
    CheckStatus,
    ProductionReadinessReview,
    PRRReport,
)


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    """Create a temporary repository structure for testing."""
    repo = tmp_path / "test_repo"
    repo.mkdir()

    # Create basic structure
    (repo / "tests").mkdir()
    (repo / "tests" / "test_example.py").write_text("def test_example(): pass")
    (repo / "docs").mkdir()
    (repo / "README.md").write_text("# Test Project")
    (repo / "LICENSE").write_text("MIT License")
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n## v1.0.0\n")
    (repo / ".github" / "workflows").mkdir(parents=True)

    # Create pyproject.toml
    pyproject_content = """
[tool.poetry]
name = "test-project"
version = "0.1.0"

[tool.poetry.dependencies]
python = "^3.13"

[tool.poetry.group.dev.dependencies]
pytest = "^8.0"
pytest-cov = "^5.0"
ruff = "^0.14"
black = "^25.0"
isort = "^7.0"
mypy = "^1.18"
bandit = "^1.8"
"""
    (repo / "pyproject.toml").write_text(pyproject_content)

    # Create poetry.lock
    (repo / "poetry.lock").write_text("")

    return repo


def test_prr_initialization(temp_repo: Path) -> None:
    """Test PRR initialization."""
    prr = ProductionReadinessReview(repo_root=temp_repo, project_name="test-project")
    assert prr.repo_root == temp_repo
    assert prr.project_name == "test-project"
    assert prr.checks == []
    assert prr.evidence_dir.exists()


def test_check_result_creation() -> None:
    """Test CheckResult dataclass."""
    check = CheckResult(
        name="Test Check",
        category=CheckCategory.QUALITY,
        status=CheckStatus.PASS,
        proof="Test passed",
        remediation=None,
        evidence_paths=["test.py"],
        metadata={"count": 5},
    )
    assert check.name == "Test Check"
    assert check.category == CheckCategory.QUALITY
    assert check.status == CheckStatus.PASS
    assert check.proof == "Test passed"
    assert check.evidence_paths == ["test.py"]
    assert check.metadata["count"] == 5


def test_prr_report_to_dict() -> None:
    """Test PRR report conversion to dictionary."""
    from datetime import UTC, datetime

    check = CheckResult(
        name="Test Check",
        category=CheckCategory.QUALITY,
        status=CheckStatus.PASS,
        proof="Test proof",
    )

    report = PRRReport(
        project_name="test-project",
        review_date=datetime.now(UTC),
        checks=[check],
        go_decision=True,
        residual_risks=[],
        summary="Test summary",
    )

    report_dict = report.to_dict()
    assert report_dict["project_name"] == "test-project"
    assert report_dict["go_decision"] is True
    assert len(report_dict["checks"]) == 1
    assert report_dict["checks"][0]["name"] == "Test Check"


def test_check_tests_configured(temp_repo: Path) -> None:
    """Test that PRR detects test configuration."""
    prr = ProductionReadinessReview(repo_root=temp_repo)
    prr._check_tests()

    assert len(prr.checks) == 1
    check = prr.checks[0]
    assert check.name == "Unit/Integration/E2E Tests"
    assert check.category == CheckCategory.QUALITY
    assert check.status == CheckStatus.PASS
    assert check.proof is not None
    assert "pytest" in check.proof.lower()


def test_check_lint_configured(temp_repo: Path) -> None:
    """Test that PRR detects linting configuration."""
    prr = ProductionReadinessReview(repo_root=temp_repo)
    prr._check_lint()

    assert len(prr.checks) == 1
    check = prr.checks[0]
    assert check.name == "Linting Configuration"
    assert check.status == CheckStatus.PASS
    assert check.proof is not None
    assert "ruff" in check.proof.lower()


def test_check_static_analysis_configured(temp_repo: Path) -> None:
    """Test that PRR detects static analysis tools."""
    prr = ProductionReadinessReview(repo_root=temp_repo)
    prr._check_static_analysis()

    assert len(prr.checks) == 1
    check = prr.checks[0]
    assert check.name == "Static Analysis"
    assert check.status == CheckStatus.PASS
    assert check.proof is not None
    assert "mypy" in check.proof.lower()


def test_check_threat_model_fail(temp_repo: Path) -> None:
    """Test that PRR fails without threat model documentation."""
    prr = ProductionReadinessReview(repo_root=temp_repo)
    prr._check_threat_model()

    assert len(prr.checks) == 1
    check = prr.checks[0]
    assert check.name == "Threat Model"
    assert check.status == CheckStatus.FAIL
    assert check.remediation is not None


def test_check_threat_model_pass(temp_repo: Path) -> None:
    """Test that PRR passes with SECURITY.md."""
    (temp_repo / "SECURITY.md").write_text("# Security\n\nThreat model...")
    prr = ProductionReadinessReview(repo_root=temp_repo)
    prr._check_threat_model()

    assert len(prr.checks) == 1
    check = prr.checks[0]
    assert check.name == "Threat Model"
    assert check.status == CheckStatus.PASS


def test_check_sbom_with_lock_files(temp_repo: Path) -> None:
    """Test SBOM check with lock files."""
    prr = ProductionReadinessReview(repo_root=temp_repo)
    prr._check_sbom()

    assert len(prr.checks) == 1
    check = prr.checks[0]
    assert check.name == "SBOM (SPDX/CycloneDX)"
    assert check.status == CheckStatus.WARN
    assert check.proof is not None
    assert "poetry.lock" in check.proof


def test_check_licenses(temp_repo: Path) -> None:
    """Test license check."""
    prr = ProductionReadinessReview(repo_root=temp_repo)
    prr._check_licenses()

    assert len(prr.checks) == 1
    check = prr.checks[0]
    assert check.name == "Third-party License Obligations"
    assert check.status == CheckStatus.PASS


def test_check_release_notes(temp_repo: Path) -> None:
    """Test release notes check."""
    prr = ProductionReadinessReview(repo_root=temp_repo)
    prr._check_release_notes()

    assert len(prr.checks) == 1
    check = prr.checks[0]
    assert check.name == "Release Notes"
    assert check.status == CheckStatus.PASS


def test_check_config_pinned(temp_repo: Path) -> None:
    """Test config pinning check."""
    prr = ProductionReadinessReview(repo_root=temp_repo)
    prr._check_config_pinned()

    assert len(prr.checks) == 1
    check = prr.checks[0]
    assert check.name == "Config Pinned"
    assert check.status == CheckStatus.PASS
    assert check.proof is not None
    assert "poetry.lock" in check.proof


def test_check_feature_flags(temp_repo: Path) -> None:
    """Test feature flags check."""
    # Create a file with feature flags
    code_dir = temp_repo / "src"
    code_dir.mkdir()
    (code_dir / "config.py").write_text(
        "FEATURE_ENABLE_NEW_API = os.getenv('FEATURE_ENABLE_NEW_API', '0')"
    )

    prr = ProductionReadinessReview(repo_root=temp_repo)
    prr._check_feature_flags()

    assert len(prr.checks) == 1
    check = prr.checks[0]
    assert check.name == "Feature Flags"
    assert check.status == CheckStatus.PASS


def test_skip_optional_checks(temp_repo: Path) -> None:
    """Test that optional checks are skipped when requested."""
    prr = ProductionReadinessReview(repo_root=temp_repo)

    # This should be skipped
    prr._check_coverage(skip_optional=True)

    assert len(prr.checks) == 1
    check = prr.checks[0]
    assert check.status == CheckStatus.SKIP


def test_full_prr_run(temp_repo: Path) -> None:
    """Test full PRR execution."""
    prr = ProductionReadinessReview(repo_root=temp_repo)
    report = prr.run_all_checks(skip_optional=True)

    assert isinstance(report, PRRReport)
    assert report.project_name == "watercrawl"
    assert len(report.checks) > 0
    assert isinstance(report.go_decision, bool)
    assert isinstance(report.residual_risks, list)
    assert isinstance(report.summary, str)


def test_go_decision_with_failures(temp_repo: Path) -> None:
    """Test that PRR returns NO-GO with critical failures."""
    # Remove LICENSE to cause failure
    (temp_repo / "LICENSE").unlink()

    prr = ProductionReadinessReview(repo_root=temp_repo)
    report = prr.run_all_checks(skip_optional=True)

    # Should have failures
    has_failures = any(check.status == CheckStatus.FAIL for check in report.checks)
    assert has_failures

    # Decision should be NO-GO
    assert not report.go_decision


def test_go_decision_with_warnings_only(temp_repo: Path) -> None:
    """Test that PRR returns GO with only warnings."""
    prr = ProductionReadinessReview(repo_root=temp_repo)

    # Manually add only warning checks
    prr.checks = [
        CheckResult(
            name="Test Warning",
            category=CheckCategory.QUALITY,
            status=CheckStatus.WARN,
            proof="This is just a warning",
        )
    ]

    report = prr._generate_report()

    # Decision should be GO (warnings don't block)
    assert report.go_decision
    assert len(report.residual_risks) > 0


def test_evidence_bundle_creation(temp_repo: Path) -> None:
    """Test that evidence bundle is created."""
    prr = ProductionReadinessReview(repo_root=temp_repo)
    prr._check_tests()

    evidence_path = prr._save_evidence_bundle()

    assert evidence_path is not None
    assert evidence_path.exists()
    assert evidence_path.suffix == ".json"

    # Verify JSON content
    data = json.loads(evidence_path.read_text())
    assert data["project_name"] == "watercrawl"
    assert len(data["checks"]) > 0


def test_check_categories_coverage() -> None:
    """Test that all check categories are defined."""
    categories = [
        CheckCategory.QUALITY,
        CheckCategory.RELIABILITY,
        CheckCategory.SECURITY,
        CheckCategory.SUPPLY_CHAIN,
        CheckCategory.COMPLIANCE,
        CheckCategory.OBSERVABILITY,
        CheckCategory.DEPLOYMENT,
        CheckCategory.DOCUMENTATION,
    ]
    assert len(categories) == 8


def test_check_statuses_coverage() -> None:
    """Test that all check statuses are defined."""
    statuses = [
        CheckStatus.PASS,
        CheckStatus.FAIL,
        CheckStatus.WARN,
        CheckStatus.NA,
        CheckStatus.SKIP,
    ]
    assert len(statuses) == 5
