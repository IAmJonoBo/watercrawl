import json
from pathlib import Path

import pandas as pd
from click.testing import CliRunner

from firecrawl_demo.cli import cli


def _write_sample_csv(path: Path, include_email: bool = False) -> None:
    base_row = {
        "Name of Organisation": "Aero Labs",
        "Province": "KwaZulu-Natal",
        "Status": "Candidate",
        "Website URL": "",
        "Contact Person": "",
        "Contact Number": "",
    }
    if include_email:
        base_row["Contact Email Address"] = "info@aerolabs.co.za"
    df = pd.DataFrame([base_row])
    df.to_csv(path, index=False)


def test_cli_validate_reports_issues(tmp_path):
    input_path = tmp_path / "input.csv"
    _write_sample_csv(input_path, include_email=False)

    runner = CliRunner()
    result = runner.invoke(cli, ["validate", str(input_path), "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["rows"] == 1
    assert payload["issues"][0]["code"] == "missing_column"


def test_cli_enrich_creates_output(tmp_path):
    input_path = tmp_path / "input.csv"
    output_path = tmp_path / "output.csv"
    _write_sample_csv(input_path, include_email=True)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "enrich",
            str(input_path),
            "--output",
            str(output_path),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["rows_enriched"] == 1
    assert output_path.exists()
