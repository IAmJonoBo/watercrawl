# bandit: disable=B101 - pytest assertions exercise return payloads

import json
from pathlib import Path

import pandas as pd
import pytest

from watercrawl.core.excel import EXPECTED_COLUMNS
from watercrawl.integrations.storage import versioning as versioning_module
from watercrawl.integrations.storage.lakehouse import (
    LakehouseConfig,
    LocalLakehouseWriter,
)
from watercrawl.integrations.storage.versioning import (
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


def test_versioning_manager_records_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = _sample_frame()
    writer = LocalLakehouseWriter(
        LakehouseConfig(root_path=tmp_path / "lake", table_name="flight_schools")
    )
    manifest = writer.write(run_id="run-002", dataframe=frame)

    manager = VersioningManager(metadata_root=tmp_path / "versions", enabled=True)
    input_fingerprint = fingerprint_dataframe(frame)

    monkeypatch.setattr(versioning_module, "_capture_git_commit", lambda: None)

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


def test_versioning_manager_includes_dvc_and_lakefs_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = _sample_frame()
    writer = LocalLakehouseWriter(
        LakehouseConfig(root_path=tmp_path / "lake", table_name="flight_schools")
    )
    manifest = writer.write(run_id="run-003", dataframe=frame)

    manager = VersioningManager(metadata_root=tmp_path / "versions", enabled=True)
    manager._dvc_remote = "s3://delta-remote"
    manager._lakefs_repo = "lakefs://main"

    monkeypatch.setenv("DVC_COMMIT", "abc123")
    monkeypatch.setenv("LAKEFS_BRANCH", "develop")
    monkeypatch.setenv("LAKEFS_COMMIT", "def456")
    monkeypatch.setattr(versioning_module, "_capture_git_commit", lambda: "deadbeef")

    version_info = manager.record_snapshot(
        run_id="run-003",
        manifest=manifest,
        input_fingerprint=fingerprint_dataframe(frame),
    )

    metadata = json.loads(version_info.metadata_path.read_text())
    assert metadata["git_commit"] == "deadbeef"
    assert metadata["dvc"]["remote"] == "s3://delta-remote"
    assert metadata["dvc"]["commit"] == "abc123"
    assert metadata["lakefs"]["repository"] == "lakefs://main"
    assert metadata["lakefs"]["branch"] == "develop"
    assert metadata["lakefs"]["commit"] == "def456"

    dvc_pointer = (version_info.metadata_path.parent / "dvc.json").read_text()
    assert "delta-remote" in dvc_pointer
    lakefs_pointer = (version_info.metadata_path.parent / "lakefs.json").read_text()
    assert "lakefs://main" in lakefs_pointer
