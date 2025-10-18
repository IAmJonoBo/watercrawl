"""Excel processing utilities for flight school data normalization and export."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from numbers import Real
from pathlib import Path
from typing import Any

import pandas as pd
from pint import UnitRegistry
from pint.errors import DimensionalityError, RedefinitionError, UndefinedUnitError

from . import config  # type: ignore
from .models import (  # type: ignore
    EnrichmentResult,
    SchoolRecord,
    normalize_province,
    normalize_status,
)

EXPECTED_COLUMNS = [
    "Name of Organisation",
    "Province",
    "Status",
    "Website URL",
    "Contact Person",
    "Contact Number",
    "Contact Email Address",
]


UNIT_REGISTRY = UnitRegistry()
for definition in ("count = []", "plane = count", "planes = count", "aircraft = count"):
    try:
        UNIT_REGISTRY.define(definition)
    except (
        RedefinitionError
    ):  # pragma: no cover - ignore duplicate definitions during reloads
        continue


NUMERIC_UNIT_RULES: dict[str, dict[str, Any]] = {
    "Fleet Size": {
        "canonical_unit": "count",
        "cast": int,
        "allowed_units": {"count", "plane", "planes", "aircraft"},
    },
    "Runway Length": {
        "canonical_unit": "meter",
        "cast": float,
        "allowed_units": {"meter", "metre", "m", "foot", "feet", "ft"},
    },
    "Runway Length (m)": {
        "canonical_unit": "meter",
        "cast": float,
        "allowed_units": {"meter", "metre", "m"},
    },
}


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


def read_dataset(path: Path) -> pd.DataFrame:
    """Read and normalize a dataset from the given path."""
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        frame = pd.read_excel(path, sheet_name=config.CLEANED_SHEET)
    elif suffix == ".csv":
        frame = pd.read_csv(path)
    else:
        raise ValueError(f"Unsupported file format: {suffix}")

    normalized = normalize_numeric_units(frame)
    normalized = normalize_categorical_values(normalized)
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


def normalize_numeric_units(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize numeric units in the dataframe according to predefined rules."""
    normalized = frame.copy()
    # Cache allowed units for each rule
    allowed_units_cache = {}
    for column, rule in NUMERIC_UNIT_RULES.items():
        if column not in normalized.columns:
            continue
        if column not in allowed_units_cache:
            allowed_units_cache[column] = {
                str(UNIT_REGISTRY(unit).units)
                for unit in rule.get("allowed_units", set())
            }

        allowed_units = allowed_units_cache[column]
        normalized[column] = normalized[column].apply(
            _make_quantity_applier(column, rule, allowed_units)
        )
    return normalized


def _make_quantity_applier(column: str, rule: dict[str, Any], allowed_units: set[str]):
    """Create an applier function for normalizing quantities."""

    def apply_rule(value):
        return _normalize_quantity(value, column, rule, allowed_units)

    return apply_rule


def normalize_categorical_values(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize categorical values in the dataframe."""
    normalized = frame.copy()
    if "Province" in normalized.columns:
        normalized["Province"] = normalized["Province"].apply(normalize_province)
    if "Status" in normalized.columns:
        normalized["Status"] = normalized["Status"].apply(normalize_status)
    return normalized


def _normalize_quantity(
    value: Any, column: str, rule: dict[str, Any], allowed_units: set[str]
) -> Any:
    """Normalize a quantity value according to the given rule."""
    if _is_missing(value):
        return None

    canonical_unit = rule["canonical_unit"]
    quantity = _coerce_to_quantity(value, canonical_unit, column)

    if quantity is None:
        return None

    unit_name = str(quantity.units)  # type: ignore
    # If the parsed quantity is 'dimensionless', it means the value was numeric without a unit;
    # substitute the canonical unit so validation against allowed units works as expected.
    if unit_name == "dimensionless":
        unit_name = str(UNIT_REGISTRY(canonical_unit).units)
    if unit_name not in allowed_units:
        raise ValueError(f"{column} unit '{unit_name}' is not supported")

    try:
        converted = quantity.to(canonical_unit)  # type: ignore
    except DimensionalityError as exc:  # pragma: no cover - defensive safety
        raise ValueError(f"{column} value '{value}' has incompatible units") from exc

    magnitude = converted.magnitude
    caster = rule.get("cast", float)
    if caster is int:
        return int(round(magnitude))
    return caster(magnitude)


def _coerce_to_quantity(value: Any, canonical_unit: str, column: str) -> Any:
    """Coerce a value to a quantity with the canonical unit."""
    if isinstance(value, (int, float, Decimal)) and not _is_missing(value):
        return UNIT_REGISTRY.Quantity(value, canonical_unit)

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            quantity = UNIT_REGISTRY(text)
            if isinstance(quantity.magnitude, Real):
                return UNIT_REGISTRY.Quantity(quantity.magnitude, canonical_unit)
            return quantity
        except (UndefinedUnitError, ValueError):
            try:
                magnitude = float(text)
            except ValueError as exc:  # pragma: no cover - invalid literal
                raise ValueError(f"{column} value '{value}' is not a number") from exc
            return UNIT_REGISTRY.Quantity(magnitude, canonical_unit)

    raise ValueError(f"{column} value '{value}' is not supported")


def _is_missing(value: Any) -> bool:
    """Check if a value is missing or empty."""
    if isinstance(value, str):
        return not value.strip()
    return pd.isna(value)
