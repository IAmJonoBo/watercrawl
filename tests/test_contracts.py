from __future__ import annotations

from pathlib import Path

import pandas as pd
from click.testing import CliRunner

from firecrawl_demo.cli import cli
from firecrawl_demo.contracts import validate_curated_dataframe


def _valid_row() -> dict[str, str]:
    return {
        "Name of Organisation": "Test Flight School",
        "Province": "Gauteng",
        "Status": "Verified",
        "Website URL": "https://testflightschool.co.za",
        "Contact Person": "Amina Dlamini",
        "Contact Number": "+27123456789",
        "Contact Email Address": "amina@testflightschool.co.za",
    }


def test_validate_curated_dataframe_succeeds_for_valid_row() -> None:
    frame = pd.DataFrame([_valid_row()])
    result = validate_curated_dataframe(frame)
    assert result.success
    assert result.unsuccessful_expectations == 0


def test_validate_curated_dataframe_flags_invalid_province() -> None:
    invalid_row = _valid_row()
    invalid_row["Province"] = "Atlantis"
    frame = pd.DataFrame([invalid_row])
    result = validate_curated_dataframe(frame)
    assert not result.success
    assert result.unsuccessful_expectations >= 1


def test_contracts_cli_reports_failures(tmp_path: Path) -> None:
    invalid_row = _valid_row()
    invalid_row["Status"] = "Invalid"
    frame = pd.DataFrame([invalid_row])
    dataset_path = tmp_path / "invalid.csv"
    frame.to_csv(dataset_path, index=False)

    runner = CliRunner()
    response = runner.invoke(cli, ["contracts", str(dataset_path)])

    assert response.exit_code != 0
    assert "Failing expectations" in response.output
