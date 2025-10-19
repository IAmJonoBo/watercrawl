from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    import pandas as pd

    _PANDAS_AVAILABLE = True
except ImportError:
    pd = None  # type: ignore
    _PANDAS_AVAILABLE = False

from firecrawl_demo.core import config

from .models import EXPECTED_COLUMNS, ValidationIssue, ValidationReport


@dataclass(frozen=True)
class DatasetValidator:
    """Validates input datasets for mandatory columns and value constraints."""

    def validate_dataframe(self, frame: Any) -> ValidationReport:
        issues: list[ValidationIssue] = []
        missing_columns = [col for col in EXPECTED_COLUMNS if col not in frame.columns]
        for column in missing_columns:
            issues.append(
                ValidationIssue(
                    code="missing_column",
                    message=f"Missing expected column: {column}",
                    column=column,
                )
            )

        if missing_columns:
            return ValidationReport(issues=issues, rows=len(frame))

        issues.extend(self._validate_provinces(frame))
        issues.extend(self._validate_statuses(frame))
        return ValidationReport(issues=issues, rows=len(frame))

    def _validate_provinces(self, frame: Any) -> list[ValidationIssue]:
        allowed = {province.lower(): province for province in config.PROVINCES}
        province_series = frame["Province"].fillna("")
        issues: list[ValidationIssue] = []
        for offset, (_, raw_value) in enumerate(province_series.items(), start=2):
            cleaned = str(raw_value).strip().lower()
            if cleaned and cleaned in allowed:
                continue
            if cleaned == "unknown" or not cleaned:
                continue
            issues.append(
                ValidationIssue(
                    code="invalid_province",
                    message=f"Province '{raw_value}' is not recognised",
                    row=offset,
                    column="Province",
                )
            )
        return issues

    def _validate_statuses(self, frame: Any) -> list[ValidationIssue]:
        allowed = {status.lower() for status in config.CANONICAL_STATUSES}
        issues: list[ValidationIssue] = []
        for offset, (_, raw_value) in enumerate(
            frame["Status"].fillna("").items(), start=2
        ):
            cleaned = str(raw_value).strip().lower()
            if not cleaned:
                issues.append(
                    ValidationIssue(
                        code="missing_status",
                        message="Status is empty",
                        row=offset,
                        column="Status",
                    )
                )
                continue
            if cleaned not in allowed:
                issues.append(
                    ValidationIssue(
                        code="invalid_status",
                        message=f"Status '{raw_value}' is not permitted",
                        row=offset,
                        column="Status",
                    )
                )
        return issues
