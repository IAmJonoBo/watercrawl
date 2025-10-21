"""Deterministic Deequ-style checks for curated flight-school datasets."""

from __future__ import annotations

import importlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pandas as pd

from .shared_config import canonical_contracts_config

# Detect PySpark for future JVM-backed integrations. The lightweight fallback
# below runs regardless of availability so Deequ gating remains active in
# environments that only ship the Python toolchain.
try:  # pragma: no cover - exercised in integration environments when PySpark ships
    importlib.import_module("pyspark")
    _PYSPARK_AVAILABLE = True
except ImportError:  # pragma: no cover - deterministic path in unit tests
    _PYSPARK_AVAILABLE = False

# Public flag indicating Deequ support is available. The fallback implementation
# means we always execute the checks even without PySpark.
DEEQU_AVAILABLE: Final[bool] = True

_PHONE_PATTERN = re.compile(r"^\+27\d{9}$")
_EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_HTTPS_PREFIX = "https://"
_MAX_FAILURE_EXAMPLES = 10


@dataclass(frozen=True)
class DeequContractResult:
    """Aggregate outcome returned by :func:`run_deequ_checks`."""

    success: bool
    check_count: int
    failures: int
    metrics: dict[str, Any]
    results: list[dict[str, Any]]


def _load_dataset(dataset_path: Path) -> pd.DataFrame:
    frame = pd.read_csv(
        dataset_path,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
    )
    for column in frame.columns:
        if frame[column].dtype == object:
            frame[column] = frame[column].astype(str).str.strip()
    return frame


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return round(numerator / denominator, 4)


