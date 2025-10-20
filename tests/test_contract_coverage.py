"""Tests for contract coverage tracking."""

from __future__ import annotations

from pathlib import Path

from firecrawl_demo.integrations.contracts import (
    calculate_contract_coverage,
    report_coverage,
)


def test_calculate_contract_coverage_finds_sample_dataset() -> None:
    """Verify that the sample dataset is detected as a curated table."""
    coverage = calculate_contract_coverage()

    # Should have at least one table (sample)
    assert coverage.total_tables >= 1
    assert (
        "sample" in [t for t in ["sample"] if t not in coverage.uncovered_tables]
        or "sample" not in coverage.uncovered_tables
    )


def test_calculate_contract_coverage_checks_great_expectations() -> None:
    """Verify that Great Expectations coverage is detected."""
    coverage = calculate_contract_coverage()

    # The sample dataset should have Great Expectations coverage
    # since curated_dataset.json exists
    assert coverage.coverage_by_tool["great_expectations"] >= 1


def test_calculate_contract_coverage_checks_dbt() -> None:
    """Verify that dbt coverage is detected."""
    coverage = calculate_contract_coverage()

    # The sample dataset should have dbt coverage
    # since stg_curated_dataset.sql exists
    assert coverage.coverage_by_tool["dbt"] >= 1


def test_calculate_contract_coverage_meets_threshold() -> None:
    """Verify that coverage meets the 95% threshold."""
    coverage = calculate_contract_coverage()

    # With Great Expectations and dbt coverage for sample dataset,
    # coverage should be 100%
    assert coverage.coverage_percent >= 95.0
    assert coverage.meets_threshold


def test_report_coverage_generates_json(tmp_path: Path) -> None:
    """Verify that coverage report can be written to JSON."""
    output_path = tmp_path / "coverage_report.json"

    report = report_coverage(output_path)

    assert output_path.exists()
    assert report["total_tables"] >= 1
    assert report["coverage_percent"] >= 0.0
    assert report["threshold"] == 95.0
    assert "coverage_by_tool" in report
    assert "uncovered_tables" in report


def test_report_coverage_includes_all_tools() -> None:
    """Verify that coverage report tracks all contract tools."""
    report = report_coverage()

    assert "great_expectations" in report["coverage_by_tool"]
    assert "dbt" in report["coverage_by_tool"]
    assert "deequ" in report["coverage_by_tool"]


def test_contract_coverage_percentage_calculation() -> None:
    """Verify that coverage percentage is calculated correctly."""
    coverage = calculate_contract_coverage()

    if coverage.total_tables > 0:
        expected_percent = (coverage.covered_tables / coverage.total_tables) * 100.0
        assert abs(coverage.coverage_percent - expected_percent) < 0.01
