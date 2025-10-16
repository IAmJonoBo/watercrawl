from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from . import config
from .models import EnrichmentResult, SchoolRecord

EXPECTED_COLUMNS = [
    "Name of Organisation",
    "Province",
    "Status",
    "Website URL",
    "Contact Person",
    "Contact Number",
    "Contact Email Address",
]


class ExcelExporter:
    """Exports enriched dataframes to Excel and CSV artefacts."""

    def __init__(self, workbook_path: Path, provenance_path: Path):
        self.workbook_path = workbook_path
        self.provenance_path = provenance_path

    def write(self, enriched_df: pd.DataFrame, provenance_rows: Iterable[dict]) -> None:
        self.workbook_path.parent.mkdir(parents=True, exist_ok=True)
        self.provenance_path.parent.mkdir(parents=True, exist_ok=True)

        with pd.ExcelWriter(self.workbook_path, engine="openpyxl") as writer:
            enriched_df.to_excel(writer, sheet_name=config.CLEANED_SHEET, index=False)

        pd.DataFrame(list(provenance_rows)).to_csv(self.provenance_path, index=False)


def read_dataset(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, sheet_name=config.CLEANED_SHEET)
    if suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"Unsupported file format: {suffix}")


def write_dataset(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name=config.CLEANED_SHEET, index=False)
        return
    if suffix == ".csv":
        df.to_csv(path, index=False)
        return
    raise ValueError(f"Unsupported file format: {suffix}")


def load_school_records(path: Path = config.SOURCE_XLSX) -> list[SchoolRecord]:
    df = read_dataset(path)
    missing = [col for col in EXPECTED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Missing expected columns: {missing}")
    return [SchoolRecord.from_dataframe_row(row) for _, row in df.iterrows()]


def append_enrichment_columns(
    df: pd.DataFrame, results: list[EnrichmentResult]
) -> pd.DataFrame:
    enrichment_rows = [result.record.as_dict() for result in results]
    enrichment_df = pd.DataFrame(enrichment_rows)
    combined = pd.concat([df.reset_index(drop=True), enrichment_df], axis=1)
    return combined
