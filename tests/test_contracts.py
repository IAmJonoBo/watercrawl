from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path

import pandas as pd
import pytest
from click.testing import CliRunner
from pydantic import ValidationError

from watercrawl.core import config
from watercrawl.domain.contracts import EvidenceRecordContract
from watercrawl.infrastructure.evidence import (
    CSVEvidenceSink,
    StreamingEvidenceSink,
)
from watercrawl.integrations.contracts import (
    DBT_AVAILABLE,
    GREAT_EXPECTATIONS_AVAILABLE,
    DbtContractResult,
    run_dbt_contract_tests,
    validate_curated_dataframe,
)
from watercrawl.interfaces.cli import cli


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


@pytest.mark.skipif(
    not GREAT_EXPECTATIONS_AVAILABLE,
    reason="Great Expectations not available in this environment",
)
def test_validate_curated_dataframe_succeeds_for_valid_row() -> None:
    frame = pd.DataFrame([_valid_row()])
    result = validate_curated_dataframe(frame)
    assert result.success
    assert result.unsuccessful_expectations == 0
    assert result.statistics.get("successful_expectations") == result.statistics.get(
        "evaluated_expectations"
    )


@pytest.mark.skipif(
    not GREAT_EXPECTATIONS_AVAILABLE,
    reason="Great Expectations not available in this environment",
)
def test_validate_curated_dataframe_flags_invalid_province() -> None:
    invalid_row = _valid_row()
    invalid_row["Province"] = "Atlantis"
    frame = pd.DataFrame([invalid_row])
    result = validate_curated_dataframe(frame)
    assert not result.success
    assert result.unsuccessful_expectations >= 1


@pytest.mark.skipif(
    not GREAT_EXPECTATIONS_AVAILABLE,
    reason="Great Expectations not available in this environment",
)
def test_validate_curated_dataframe_enforces_confidence_threshold() -> None:
    low_confidence = _valid_row()
    low_confidence["Confidence"] = "40"
    frame = pd.DataFrame([low_confidence])
    result = validate_curated_dataframe(frame)
    assert not result.success
    assert result.unsuccessful_expectations >= 1


@pytest.fixture()
def contracts_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Path]:
    evidence_log = tmp_path / "evidence_log.csv"
    contracts_dir = tmp_path / "contracts_artifacts"
    monkeypatch.setattr(config, "EVIDENCE_LOG", evidence_log)
    monkeypatch.setenv("CONTRACTS_ARTIFACT_DIR", str(contracts_dir))
    monkeypatch.setenv("DBT_TARGET_PATH", str(tmp_path / "target"))
    monkeypatch.setenv("DBT_LOG_PATH", str(tmp_path / "logs"))
    monkeypatch.setenv("DBT_DUCKDB_PATH", str(tmp_path / "contracts.duckdb"))
    monkeypatch.setenv(
        "DBT_PROFILES_DIR",
        str(config.PROJECT_ROOT / "data_contracts" / "analytics"),
    )
    return {"evidence_log": evidence_log, "contracts_dir": contracts_dir}


@pytest.mark.skipif(
    not DBT_AVAILABLE,
    reason="dbt-core not available in this environment",
)
def test_dbt_contract_runner_passes(
    tmp_path: Path, contracts_runtime: dict[str, Path]
) -> None:
    dataset_path = tmp_path / "valid.csv"
    pd.DataFrame([_valid_row()]).to_csv(dataset_path, index=False)

    previous_canonical = os.environ.get("CONTRACTS_CANONICAL_JSON")

    result = run_dbt_contract_tests(
        dataset_path,
        project_dir=config.PROJECT_ROOT / "data_contracts" / "analytics",
        profiles_dir=config.PROJECT_ROOT / "data_contracts" / "analytics",
        target_path=contracts_runtime["contracts_dir"] / "target",
        log_path=contracts_runtime["contracts_dir"] / "logs",
    )

    assert isinstance(result, DbtContractResult)
    assert result.success
    assert result.failures == 0
    assert result.total >= 1
    assert result.run_results_path is not None
    assert result.run_results_path.exists()
    assert result.project_dir == config.PROJECT_ROOT / "data_contracts" / "analytics"
    assert result.profiles_dir == config.PROJECT_ROOT / "data_contracts" / "analytics"
    assert os.environ.get("CONTRACTS_CANONICAL_JSON") == previous_canonical


@pytest.mark.skipif(
    not DBT_AVAILABLE,
    reason="dbt-core not available in this environment",
)
def test_contracts_cli_reports_failures(
    tmp_path: Path, contracts_runtime: dict[str, Path]
) -> None:
    invalid_row = _valid_row()
    invalid_row["Website URL"] = "http://testflightschool.co.za"
    frame = pd.DataFrame([invalid_row])
    dataset_path = tmp_path / "invalid.csv"
    frame.to_csv(dataset_path, index=False)

    runner = CliRunner()
    response = runner.invoke(cli, ["contracts", str(dataset_path)])

    assert response.exit_code != 0
    assert "Failing expectations" in response.output
    assert "Deequ checks:" in response.output
    dbt_line = next(
        (
            line
            for line in response.output.splitlines()
            if line.startswith("dbt tests:")
        ),
        "",
    )
    assert dbt_line
    if "Failing dbt tests" not in response.output:
        assert "passed" in dbt_line


