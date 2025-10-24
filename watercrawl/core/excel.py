"""Excel processing utilities for flight school data normalization and export."""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Mapping

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

_SUPPORTED_SUFFIXES = {".csv", ".xlsx", ".xls"}


def _column_key(name: str) -> str:
    return "".join(ch for ch in name.casefold() if ch.isalnum())


def _expand_input(target: Path) -> list[Path]:
    if target.is_dir():
        return [
            child
            for child in sorted(target.iterdir(), key=lambda item: item.name.lower())
            if child.is_file() and child.suffix.lower() in _SUPPORTED_SUFFIXES
        ]
    return [target]


def _collect_inputs(path_or_paths: Path | Sequence[Path]) -> list[Path]:
    inputs: list[Path] = []
    if isinstance(path_or_paths, Path):
        inputs.extend(_expand_input(path_or_paths))
    else:
        for entry in path_or_paths:
            inputs.extend(_expand_input(entry))
    return inputs


def _resolve_sheet_name(
    path: Path, sheet_map: Mapping[str, str] | None
) -> str:
    if not sheet_map:
        return config.CLEANED_SHEET
    for key in (str(path), path.name, path.stem):
        if key in sheet_map:
            return sheet_map[key]
    return config.CLEANED_SHEET


def _align_columns(
    frame: pd.DataFrame, descriptors: Sequence[Any]
) -> tuple[pd.DataFrame, set[str]]:
    # Late import to avoid circular dependency at module import time.
    from watercrawl.core.profiles import ColumnDescriptor

    if not descriptors:
        return frame, set()
    required_columns = set(getattr(config, "EXPECTED_COLUMNS", ()))
    alias_lookup: dict[str, str] = {}
    canonical_order: list[str] = []
    for descriptor in descriptors:
        if isinstance(descriptor, ColumnDescriptor):
            canonical_order.append(descriptor.name)
            alias_lookup[_column_key(descriptor.name)] = descriptor.name
            if descriptor.required:
                required_columns.add(descriptor.name)
            hints = descriptor.format_hints or {}
            for alias in hints.get("aliases", ()):  # type: ignore[call-arg]
                alias_lookup[_column_key(str(alias))] = descriptor.name
        else:
            name = getattr(descriptor, "name", None)
            if name:
                canonical_order.append(name)
                alias_lookup[_column_key(str(name))] = str(name)

    rename_map: dict[str, str] = {}
    for column in frame.columns:
        key = _column_key(str(column))
        canonical = alias_lookup.get(key)
        if canonical and canonical not in rename_map.values():
            rename_map[str(column)] = canonical

    aligned = frame.rename(columns=rename_map).copy()
    missing_columns: set[str] = set()
    for name in canonical_order:
        if name not in aligned.columns:
            aligned[name] = pd.NA
            if name in required_columns:
                missing_columns.add(name)

    ordered_columns = [name for name in canonical_order if name in aligned.columns]
    remaining = [col for col in aligned.columns if col not in ordered_columns]
    return aligned[ordered_columns + remaining], missing_columns


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
    path: Path | Sequence[Path],
    *,
    registry: ColumnNormalizationRegistry | None = None,
    sheet_map: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """Read and normalize a dataset from one or more paths."""

    input_paths = _collect_inputs(path)
    if not input_paths:
        raise ValueError("No supported dataset files were provided")

    descriptors = getattr(config, "COLUMN_DESCRIPTORS", ())
    frames: list[pd.DataFrame] = []
    source_rows: list[dict[str, Any]] = []
    missing_columns_global: set[str] = set()
    for input_path in input_paths:
        suffix = input_path.suffix.lower()
        sheet_name: str | None = None
        if suffix in {".xlsx", ".xls"}:
            sheet_name = _resolve_sheet_name(input_path, sheet_map)
            frame = pd.read_excel(input_path, sheet_name=sheet_name)
        elif suffix == ".csv":
            frame = pd.read_csv(input_path)
        else:
            raise ValueError(f"Unsupported file format: {suffix}")
        aligned, missing_columns = _align_columns(frame, descriptors)
        frames.append(aligned)
        if missing_columns:
            missing_columns_global.update(missing_columns)
        for local_index, row_index in enumerate(aligned.index):
            source_rows.append(
                {
                    "row": len(source_rows),
                    "path": str(input_path.resolve()),
                    "sheet": sheet_name,
                    "source_row": (
                        int(row_index)
                        if isinstance(row_index, (int, float)) and not pd.isna(row_index)
                        else str(row_index) if row_index is not None else None
                    ),
                    "local_index": local_index,
                }
            )

    combined = pd.concat(frames, ignore_index=True, sort=False)
    metadata_attrs: dict[str, Any] = {
        "source_rows": source_rows,
        "source_files": sorted({entry["path"] for entry in source_rows}),
    }
    if missing_columns_global:
        metadata_attrs["missing_columns"] = sorted(missing_columns_global)
    if sheet_map:
        metadata_attrs["sheet_overrides"] = dict(sheet_map)

    active_registry = registry or getattr(config, "COLUMN_NORMALIZATION_REGISTRY", None)
    diagnostics: dict[str, Any] = {}
    normalized_columns: set[str] = set()

    working_frame = combined
    if active_registry and descriptors:
        working = combined.copy()
        for descriptor in descriptors:
            if descriptor.name not in working.columns:
                continue
            result = active_registry.normalize_series(
                descriptor, working[descriptor.name]
            )
            working[descriptor.name] = result.series
            diagnostics[descriptor.name] = result.diagnostics.to_dict()
            normalized_columns.add(descriptor.name)
        working_frame = working

    remaining_rules: dict[str, dict[str, Any]] | None = None
    if active_registry is not None:
        remaining_rules = {
            name: rule
            for name, rule in active_registry.numeric_rules.items()
            if name not in normalized_columns
        }

    normalized = normalize_numeric_units(working_frame, rules=remaining_rules)
    normalized = normalize_categorical_values(
        normalized, skip_columns=normalized_columns
    )
    normalized.attrs.update(metadata_attrs)

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
    normalized.attrs.update(frame.attrs)
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
    normalized.attrs.update(frame.attrs)
    skip = set(skip_columns or ())
    if "Province" in normalized.columns and "Province" not in skip:
        normalized["Province"] = normalized["Province"].apply(normalize_province)
    if "Status" in normalized.columns and "Status" not in skip:
        normalized["Status"] = normalized["Status"].apply(normalize_status)
    return normalized
