from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from hypothesis.extra.pandas import column, data_frames, range_indexes

from watercrawl.core import config, excel


def test_excel_import():
    assert hasattr(excel, "ExcelExporter")


def _fleet_values() -> st.SearchStrategy[object]:
    base_int = st.integers(min_value=0, max_value=500)
    float_values = st.floats(
        min_value=0,
        max_value=500,
        allow_nan=False,
        allow_infinity=False,
    ).map(lambda value: f"{value:.2f}")
    return st.one_of(
        base_int,
        base_int.map(lambda value: f"{value} count"),
        base_int.map(lambda value: f"{value} planes"),
        float_values,
        st.none(),
        st.just(""),
    )


def _runway_values() -> st.SearchStrategy[object]:
    base_float = st.floats(
        min_value=50,
        max_value=5000,
        allow_nan=False,
        allow_infinity=False,
    )
    return st.one_of(
        base_float,
        base_float.map(lambda value: f"{value:.1f} meter"),
        base_float.map(lambda value: f"{value:.1f} m"),
        base_float.map(lambda value: f"{value:.1f} ft"),
        st.none(),
        st.just(""),
    )


def _province_values() -> st.SearchStrategy[object]:
    canonical = list(config.PROVINCES) + [
        province.upper() for province in config.PROVINCES
    ]
    return st.one_of(
        st.sampled_from(canonical), st.just("unknown"), st.none(), st.just("")
    )


def _status_values() -> st.SearchStrategy[object]:
    canonical = list(config.CANONICAL_STATUSES) + [
        status.upper() for status in config.CANONICAL_STATUSES
    ]
    return st.one_of(
        st.sampled_from(canonical), st.none(), st.just(""), st.just("invalid")
    )


def _spreadsheet_frames() -> st.SearchStrategy[pd.DataFrame]:
    return data_frames(
        columns=[
            column(
                "Name of Organisation",
                elements=st.from_regex(r"[A-Za-z][A-Za-z ]{0,29}", fullmatch=True),
            ),
            column("Province", elements=_province_values()),
            column("Status", elements=_status_values()),
            column(
                "Website URL",
                elements=st.one_of(st.none(), st.just("https://example.org")),
            ),
            column(
                "Contact Person", elements=st.one_of(st.none(), st.text(max_size=20))
            ),
            column(
                "Contact Number", elements=st.one_of(st.none(), st.just("+27115550010"))
            ),
            column(
                "Contact Email Address",
                elements=st.one_of(st.none(), st.just("info@example.org")),
            ),
            column("Fleet Size", elements=_fleet_values()),
            column("Runway Length", elements=_runway_values()),
            column(
                "Runway Length (m)",
                elements=st.one_of(
                    st.none(),
                    st.floats(min_value=0.0, max_value=5000.0, allow_nan=False),
                ),
            ),
        ],
        index=range_indexes(min_size=1, max_size=5),
    )


@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(frame=_spreadsheet_frames())
def test_read_dataset_normalizes_units_and_categories(
    tmp_path: Path, frame: pd.DataFrame
) -> None:
    dataset_path = tmp_path / "dataset.csv"
    frame.to_csv(dataset_path, index=False)

    normalized = excel.read_dataset(dataset_path)
    expected = excel.normalize_categorical_values(excel.normalize_numeric_units(frame))

    subset_columns = [
        column
        for column in (
            "Province",
            "Status",
            "Fleet Size",
            "Runway Length",
            "Runway Length (m)",
        )
        if column in normalized.columns
    ]
    pd.testing.assert_frame_equal(
        normalized[subset_columns], expected[subset_columns], check_dtype=False
    )

    provinces = set(normalized["Province"].dropna())
    assert provinces.issubset({*config.PROVINCES, "Unknown"})
    statuses = set(normalized["Status"].dropna())
    assert statuses.issubset(set(config.CANONICAL_STATUSES))

    if "Fleet Size" in normalized.columns:
        for value in normalized["Fleet Size"].tolist():
            if pd.isna(value):
                continue
            assert float(value).is_integer()
    if "Runway Length" in normalized.columns:
        for value in normalized["Runway Length"].tolist():
            if pd.isna(value):
                continue
            assert isinstance(float(value), float)


