"""Declarative column normalisation registry and helpers."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from numbers import Real
from typing import Any, Callable, Iterable, Mapping, Protocol
from urllib.parse import urlparse, urlunparse

import pandas as pd
from pandas import Series
from pint import UnitRegistry
from pint.errors import DimensionalityError, RedefinitionError, UndefinedUnitError

from .profiles import ColumnDescriptor, NumericUnitRule

__all__ = [
    "ColumnNormalizationRegistry",
    "ColumnNormalizationResult",
    "ColumnDiagnostics",
    "NormalizationIssue",
    "build_default_registry",
    "build_numeric_rule_lookup",
    "normalize_numeric_value",
]


class PhoneNormalizer(Protocol):
    def __call__(self, raw: str | None) -> tuple[str | None, list[str]]: ...


class EmailValidator(Protocol):
    def __call__(
        self, email: str | None, organisation_domain: str | None
    ) -> tuple[str | None, list[str]]: ...


@dataclass(frozen=True)
class NormalizationIssue:
    """Issue encountered while normalising a value."""

    index: int
    message: str


@dataclass(frozen=True)
class ColumnDiagnostics:
    """Aggregate statistics for a normalised column."""

    column: str
    semantic_type: str
    total_rows: int
    null_count: int
    null_rate: float
    unique_count: int
    issue_count: int
    issues: Mapping[str, int]
    format_issue_rate: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "column": self.column,
            "semantic_type": self.semantic_type,
            "total_rows": self.total_rows,
            "null_count": self.null_count,
            "null_rate": self.null_rate,
            "unique_count": self.unique_count,
            "issue_count": self.issue_count,
            "format_issue_rate": self.format_issue_rate,
            "issues": dict(self.issues),
        }


@dataclass(frozen=True)
class ColumnNormalizationResult:
    """Result of applying a column normaliser."""

    series: Series
    diagnostics: ColumnDiagnostics


NormalizerCallable = Callable[
    [Series, ColumnDescriptor, "ColumnNormalizationRegistry"], ColumnNormalizationResult
]


class ColumnNormalizationRegistry:
    """Registry mapping semantic types to column normalisers."""

    def __init__(self) -> None:
        self._normalizers: dict[str, NormalizerCallable] = {}
        self.numeric_rules: dict[str, dict[str, Any]] = {}

    def register_type(self, semantic_type: str, normalizer: NormalizerCallable) -> None:
        self._normalizers[semantic_type.lower()] = normalizer

    def normalize_series(
        self, descriptor: ColumnDescriptor, series: Series
    ) -> ColumnNormalizationResult:
        normalizer = self._normalizers.get(descriptor.semantic_type.lower())
        if normalizer is None:
            normalizer = _text_normalizer
        return normalizer(series, descriptor, self)


def build_numeric_rule_lookup(
    numeric_rules: Iterable[NumericUnitRule],
) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for rule in numeric_rules:
        lookup[rule.column] = {
            "canonical_unit": rule.canonical_unit,
            "allowed_units": {str(unit) for unit in rule.allowed_units},
            "cast": rule.cast,
        }
    return lookup


UNIT_REGISTRY = UnitRegistry()
for definition in ("count = []", "plane = count", "planes = count", "aircraft = count"):
    try:
        UNIT_REGISTRY.define(definition)
    except RedefinitionError:  # pragma: no cover - reload safety
        continue


def build_default_registry(
    *,
    phone_normalizer: PhoneNormalizer | None = None,
    email_validator: EmailValidator | None = None,
) -> ColumnNormalizationRegistry:
    registry = ColumnNormalizationRegistry()
    registry.register_type("text", _text_normalizer)
    registry.register_type("string", _text_normalizer)
    registry.register_type("address", _address_normalizer)
    registry.register_type("enum", _enum_normalizer)
    registry.register_type("numeric", _numeric_normalizer)
    registry.register_type("numeric_with_units", _numeric_with_units_normalizer)
    registry.register_type("date", _date_normalizer)
    registry.register_type("url", _url_normalizer)
    if phone_normalizer is not None:
        registry.register_type("phone", _phone_normalizer(phone_normalizer))
    if email_validator is not None:
        registry.register_type("email", _email_normalizer(email_validator))
    return registry


def _text_normalizer(
    series: Series, descriptor: ColumnDescriptor, registry: ColumnNormalizationRegistry
) -> ColumnNormalizationResult:
    hints = {key.lower(): value for key, value in descriptor.format_hints.items()}
    collapse_whitespace = bool(hints.get("collapse_whitespace", True))
    strip_values = bool(hints.get("strip", True))
    case_hint = str(hints.get("case", "")).lower()
    normalized: list[Any] = []
    issues: list[NormalizationIssue] = []
    for index, value in series.items():
        text = _coerce_to_str(value)
        if text is None:
            if descriptor.required:
                issues.append(NormalizationIssue(int(index), "Missing required value"))
            normalized.append(None)
            continue
        if strip_values:
            text = text.strip()
        if collapse_whitespace:
            text = " ".join(text.split())
        if case_hint == "upper":
            text = text.upper()
        elif case_hint == "lower":
            text = text.lower()
        elif case_hint == "title":
            text = text.title()
        normalized.append(text)
    diagnostics = _build_diagnostics(descriptor, series.index, normalized, issues)
    return ColumnNormalizationResult(pd.Series(normalized, index=series.index), diagnostics)


def _address_normalizer(
    series: Series, descriptor: ColumnDescriptor, registry: ColumnNormalizationRegistry
) -> ColumnNormalizationResult:
    hints = {"case": "title"}
    hints.update(descriptor.format_hints)
    updated_descriptor = ColumnDescriptor(
        name=descriptor.name,
        semantic_type=descriptor.semantic_type,
        required=descriptor.required,
        allowed_values=descriptor.allowed_values,
        format_hints=hints,
    )
    return _text_normalizer(series, updated_descriptor, registry)


def _enum_normalizer(
    series: Series, descriptor: ColumnDescriptor, registry: ColumnNormalizationRegistry
) -> ColumnNormalizationResult:
    allowed_map = {value.lower(): value for value in descriptor.allowed_values}
    hints = {key.lower(): value for key, value in descriptor.format_hints.items()}
    default_value = hints.get("default")
    issues: list[NormalizationIssue] = []
    normalized: list[Any] = []
    for index, value in series.items():
        text = _coerce_to_str(value)
        if text is None:
            if descriptor.required:
                issues.append(NormalizationIssue(int(index), "Missing required value"))
            normalized.append(default_value)
            continue
        cleaned = text.strip()
        canonical = allowed_map.get(cleaned.lower())
        if canonical is None:
            issues.append(
                NormalizationIssue(int(index), f"Value '{cleaned}' not in allowed set")
            )
            normalized.append(default_value)
        else:
            normalized.append(canonical)
    diagnostics = _build_diagnostics(descriptor, series.index, normalized, issues)
    return ColumnNormalizationResult(pd.Series(normalized, index=series.index), diagnostics)


def _numeric_normalizer(
    series: Series, descriptor: ColumnDescriptor, registry: ColumnNormalizationRegistry
) -> ColumnNormalizationResult:
    hints = descriptor.format_hints
    cast_hint = str(hints.get("cast", "float")).lower()
    def _cast_to_int(value: float) -> int:
        return int(round(value))

    caster: Callable[[float], Any] = float
    if cast_hint == "int":
        caster = _cast_to_int
    issues: list[NormalizationIssue] = []
    normalized: list[Any] = []
    for index, value in series.items():
        if _is_missing(value):
            if descriptor.required:
                issues.append(NormalizationIssue(int(index), "Missing required value"))
            normalized.append(None)
            continue
        try:
            normalized.append(caster(float(value)))
        except (TypeError, ValueError):
            issues.append(
                NormalizationIssue(int(index), f"Unable to parse numeric value '{value}'")
            )
            normalized.append(None)
    diagnostics = _build_diagnostics(descriptor, series.index, normalized, issues)
    return ColumnNormalizationResult(pd.Series(normalized, index=series.index), diagnostics)


def _numeric_with_units_normalizer(
    series: Series, descriptor: ColumnDescriptor, registry: ColumnNormalizationRegistry
) -> ColumnNormalizationResult:
    rule = registry.numeric_rules.get(descriptor.name)
    if rule is None:
        return _numeric_normalizer(series, descriptor, registry)
    allowed_units = rule.get("_allowed_units_cache")
    if allowed_units is None:
        allowed_units = {
            str(UNIT_REGISTRY(unit).units) for unit in rule.get("allowed_units", set())
        }
        rule["_allowed_units_cache"] = allowed_units
    issues: list[NormalizationIssue] = []
    normalized: list[Any] = []
    for index, value in series.items():
        try:
            normalized_value = normalize_numeric_value(
                value=value,
                column=descriptor.name,
                rule=rule,
                allowed_units=allowed_units,
            )
        except ValueError as exc:
            issues.append(NormalizationIssue(int(index), str(exc)))
            normalized_value = None
        if normalized_value is None and descriptor.required:
            issues.append(NormalizationIssue(int(index), "Missing required value"))
        normalized.append(normalized_value)
    diagnostics = _build_diagnostics(descriptor, series.index, normalized, issues)
    return ColumnNormalizationResult(pd.Series(normalized, index=series.index), diagnostics)


def _date_normalizer(
    series: Series, descriptor: ColumnDescriptor, registry: ColumnNormalizationRegistry
) -> ColumnNormalizationResult:
    hints = {key.lower(): value for key, value in descriptor.format_hints.items()}
    input_formats = hints.get("input_formats") or []
    output_format = hints.get("output_format", "%Y-%m-%d")
    issues: list[NormalizationIssue] = []
    normalized: list[Any] = []
    for index, value in series.items():
        text = _coerce_to_str(value)
        if text is None:
            if descriptor.required:
                issues.append(NormalizationIssue(int(index), "Missing required value"))
            normalized.append(None)
            continue
        cleaned = text.strip()
        parsed: datetime | None = None
        formats = list(input_formats) if input_formats else ["%Y-%m-%d", "%d/%m/%Y"]
        for fmt in formats:
            try:
                parsed = datetime.strptime(cleaned, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            issues.append(
                NormalizationIssue(
                    int(index), f"Unable to parse date '{cleaned}' with known formats"
                )
            )
            normalized.append(None)
        else:
            normalized.append(parsed.strftime(str(output_format)))
    diagnostics = _build_diagnostics(descriptor, series.index, normalized, issues)
    return ColumnNormalizationResult(pd.Series(normalized, index=series.index), diagnostics)


def _url_normalizer(
    series: Series, descriptor: ColumnDescriptor, registry: ColumnNormalizationRegistry
) -> ColumnNormalizationResult:
    hints = {key.lower(): value for key, value in descriptor.format_hints.items()}
    ensure_https = bool(hints.get("ensure_https", True))
    strip_query = bool(hints.get("strip_query", True))
    strip_fragment = bool(hints.get("strip_fragment", True))
    strip_trailing = bool(hints.get("strip_trailing_slash", True))
    issues: list[NormalizationIssue] = []
    normalized: list[Any] = []
    for index, value in series.items():
        text = _coerce_to_str(value)
        if text is None:
            if descriptor.required:
                issues.append(NormalizationIssue(int(index), "Missing required value"))
            normalized.append(None)
            continue
        cleaned = text.strip()
        if not cleaned:
            normalized.append(None)
            continue
        if "://" not in cleaned:
            cleaned = ("https://" if ensure_https else "http://") + cleaned
        parsed = urlparse(cleaned)
        if not parsed.netloc:
            issues.append(
                NormalizationIssue(int(index), f"URL '{text}' is missing a hostname")
            )
            normalized.append(None)
            continue
        scheme = parsed.scheme.lower()
        if ensure_https:
            scheme = "https"
        netloc = parsed.netloc.lower()
        path = parsed.path or ""
        if strip_trailing:
            path = path.rstrip("/")
        query = "" if strip_query else parsed.query
        fragment = "" if strip_fragment else parsed.fragment
        rebuilt = urlunparse((scheme, netloc, path, parsed.params, query, fragment))
        normalized.append(rebuilt)
    diagnostics = _build_diagnostics(descriptor, series.index, normalized, issues)
    return ColumnNormalizationResult(pd.Series(normalized, index=series.index), diagnostics)


def _phone_normalizer(phone_normalizer: PhoneNormalizer) -> NormalizerCallable:
    def _normalizer(
        series: Series, descriptor: ColumnDescriptor, registry: ColumnNormalizationRegistry
    ) -> ColumnNormalizationResult:
        normalized: list[Any] = []
        issues: list[NormalizationIssue] = []
        for index, value in series.items():
            cleaned = _coerce_to_str(value)
            normalized_value, field_issues = phone_normalizer(cleaned)
            normalized.append(normalized_value)
            for issue in field_issues:
                issues.append(NormalizationIssue(int(index), issue))
        diagnostics = _build_diagnostics(descriptor, series.index, normalized, issues)
        return ColumnNormalizationResult(pd.Series(normalized, index=series.index), diagnostics)

    return _normalizer


def _email_normalizer(email_validator: EmailValidator) -> NormalizerCallable:
    def _normalizer(
        series: Series, descriptor: ColumnDescriptor, registry: ColumnNormalizationRegistry
    ) -> ColumnNormalizationResult:
        normalized: list[Any] = []
        issues: list[NormalizationIssue] = []
        for index, value in series.items():
            cleaned = _coerce_to_str(value)
            normalized_value, field_issues = email_validator(cleaned, None)
            normalized.append(normalized_value)
            for issue in field_issues:
                issues.append(NormalizationIssue(int(index), issue))
        diagnostics = _build_diagnostics(descriptor, series.index, normalized, issues)
        return ColumnNormalizationResult(pd.Series(normalized, index=series.index), diagnostics)

    return _normalizer


def normalize_numeric_value(
    *,
    value: Any,
    column: str,
    rule: Mapping[str, Any],
    allowed_units: set[str],
) -> Any:
    if _is_missing(value):
        return None
    canonical_unit = rule["canonical_unit"]
    quantity = _coerce_to_quantity(value, canonical_unit, column)
    if quantity is None:
        return None
    unit_name = str(getattr(quantity, "units", "dimensionless"))
    if unit_name == "dimensionless":
        unit_name = str(UNIT_REGISTRY(canonical_unit).units)
    if unit_name not in allowed_units:
        raise ValueError(f"{column} unit '{unit_name}' is not supported")
    try:
        converted = quantity.to(canonical_unit)
    except DimensionalityError as exc:
        raise ValueError(f"{column} value '{value}' has incompatible units") from exc
    magnitude = converted.magnitude
    caster = rule.get("cast", float)
    if caster is int:
        return int(round(magnitude))
    return caster(magnitude)


def _coerce_to_quantity(value: Any, canonical_unit: str, column: str) -> Any:
    if isinstance(value, (int, float, Decimal)) and not _is_missing(value):
        return UNIT_REGISTRY.Quantity(value, canonical_unit)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            quantity = UNIT_REGISTRY(text)
        except (UndefinedUnitError, ValueError):
            try:
                magnitude = float(text)
            except ValueError as exc:
                raise ValueError(f"{column} value '{value}' is not a number") from exc
            return UNIT_REGISTRY.Quantity(magnitude, canonical_unit)
        if hasattr(quantity, "magnitude"):
            magnitude = quantity.magnitude  # type: ignore[attr-defined]
            if isinstance(magnitude, Real):  # type: ignore[name-defined]
                if str(getattr(quantity, "units", "dimensionless")) == "dimensionless":
                    return UNIT_REGISTRY.Quantity(magnitude, canonical_unit)
                return quantity
            return quantity
        if isinstance(quantity, Real):  # type: ignore[name-defined]
            return UNIT_REGISTRY.Quantity(quantity, canonical_unit)
        raise ValueError(f"{column} value '{value}' is not supported")
    raise ValueError(f"{column} value '{value}' is not supported")


def _coerce_to_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        if not value.strip():
            return None
        return value
    if isinstance(value, (int, float, Decimal)):
        return str(value)
    return str(value)


def _is_missing(value: Any) -> bool:
    if isinstance(value, str):
        return not value.strip()
    return pd.isna(value)


def _build_diagnostics(
    descriptor: ColumnDescriptor,
    index: Iterable[Any],
    values: list[Any],
    issues: list[NormalizationIssue],
) -> ColumnDiagnostics:
    series = pd.Series(values, index=index, dtype=object)
    total = len(series)
    null_count = int(series.isna().sum())
    issue_counter = Counter(issue.message for issue in issues)
    non_null = total - null_count
    format_issue_rate = (sum(issue_counter.values()) / non_null) if non_null else 0.0
    return ColumnDiagnostics(
        column=descriptor.name,
        semantic_type=descriptor.semantic_type,
        total_rows=total,
        null_count=null_count,
        null_rate=(null_count / total) if total else 0.0,
        unique_count=int(series.nunique(dropna=True)),
        issue_count=sum(issue_counter.values()),
        issues=issue_counter,
        format_issue_rate=format_issue_rate,
    )