def run_deequ_checks(dataset_path: Path) -> DeequContractResult:
    """Execute Deequ-inspired quality checks over *dataset_path*."""

    frame = _load_dataset(dataset_path)
    canonical = canonical_contracts_config()
    row_count = len(frame.index)
    metrics: dict[str, Any] = {
        "row_count": row_count,
        "pyspark_available": _PYSPARK_AVAILABLE,
    }
    results: list[dict[str, Any]] = []
    failure_count = 0

    def record(check: str, passed: bool, details: dict[str, Any]) -> None:
        nonlocal failure_count
        results.append({"check": check, "success": passed, "details": details})
        if not passed:
            failure_count += 1

    def ensure_column(column: str) -> pd.Series | None:
        if column not in frame.columns:
            record(
                f"column_presence:{column}",
                False,
                {"message": f"Column '{column}' is missing from dataset."},
            )
            metrics.setdefault("missing_columns", []).append(column)
            return None
        return frame[column]

    required_columns = [
        "Name of Organisation",
        "Province",
        "Status",
        "Website URL",
        "Contact Person",
        "Contact Number",
        "Contact Email Address",
        "Confidence",
    ]

    completeness_metrics: dict[str, float] = {}
    for column in required_columns:
        series = ensure_column(column)
        if series is None:
            completeness_metrics[column] = 0.0
            continue
        stripped = series.astype(str).str.strip()
        non_empty = stripped != ""
        completeness_metrics[column] = _ratio(int(non_empty.sum()), row_count)
        record(
            f"completeness:{column}",
            bool(non_empty.all()),
            {
                "non_empty_rows": int(non_empty.sum()),
                "total_rows": row_count,
            },
        )
    metrics["completeness"] = completeness_metrics

    status_series = ensure_column("Status")
    confidence_series = ensure_column("Confidence")
    email_series = ensure_column("Contact Email Address")
    phone_series = ensure_column("Contact Number")
    website_series = ensure_column("Website URL")
    name_series = ensure_column("Name of Organisation")

    if confidence_series is not None:
        numeric_confidence = pd.to_numeric(
            confidence_series, errors="coerce"
        ).fillna(math.nan)
        min_conf = canonical["evidence"]["minimum_confidence"]
        max_conf = canonical["evidence"]["maximum_confidence"]
        within_bounds = numeric_confidence.between(min_conf, max_conf, inclusive="both")
        metrics["confidence_within_bounds"] = {
            "min": min_conf,
            "max": max_conf,
            "ratio": _ratio(int(within_bounds.sum()), row_count),
        }
        failing_rows = frame.loc[~within_bounds.fillna(False), [
            "Name of Organisation",
            "Confidence",
        ]]
        record(
            "confidence_range",
            bool(within_bounds.all()),
            {
                "threshold": {"min": min_conf, "max": max_conf},
                "failures": failing_rows.head(_MAX_FAILURE_EXAMPLES).to_dict("records"),
            },
        )

    if status_series is not None and email_series is not None:
        verified_mask = status_series.str.casefold() == "verified"
        verified_total = int(verified_mask.sum())
        if verified_total:
            verified_emails = email_series[verified_mask].str.strip()
            email_present = verified_emails != ""
            email_valid = verified_emails.str.match(_EMAIL_PATTERN)
            metrics["verified_email_ratio"] = _ratio(int(email_present.sum()), verified_total)
            metrics["verified_email_valid_ratio"] = _ratio(
                int((email_present & email_valid).sum()), verified_total
            )
            missing_email = frame.loc[verified_mask & ~email_present, [
                "Name of Organisation",
                "Contact Email Address",
            ]]
            invalid_email = frame.loc[verified_mask & email_present & ~email_valid, [
                "Name of Organisation",
                "Contact Email Address",
            ]]
            record(
                "verified_email_present",
                bool(email_present.all()),
                {"missing": missing_email.head(_MAX_FAILURE_EXAMPLES).to_dict("records")},
            )
            record(
                "verified_email_format",
                bool(email_valid[verified_mask].all()),
                {"invalid": invalid_email.head(_MAX_FAILURE_EXAMPLES).to_dict("records")},
            )
        else:
            metrics["verified_email_ratio"] = 1.0
            metrics["verified_email_valid_ratio"] = 1.0

    if status_series is not None and phone_series is not None:
        verified_mask = status_series.str.casefold() == "verified"
        verified_total = int(verified_mask.sum())
        if verified_total:
            verified_phones = phone_series[verified_mask].str.strip()
            phone_present = verified_phones != ""
            phone_valid = verified_phones.str.match(_PHONE_PATTERN)
            metrics["verified_phone_ratio"] = _ratio(int(phone_present.sum()), verified_total)
            metrics["verified_phone_valid_ratio"] = _ratio(
                int((phone_present & phone_valid).sum()), verified_total
            )
            missing_phone = frame.loc[verified_mask & ~phone_present, [
                "Name of Organisation",
                "Contact Number",
            ]]
            invalid_phone = frame.loc[verified_mask & phone_present & ~phone_valid, [
                "Name of Organisation",
                "Contact Number",
            ]]
            record(
                "verified_phone_present",
                bool(phone_present.all()),
                {"missing": missing_phone.head(_MAX_FAILURE_EXAMPLES).to_dict("records")},
            )
            record(
                "verified_phone_format",
                bool(phone_valid[verified_mask].all()),
                {"invalid": invalid_phone.head(_MAX_FAILURE_EXAMPLES).to_dict("records")},
            )
        else:
            metrics["verified_phone_ratio"] = 1.0
            metrics["verified_phone_valid_ratio"] = 1.0

    if website_series is not None:
        stripped = website_series.astype(str).str.strip()
        non_empty = stripped != ""
        https_mask = stripped.str.startswith(_HTTPS_PREFIX)
        metrics["https_ratio"] = _ratio(int((~non_empty | https_mask).sum()), row_count)
        insecure_rows = frame.loc[non_empty & ~https_mask, [
            "Name of Organisation",
            "Website URL",
        ]]
        record(
            "https_required",
            bool((~non_empty | https_mask).all()),
            {"insecure": insecure_rows.head(_MAX_FAILURE_EXAMPLES).to_dict("records")},
        )

    if phone_series is not None:
        stripped = phone_series.astype(str).str.strip()
        non_empty = stripped != ""
        valid = stripped.str.match(_PHONE_PATTERN)
        metrics["phone_valid_ratio"] = _ratio(int((~non_empty | valid).sum()), row_count)
        invalid_rows = frame.loc[non_empty & ~valid, [
            "Name of Organisation",
            "Contact Number",
        ]]
        record(
            "phone_format",
            bool((~non_empty | valid).all()),
            {"invalid": invalid_rows.head(_MAX_FAILURE_EXAMPLES).to_dict("records")},
        )

    if email_series is not None:
        stripped = email_series.astype(str).str.strip()
        non_empty = stripped != ""
        valid = stripped.str.match(_EMAIL_PATTERN)
        metrics["email_valid_ratio"] = _ratio(int((~non_empty | valid).sum()), row_count)
        invalid_rows = frame.loc[non_empty & ~valid, [
            "Name of Organisation",
            "Contact Email Address",
        ]]
        record(
            "email_format",
            bool((~non_empty | valid).all()),
            {"invalid": invalid_rows.head(_MAX_FAILURE_EXAMPLES).to_dict("records")},
        )

    if name_series is not None:
        duplicates = frame.duplicated(subset=["Name of Organisation"], keep=False)
        metrics["duplicate_name_count"] = int(duplicates.sum())
        duplicate_rows = (
            frame.loc[duplicates, ["Name of Organisation", "Province", "Status"]]
            .head(_MAX_FAILURE_EXAMPLES)
            .to_dict("records")
        )
        record(
            "unique_name",
            not duplicates.any(),
            {"duplicates": duplicate_rows},
        )

    check_count = len(results)
    success = failure_count == 0
    return DeequContractResult(
        success=success,
        check_count=check_count,
        failures=failure_count,
        metrics=metrics,
        results=results,
    )
