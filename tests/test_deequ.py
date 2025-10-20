"""Tests for Deequ contract runner."""

from __future__ import annotations

from pathlib import Path

import pytest

from firecrawl_demo.integrations.contracts import (
    DEEQU_AVAILABLE,
    DeequContractResult,
    run_deequ_checks,
)


def test_deequ_runner_returns_stub_when_unavailable(tmp_path: Path) -> None:
    """Verify that Deequ runner returns a stub result when PySpark is not available."""
    dataset_path = tmp_path / "test.csv"
    dataset_path.write_text("col1,col2\nval1,val2\n")

    result = run_deequ_checks(dataset_path)

    assert isinstance(result, DeequContractResult)
    # When PySpark is not available, returns success with 0 checks
    if not DEEQU_AVAILABLE:
        assert result.success is True
        assert result.check_count == 0
        assert result.failures == 0
        assert "note" in result.metrics


def test_deequ_available_flag() -> None:
    """Verify that DEEQU_AVAILABLE flag reflects PySpark availability."""
    # This test simply checks that the flag is a boolean
    assert isinstance(DEEQU_AVAILABLE, bool)


def test_deequ_result_dataclass() -> None:
    """Verify that DeequContractResult can be instantiated."""
    result = DeequContractResult(
        success=True,
        check_count=5,
        failures=0,
        metrics={"completeness": 1.0},
    )

    assert result.success is True
    assert result.check_count == 5
    assert result.failures == 0
    assert result.metrics["completeness"] == 1.0


def test_deequ_result_with_failures() -> None:
    """Verify that DeequContractResult handles failures correctly."""
    result = DeequContractResult(
        success=False,
        check_count=5,
        failures=2,
        metrics={"completeness": 0.8},
    )

    assert result.success is False
    assert result.failures == 2
    assert result.check_count == 5
