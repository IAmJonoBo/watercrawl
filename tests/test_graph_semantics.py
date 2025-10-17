from __future__ import annotations

from pathlib import Path

import pandas as pd

from firecrawl_demo.core.excel import EXPECTED_COLUMNS
from firecrawl_demo.integrations.graph_semantics import (
    build_csvw_metadata,
    build_r2rml_mapping,
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
