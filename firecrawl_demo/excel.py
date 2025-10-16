"""Helpers for reading and writing the flight school workbook."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

import pandas as pd  # type: ignore[import-untyped]

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


def load_school_records(path: Path = config.SOURCE_XLSX) -> List[SchoolRecord]:
    """Load school records from the specified Excel file and return them as a list of SchoolRecord objects."""
    df = pd.read_excel(path, sheet_name=config.CLEANED_SHEET)
    missing = [col for col in EXPECTED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Missing expected columns: {missing}")
    records: List[SchoolRecord] = [SchoolRecord.from_row(row.to_dict()) for _, row in df.iterrows()]
    return records

def load_cleaned_dataframe(path: Path = config.SOURCE_XLSX) -> pd.DataFrame:
    """Return the cleaned worksheet as a DataFrame for downstream enrichment merges."""
    return pd.read_excel(path, sheet_name=config.CLEANED_SHEET)

def append_enrichment_columns(df: pd.DataFrame, results: List[EnrichmentResult]) -> pd.DataFrame:
    enrichment_rows = [result.as_dict() for result in results]
    enrichment_df = pd.DataFrame(enrichment_rows)
    # Add Analyst Feedback column if not present
    if "Analyst Feedback" not in df.columns:
        df["Analyst Feedback"] = ""
    combined = pd.concat([df.reset_index(drop=True), enrichment_df], axis=1)
    return combined

def write_outputs(
    enriched_df: pd.DataFrame,
    provenance_rows: Iterable[dict],
    *,
    workbook_path: Path = config.ENRICHED_XLSX,
    provenance_path: Path = config.PROVENANCE_CSV,
) -> None:
    workbook_path.parent.mkdir(parents=True, exist_ok=True)
    provenance_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
        enriched_df.to_excel(writer, sheet_name=config.CLEANED_SHEET, index=False)

    pd.DataFrame(list(provenance_rows)).to_csv(provenance_path, index=False)
