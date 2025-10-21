"""Tests for Deequ contract runner."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from firecrawl_demo.integrations.contracts import (
    DEEQU_AVAILABLE,
    DeequContractResult,
    run_deequ_checks,
)


def _valid_row() -> dict[str, str]:
    return {
        "Name of Organisation": "Test Flight School",
        "Province": "Gauteng",
        "Status": "Verified",
        "Website URL": "https://testflightschool.co.za",
        "Contact Person": "Amina Dlamini",
        "Contact Number": "+27123456789",
        "Contact Email Address": "amina@testflightschool.co.za",
        "Confidence": "85",
    }


def test_deequ_runner_succeeds_for_valid_dataset(tmp_path: Path) -> None:
    dataset_path = tmp_path / "valid.csv"
    pd.DataFrame([_valid_row()]).to_csv(dataset_path, index=False)

    result = run_deequ_checks(dataset_path)

    assert isinstance(result, DeequContractResult)
    assert result.success is True
    assert result.failures == 0
    assert result.check_count > 0
    assert result.metrics["row_count"] == 1
    assert result.metrics["verified_email_ratio"] == 1.0


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
        results=[],
    )

    assert result.success is True
    assert result.check_count == 5
    assert result.failures == 0
    assert result.metrics["completeness"] == 1.0


def test_deequ_runner_flags_verified_contact_gaps(tmp_path: Path) -> None:
    invalid = _valid_row()
    invalid["Contact Email Address"] = ""
    dataset_path = tmp_path / "invalid.csv"
    pd.DataFrame([invalid]).to_csv(dataset_path, index=False)

    result = run_deequ_checks(dataset_path)

    assert result.success is False
    failing_checks = {
        entry["check"] for entry in result.results if not entry.get("success", True)
    }
    assert "verified_email_present" in failing_checks
    assert result.metrics["verified_email_ratio"] == 0.0


def test_deequ_runner_detects_duplicate_names(tmp_path: Path) -> None:
    dataset_path = tmp_path / "duplicates.csv"
    pd.DataFrame([_valid_row(), _valid_row()]).to_csv(dataset_path, index=False)

    result = run_deequ_checks(dataset_path)

    assert not result.success
    duplicate_entry = next(
        entry for entry in result.results if entry["check"] == "unique_name"
    )
    assert duplicate_entry["success"] is False
    assert duplicate_entry["details"]["duplicates"]
