from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from watercrawl.core.excel import EXPECTED_COLUMNS
from watercrawl.integrations.storage.lakehouse import (
    LakehouseConfig,
    LocalLakehouseWriter,
    restore_snapshot,
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


def test_local_lakehouse_writer_persists_snapshot(tmp_path: Path) -> None:
    config = LakehouseConfig(
        backend="filesystem",
        root_path=tmp_path,
        table_name="flight_schools",
    )
    writer = LocalLakehouseWriter(config)
    frame = _sample_frame()

    manifest = writer.write(run_id="run-001", dataframe=frame)

    assert manifest.table_uri.startswith(f"{config.backend}://")
    assert manifest.table_path.exists()
    assert manifest.manifest_path.exists()
    assert manifest.fingerprint
    manifest_payload = json.loads(manifest.manifest_path.read_text())
    assert manifest_payload["run_id"] == "run-001"
    assert manifest_payload["row_count"] == 1
    assert manifest_payload["fingerprint"] == manifest.fingerprint
    assert manifest_payload["environment"]["profile"] == "dev"
    if manifest.degraded:
        degraded_info = manifest_payload["artifacts"]["degraded"]
        assert degraded_info["reason"] in {
            "delta_engine_missing",
            "parquet_engine_missing",
        }
    else:
        assert manifest.format in {"delta", "parquet"}
        if manifest.format == "delta":
            assert manifest.extras.get("delta_version") is not None


def test_local_lakehouse_writer_falls_back_to_csv_when_parquet_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = LakehouseConfig(
        backend="delta",
        root_path=tmp_path,
        table_name="flight_schools",
    )
    writer = LocalLakehouseWriter(config)
    frame = _sample_frame()

    def _raise_import_error(*_: object, **__: object) -> None:
        raise ImportError("No parquet engine installed")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", _raise_import_error)

    with pytest.warns(UserWarning, match="pyarrow"):
        manifest = writer.write(run_id="run-002", dataframe=frame)

    assert manifest.format == "csv"
    assert manifest.degraded is True
    assert manifest.remediation is not None
    assert manifest.remediation is not None
    assert "Parquet" in manifest.remediation or "lakehouse" in manifest.remediation
    assert (manifest.table_path / "data.csv").exists()

    payload = json.loads(manifest.manifest_path.read_text())
    assert payload["artifacts"]["data"] == "data.csv"
    assert payload["artifacts"]["format"] == "csv"
    degraded_info = payload["artifacts"]["degraded"]
    assert degraded_info["reason"] in {"parquet_engine_missing", "delta_engine_missing"}
    assert (
        "pyarrow" in degraded_info["remediation"]
        or "lakehouse" in degraded_info["remediation"]
    )
    assert degraded_info["fallback_artifact"] == "data.csv"


def test_restore_snapshot_returns_latest_snapshot(tmp_path: Path) -> None:
    config = LakehouseConfig(
        backend="filesystem",
        root_path=tmp_path,
        table_name="flight_schools",
    )
    writer = LocalLakehouseWriter(config)
    frame = _sample_frame()

    manifest = writer.write(run_id="run-restore", dataframe=frame)

    restored_latest = restore_snapshot(
        table_name="flight_schools",
        root_path=tmp_path,
        backend="filesystem",
    )
    restored_specific = restore_snapshot(
        table_name="flight_schools",
        version=manifest.version,
        root_path=tmp_path,
        backend="filesystem",
    )

    pd.testing.assert_frame_equal(
        restored_latest[list(frame.columns)], frame, check_dtype=False
    )
    pd.testing.assert_frame_equal(
        restored_specific[list(frame.columns)], frame, check_dtype=False
    )