@settings(
    max_examples=8,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(frame=_spreadsheet_frames())
def test_load_school_records_contracts(tmp_path: Path, frame: pd.DataFrame) -> None:
    dataset_path = tmp_path / "records.csv"
    frame.to_csv(dataset_path, index=False)

    records = excel.load_school_records(dataset_path)
    assert {record.province for record in records}.issubset(
        {*config.PROVINCES, "Unknown"}
    )
    assert {record.status for record in records}.issubset(
        set(config.CANONICAL_STATUSES)
    )


def test_normalize_numeric_units_rejects_incompatible_units() -> None:
    frame = pd.DataFrame(
        [
            {
                "Name of Organisation": "Invalid",
                "Province": "Gauteng",
                "Status": "Verified",
                "Website URL": "https://example.org",
                "Contact Person": "Analyst",
                "Contact Number": "+27115550100",
                "Contact Email Address": "analyst@example.org",
                "Runway Length": "20 parsecs",
            }
        ]
    )

    with pytest.raises(ValueError):
        excel.normalize_numeric_units(frame)


def test_read_dataset_supports_excel_roundtrips(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        [
            {
                "Name of Organisation": "Example",
                "Province": "gauteng",
                "Status": "verified",
                "Website URL": "https://example.org",
                "Contact Person": "Analyst",
                "Contact Number": "+27115550111",
                "Contact Email Address": "analyst@example.org",
                "Fleet Size": "12 planes",
                "Runway Length": "100 ft",
                "Runway Length (m)": 30.48,
            }
        ]
    )
    dataset_path = tmp_path / "dataset.xlsx"
    frame.to_excel(dataset_path, sheet_name=config.CLEANED_SHEET, index=False)

    normalized = excel.read_dataset(dataset_path)

    assert normalized.loc[0, "Province"] == "Gauteng"
    assert normalized.loc[0, "Status"] == "Verified"
    assert normalized.loc[0, "Fleet Size"] == 12
    assert pytest.approx(normalized.loc[0, "Runway Length"], rel=1e-6) == 30.48


def test_read_dataset_tracks_missing_columns(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        [
            {
                "Name of Organisation": "Missing Email",
                "Province": "Gauteng",
                "Status": "Candidate",
                "Website URL": "https://example.org",
            }
        ]
    )
    dataset_path = tmp_path / "missing.csv"
    frame.to_csv(dataset_path, index=False)

    normalized = excel.read_dataset(dataset_path)

    missing_columns = set(normalized.attrs.get("missing_columns", ()))
    assert "Contact Email Address" in missing_columns
    assert pd.isna(normalized.loc[0, "Contact Email Address"])


def test_normalize_numeric_units_rejects_unsupported_type() -> None:
    frame = pd.DataFrame(
        [
            {
                "Name of Organisation": "Invalid",
                "Province": "Gauteng",
                "Status": "Verified",
                "Fleet Size": {"value": 10},
            }
        ]
    )

    with pytest.raises(ValueError):
        excel.normalize_numeric_units(frame)


def test_excel_exporter_creates_workbook_and_provenance(tmp_path: Path) -> None:
    exporter = excel.ExcelExporter(
        tmp_path / "exports" / "enriched.xlsx",
        tmp_path / "exports" / "provenance.csv",
    )
    frame = pd.DataFrame([{"Name of Organisation": "Example"}])

    exporter.write(frame, [{"source": "internal", "notes": "baseline"}])

    workbook_path = tmp_path / "exports" / "enriched.xlsx"
    provenance_path = tmp_path / "exports" / "provenance.csv"
    assert workbook_path.exists()
    assert provenance_path.exists()


def test_read_dataset_rejects_unsupported_extension(tmp_path: Path) -> None:
    payload = tmp_path / "dataset.txt"
    payload.write_text("invalid", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported file format"):
        excel.read_dataset(payload)


def test_write_dataset_rejects_unsupported_extension(tmp_path: Path) -> None:
    frame = pd.DataFrame([{"Name of Organisation": "Example"}])
    target = tmp_path / "dataset.json"

    with pytest.raises(ValueError, match="Unsupported file format"):
        excel.write_dataset(frame, target)


def test_load_school_records_requires_expected_columns(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.csv"
    pd.DataFrame([{"Name of Organisation": "Example"}]).to_csv(dataset, index=False)

    with pytest.raises(ValueError, match="Missing expected columns"):
        excel.load_school_records(dataset)


def test_normalize_numeric_units_handles_dimensionless_and_invalid() -> None:
    frame = pd.DataFrame(
        [
            {
                "Runway Length": "100",
                "Fleet Size": "5",
            }
        ]
    )
    normalized = excel.normalize_numeric_units(frame)
    assert normalized.loc[0, "Runway Length"] == pytest.approx(100.0, rel=1e-6)
    assert normalized.loc[0, "Fleet Size"] == 5

    with pytest.raises(ValueError):
        excel.normalize_numeric_units(pd.DataFrame([{"Runway Length": "not-a-number"}]))


def test_read_dataset_combines_multiple_inputs(tmp_path: Path) -> None:
    primary = pd.DataFrame(
        [
            {
                "Name of Organisation": "Primary Org",
                "Province": "Gauteng",
                "Status": "Candidate",
                "Website URL": "https://primary.example",  # type: ignore[assignment]
            }
        ]
    )
    secondary = pd.DataFrame(
        [
            {
                "Name of Organisation": "Secondary Org",
                "Province": "Western Cape",
                "Status": "Verified",
                "Website URL": "https://secondary.example",  # type: ignore[assignment]
            }
        ]
    )
    primary_path = tmp_path / "primary.csv"
    secondary_path = tmp_path / "secondary.csv"
    primary.to_csv(primary_path, index=False)
    secondary.to_csv(secondary_path, index=False)

    combined = excel.read_dataset([primary_path, secondary_path])

    assert len(combined) == 2
    assert set(combined["Name of Organisation"]) == {"Primary Org", "Secondary Org"}
    source_rows = combined.attrs.get("source_rows")
    assert isinstance(source_rows, list)
    assert {Path(entry["path"]).name for entry in source_rows} == {
        primary_path.name,
        secondary_path.name,
    }


def test_read_dataset_accepts_directory_inputs(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    csv_path = input_dir / "data.csv"
    xlsx_path = input_dir / "extra.xlsx"

    pd.DataFrame(
        [
            {
                "Name of Organisation": "Dir Org",
                "Province": "Free State",
                "Status": "Candidate",
            }
        ]
    ).to_csv(csv_path, index=False)
    pd.DataFrame(
        [
            {
                "Name of Organisation": "Workbook Org",
                "Province": "Limpopo",
                "Status": "Verified",
            }
        ]
    ).to_excel(xlsx_path, sheet_name=config.CLEANED_SHEET, index=False)

    combined = excel.read_dataset(input_dir)

    assert len(combined) == 2
    assert set(combined["Province"]) == {"Free State", "Limpopo"}


def test_read_dataset_sheet_map_overrides_default(tmp_path: Path) -> None:
    csv_path = tmp_path / "base.csv"
    xlsx_path = tmp_path / "mapped.xlsx"

    pd.DataFrame(
        [
            {
                "Name of Organisation": "Base Org",
                "Province": "Gauteng",
                "Status": "Candidate",
            }
        ]
    ).to_csv(csv_path, index=False)

    with pd.ExcelWriter(xlsx_path) as writer:
        pd.DataFrame(
            [
                {
                    "Name of Organisation": "Mapped Org",
                    "Province": "Northern Cape",
                    "Status": "Verified",
                }
            ]
        ).to_excel(writer, sheet_name="Custom", index=False)

    combined = excel.read_dataset(
        [csv_path, xlsx_path], sheet_map={xlsx_path.name: "Custom"}
    )

    assert "Mapped Org" in set(combined["Name of Organisation"])
    source_rows = combined.attrs.get("source_rows") or []
    entry = next(
        (item for item in source_rows if Path(item["path"]).name == xlsx_path.name),
        None,
    )
    assert entry is not None
    assert entry.get("sheet") == "Custom"


def test_read_dataset_supports_multiple_sheet_overrides(tmp_path: Path) -> None:
    workbook_path = tmp_path / "multi.xlsx"
    with pd.ExcelWriter(workbook_path) as writer:
        pd.DataFrame(
            [
                {
                    "Province": "Gauteng",
                    "Name of Organisation": "Sheet One",
                    "Status": "Candidate",
                }
            ]
        ).to_excel(writer, sheet_name="Primary", index=False)
        pd.DataFrame(
            [
                {
                    "Status": "Verified",
                    "Name of Organisation": "Sheet Two",
                    "Province": "Western Cape",
                }
            ]
        ).to_excel(writer, sheet_name="Archive", index=False)

    combined = excel.read_dataset(
        workbook_path,
        sheet_map={workbook_path.name: ("Primary", "Archive")},
    )

    assert len(combined) == 2
    assert set(combined["Name of Organisation"]) == {"Sheet One", "Sheet Two"}
    overrides = combined.attrs.get("sheet_overrides")
    assert overrides == {workbook_path.name: ["Primary", "Archive"]}
    rows = combined.attrs.get("source_rows")
    assert isinstance(rows, list)
    sheet_names = {entry.get("sheet") for entry in rows}
    assert sheet_names == {"Primary", "Archive"}