@pytest.mark.skipif(
    not DBT_AVAILABLE,
    reason="dbt-core not available in this environment",
)
def test_contracts_cli_runs_both_suites_and_logs_evidence(
    tmp_path: Path, contracts_runtime: dict[str, Path]
) -> None:
    dataset_path = tmp_path / "valid.csv"
    pd.DataFrame([_valid_row()]).to_csv(dataset_path, index=False)

    runner = CliRunner()
    response = runner.invoke(cli, ["contracts", str(dataset_path), "--format", "json"])

    assert response.exit_code == 0
    raw_output = response.output
    json_start = raw_output.find("{")
    assert json_start != -1, raw_output
    payload = json.loads(raw_output[json_start:])
    assert payload["success"] is True
    assert payload["dbt"]["success"] is True
    assert payload["deequ"]["success"] is True
    assert payload["deequ"]["check_count"] > 0
    assert Path(payload["artifact_dir"]).exists()
    assert (Path(payload["artifact_dir"]) / "deequ_result.json").exists()

    evidence_log = contracts_runtime["evidence_log"]
    assert evidence_log.exists()
    with evidence_log.open() as handle:
        rows = list(csv.DictReader(handle))

    assert rows
    latest = rows[-1]
    assert latest["Organisation"] == dataset_path.name
    assert "Great Expectations" in latest["Notes"]
    assert "dbt tests" in latest["Notes"]
    assert "Deequ" in latest["Notes"]


@pytest.mark.skipif(
    not DBT_AVAILABLE,
    reason="dbt-core not available in this environment",
)
def test_contracts_cli_reports_deequ_failures(
    tmp_path: Path, contracts_runtime: dict[str, Path]
) -> None:
    invalid_row = _valid_row()
    invalid_row["Contact Email Address"] = ""
    dataset_path = tmp_path / "invalid_deequ.csv"
    pd.DataFrame([invalid_row]).to_csv(dataset_path, index=False)

    runner = CliRunner()
    response = runner.invoke(cli, ["contracts", str(dataset_path)])

    assert response.exit_code != 0
    assert "Failing Deequ checks" in response.output
    assert "verified_email_present" in response.output


def test_contracts_cli_persists_artifacts(
    tmp_path: Path, contracts_runtime: dict[str, Path]
) -> None:
    pytest.skip("dbt-core not available in Python 3.14 environment")
    dataset_path = tmp_path / "valid.csv"
    pd.DataFrame([_valid_row()]).to_csv(dataset_path, index=False)

    runner = CliRunner()
    response = runner.invoke(cli, ["contracts", str(dataset_path), "--format", "json"])

    assert response.exit_code == 0, response.output

    contracts_dir = contracts_runtime["contracts_dir"]
    artifact_dirs = [
        candidate for candidate in contracts_dir.iterdir() if candidate.is_dir()
    ]
    assert len(artifact_dirs) == 1
    artifact_dir = artifact_dirs[0]

    assert re.fullmatch(r"\d{8}T\d{6}Z", artifact_dir.name)

    assert (artifact_dir / "dataset_path.txt").read_text() == str(dataset_path)

    ge_payload = json.loads(
        (artifact_dir / "great_expectations_result.json").read_text()
    )
    assert ge_payload.get("success") is True
    assert ge_payload.get("statistics", {}).get("successful_expectations")

    dbt_payload = json.loads((artifact_dir / "dbt_run_results.json").read_text())
    results = dbt_payload.get("results", [])
    assert isinstance(results, list) and results, dbt_payload
    statuses = {
        str(entry.get("status", "")).lower()
        for entry in results
        if isinstance(entry, dict)
    }
    assert statuses.issubset({"success", "pass", "warn", "skipped"})


def test_csv_evidence_sink_validates_mappings(tmp_path: Path) -> None:
    """Evidence sinks should coerce mappings through the contract model."""

    sink = CSVEvidenceSink(path=tmp_path / "evidence.csv")
    sink.record(
        [
            {
                "row_id": 1,
                "organisation": "Test School",
                "changes": "Initial contract export",
                "sources": ["https://example.com", "https://gov.za"],
                "notes": "Automated QA",
                "confidence": 90,
            }
        ]
    )
    assert sink.path.exists()

    with pytest.raises(ValidationError):
        sink.record(
            [
                {
                    "row_id": -1,
                    "organisation": "Test School",
                    "changes": "Invalid contract",
                    "sources": [],
                    "confidence": 150,
                }
            ]
        )


def test_evidence_sink_revalidates_contract_instances(tmp_path: Path) -> None:
    """Contracts created without validation should still be enforced."""

    contract = EvidenceRecordContract.model_construct(
        row_id=-1,
        organisation="Test School",
        changes="Invalid contract",
        sources=[],
        confidence=50,
    )
    sink = CSVEvidenceSink(path=tmp_path / "log.csv")
    with pytest.raises(ValidationError):
        sink.record([contract])


def test_streaming_evidence_sink_rejects_invalid_payloads() -> None:
    """Streaming sinks apply the same contract validation pipeline."""

    sink = StreamingEvidenceSink(enabled=True)
    with pytest.raises(TypeError):
        sink.record(["not a contract"])  # type: ignore[list-item]
    with pytest.raises(ValidationError):
        sink.record(
            [
                {
                    "row_id": 0,
                    "organisation": "Test",
                    "changes": "Invalid",
                    "sources": [],
                    "confidence": -1,
                }
            ]
        )
