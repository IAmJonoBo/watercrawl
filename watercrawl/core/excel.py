"""Excel processing utilities for flight school data normalization and export."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd

from watercrawl.domain.models import (
    EnrichmentResult,
    SchoolRecord,
    normalize_province,
    normalize_status,
)

from . import config  # type: ignore
from .normalization import ColumnNormalizationRegistry, normalize_numeric_value

EXPECTED_COLUMNS = list(config.EXPECTED_COLUMNS)


class ExcelExporter:
    """Exports enriched dataframes to Excel and CSV artefacts."""

    def __init__(self, workbook_path: Path, provenance_path: Path):
        """Initialize the exporter with paths."""
        self.workbook_path = workbook_path
        self.provenance_path = provenance_path

    def write(self, enriched_df: pd.DataFrame, provenance_rows: Iterable[dict]) -> None:
        """Write the enriched dataframe and provenance to files."""
        self.workbook_path.parent.mkdir(parents=True, exist_ok=True)
        self.provenance_path.parent.mkdir(parents=True, exist_ok=True)

        with pd.ExcelWriter(self.workbook_path, engine="openpyxl") as writer:
            enriched_df.to_excel(writer, sheet_name=config.CLEANED_SHEET, index=False)

        pd.DataFrame(list(provenance_rows)).to_csv(self.provenance_path, index=False)


def read_dataset(
    path: Path,
    *,
    registry: ColumnNormalizationRegistry | None = None,
) -> pd.DataFrame:
    """Read and normalize a dataset from the given path."""
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        frame = pd.read_excel(path, sheet_name=config.CLEANED_SHEET)
    elif suffix == ".csv":
        frame = pd.read_csv(path)
    else:
        raise ValueError(f"Unsupported file format: {suffix}")

    active_registry = registry or getattr(config, "COLUMN_NORMALIZATION_REGISTRY", None)
    descriptors = getattr(config, "COLUMN_DESCRIPTORS", ())
    diagnostics: dict[str, Any] = {}
    normalized_columns: set[str] = set()

    if active_registry and descriptors:
        working = frame.copy()
        for descriptor in descriptors:
            if descriptor.name not in working.columns:
                continue
            result = active_registry.normalize_series(
                descriptor, working[descriptor.name]
            )
            working[descriptor.name] = result.series
            diagnostics[descriptor.name] = result.diagnostics.to_dict()
            normalized_columns.add(descriptor.name)
        frame = working

    remaining_rules: dict[str, dict[str, Any]] | None = None
    if active_registry is not None:
        remaining_rules = {
            name: rule
            for name, rule in active_registry.numeric_rules.items()
            if name not in normalized_columns
        }

    normalized = normalize_numeric_units(frame, rules=remaining_rules)
    normalized = normalize_categorical_values(
        normalized, skip_columns=normalized_columns
    )

    if diagnostics:
        report_path = config.INTERIM_DIR / "normalization_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(diagnostics, indent=2, sort_keys=True))

    return normalized


def write_dataset(df: pd.DataFrame, path: Path) -> None:
    """Write the dataframe to the given path."""
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
    """Load school records from the dataset at the given path."""
    df = read_dataset(path)
    missing = [col for col in EXPECTED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Missing expected columns: {missing}")
    return [SchoolRecord.from_dataframe_row(row) for _, row in df.iterrows()]


def append_enrichment_columns(
    df: pd.DataFrame, results: list[EnrichmentResult]
) -> pd.DataFrame:
    """Append enrichment columns to the dataframe."""
    enrichment_rows = [result.record.as_dict() for result in results]
    enrichment_df = pd.DataFrame(enrichment_rows)
    combined = pd.concat([df.reset_index(drop=True), enrichment_df], axis=1)
    return combined


def normalize_numeric_units(
    frame: pd.DataFrame,
    *,
    rules: dict[str, dict[str, Any]] | None = None,
) -> pd.DataFrame:
    """Normalize numeric units in the dataframe according to predefined rules."""

    normalized = frame.copy()
    rule_lookup = rules if rules is not None else dict(config.NUMERIC_UNIT_LOOKUP)
    if not rule_lookup:
        return normalized

    for column, rule in rule_lookup.items():
        if column not in normalized.columns:
            continue
        allowed_units = set(rule.get("allowed_units", set()))

        def _apply(value: Any) -> Any:
            return normalize_numeric_value(
                value=value,
                column=column,
                rule=rule,
                allowed_units=allowed_units,
            )

        normalized[column] = normalized[column].apply(_apply)

    return normalized


def normalize_categorical_values(
    frame: pd.DataFrame, *, skip_columns: Iterable[str] | None = None
) -> pd.DataFrame:
    """Normalize categorical values in the dataframe."""
    normalized = frame.copy()
    skip = set(skip_columns or ())
    if "Province" in normalized.columns and "Province" not in skip:
        normalized["Province"] = normalized["Province"].apply(normalize_province)
    if "Status" in normalized.columns and "Status" not in skip:
        normalized["Status"] = normalized["Status"].apply(normalize_status)
    return normalized
