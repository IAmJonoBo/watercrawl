from __future__ import annotations

from pathlib import Path

import pandas as pd

from firecrawl_demo.core.excel import EXPECTED_COLUMNS
from firecrawl_demo.integrations.telemetry.graph_semantics import (
    GraphSemanticsReport,
    GraphValidationIssue,
    build_csvw_metadata,
    build_r2rml_mapping,
    generate_graph_semantics_report,
)


def _sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Name of Organisation": "Aero Academy",
                "Province": "Gauteng",
                "Status": "Verified",
                "Website URL": "https://aero.example",
                "Contact Person": "Sam Analyst",
                "Contact Number": "+27110000000",
                "Contact Email Address": "sam@aero.example",
            }
        ],
        columns=list(EXPECTED_COLUMNS),
    )


def test_csvw_metadata_enumerates_columns(tmp_path: Path) -> None:
    frame = _sample_frame()
    metadata = build_csvw_metadata(
        frame=frame,
        dataset_uri="file://flight-schools.csv",
        evidence_log_uri="file://evidence.csv",
    )

    assert metadata["table"]["url"] == "file://flight-schools.csv"
    column_names = [
        column["name"] for column in metadata["table"]["tableSchema"]["columns"]
    ]
    assert "Province" in column_names
    assert metadata["table"]["notes"]["evidenceLog"] == "file://evidence.csv"


def test_r2rml_mapping_contains_predicates() -> None:
    mapping = build_r2rml_mapping(
        dataset_uri="file://flight-schools.csv", table_name="flight_schools"
    )

    assert "rr:logicalTable" in mapping
    assert "ex:province" in mapping
    assert "rr:template" in mapping


def test_generate_graph_semantics_report_success(tmp_path: Path) -> None:
    frame = _sample_frame()
    report = generate_graph_semantics_report(
        frame=frame,
        dataset_uri="file://flight-schools.csv",
        evidence_log_uri="file://evidence.csv",
    )

    assert isinstance(report, GraphSemanticsReport)
    assert report.valid
    assert report.metrics.organisation_nodes == 1
    assert report.metrics.edge_count == 2
    assert (
        report.csvw_metadata["table"]["notes"]["evidenceLog"] == "file://evidence.csv"
    )


def test_generate_graph_semantics_report_flags_missing_province() -> None:
    frame = _sample_frame()
    frame.loc[0, "Province"] = ""

    report = generate_graph_semantics_report(
        frame=frame,
        dataset_uri="file://flight-schools.csv",
        evidence_log_uri=None,
    )

    assert not report.valid
    issue_codes = [issue.code for issue in report.issues]
    assert "MISSING_PROVINCE" in issue_codes
    assert "PROVINCE_NODE_UNDERFLOW" in issue_codes
    assert any(isinstance(issue, GraphValidationIssue) for issue in report.issues)


def test_generate_graph_semantics_report_flags_low_average_degree() -> None:
    frame = _sample_frame()
    frame.loc[0, "Status"] = ""
    frame.loc[0, "Province"] = ""

    report = generate_graph_semantics_report(
        frame=frame,
        dataset_uri="file://flight-schools.csv",
        evidence_log_uri=None,
    )

    issue_codes = [issue.code for issue in report.issues]
    assert "AVG_DEGREE_UNDERFLOW" in issue_codes
