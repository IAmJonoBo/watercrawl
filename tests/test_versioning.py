import json
from pathlib import Path

import pandas as pd

from firecrawl_demo.core.excel import EXPECTED_COLUMNS
from firecrawl_demo.integrations.storage.lakehouse import (
    LakehouseConfig,
    LocalLakehouseWriter,
)
from firecrawl_demo.integrations.storage.versioning import (
    VersioningManager,
    fingerprint_dataframe,
)


def _sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Name of Organisation": "Orbit Flyers",
                "Province": "Gauteng",
                "Status": "Verified",
                "Website URL": "https://orbit.example",
                "Contact Person": "Alex Orbit",
                "Contact Number": "+27110000001",
                "Contact Email Address": "alex@orbit.example",
            }
        ],
        columns=list(EXPECTED_COLUMNS),
    )


def test_versioning_manager_records_snapshot(tmp_path: Path) -> None:
    frame = _sample_frame()
    writer = LocalLakehouseWriter(
        LakehouseConfig(root_path=tmp_path / "lake", table_name="flight_schools")
    )
    manifest = writer.write(run_id="run-002", dataframe=frame)

    manager = VersioningManager(metadata_root=tmp_path / "versions", enabled=True)
    input_fingerprint = fingerprint_dataframe(frame)

    version_info = manager.record_snapshot(
        run_id="run-002",
        manifest=manifest,
        input_fingerprint=input_fingerprint,
        extras={"initiator": "unit-test"},
    )

    assert version_info.run_id == "run-002"
    assert version_info.version == manifest.version
    assert version_info.metadata_path.exists()

    metadata = json.loads(version_info.metadata_path.read_text())
    assert metadata["input_fingerprint"] == input_fingerprint
    assert metadata["output_fingerprint"] == manifest.fingerprint
    assert metadata["extras"]["initiator"] == "unit-test"
    assert metadata["reproduce"]["command"][0] == "poetry"
    assert version_info.extras["initiator"] == "unit-test"
