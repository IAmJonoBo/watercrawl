from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from firecrawl_demo.excel import EXPECTED_COLUMNS
from firecrawl_demo.lakehouse import LakehouseConfig, LocalLakehouseWriter


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


def test_local_lakehouse_writer_persists_snapshot(tmp_path: Path) -> None:
    config = LakehouseConfig(
        backend="delta",
        root_path=tmp_path,
        table_name="flight_schools",
    )
    writer = LocalLakehouseWriter(config)
    frame = _sample_frame()

    manifest = writer.write(run_id="run-001", dataframe=frame)

    assert manifest.table_uri.startswith("delta://")
    assert manifest.table_path.exists()
    assert (manifest.table_path / "data.parquet").exists()
    assert manifest.manifest_path.exists()
    assert manifest.fingerprint
    manifest_payload = json.loads(manifest.manifest_path.read_text())
    assert manifest_payload["run_id"] == "run-001"
    assert manifest_payload["row_count"] == 1
    assert manifest_payload["fingerprint"] == manifest.fingerprint
    assert manifest_payload["schema"]["Name of Organisation"]
    assert manifest_payload["environment"]["profile"] == "dev"
