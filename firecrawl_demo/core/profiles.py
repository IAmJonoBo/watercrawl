"""Profile loading utilities for white-labeled refinement workflows."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_CAST_FACTORIES: dict[str, Callable[[Any], Any]] = {
    "int": int,
    "float": float,
    "str": str,
}


class ProfileError(RuntimeError):
    """Raised when a refinement profile fails validation."""


@dataclass(frozen=True)
class NumericUnitRule:
    """Describe how to normalise a numeric column."""

    column: str
    canonical_unit: str
    allowed_units: tuple[str, ...]
    cast: Callable[[Any], Any]


@dataclass(frozen=True)
class ColumnDescriptor:
    """Declarative metadata describing how to normalise a dataset column."""

    name: str
    semantic_type: str = "text"
    required: bool = False
    allowed_values: tuple[str, ...] = ()
    format_hints: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DatasetProfile:
    """Dataset-level configuration for refinement."""

    expected_columns: tuple[str, ...]
    numeric_units: tuple[NumericUnitRule, ...] = ()
    columns: tuple[ColumnDescriptor, ...] = ()


@dataclass(frozen=True)
class PhoneProfile:
    """Phone normalisation rules."""

    country_code: str
    e164_regex: str
    national_prefixes: tuple[str, ...] = ()
    national_number_length: int | None = None


@dataclass(frozen=True)
class EmailProfile:
    """Email validation configuration."""

    regex: str
    role_prefixes: tuple[str, ...] = ()
    require_domain_match: bool = True


@dataclass(frozen=True)
class ContactProfile:
    """Aggregate contact validation rules."""

    phone: PhoneProfile
    email: EmailProfile


@dataclass(frozen=True)
class ComplianceProfile:
    """Compliance metadata controlling evidence heuristics."""

    default_confidence: Mapping[str, int]
    min_evidence_sources: int
    official_source_keywords: tuple[str, ...] = ()
    evidence_queries: tuple[str, ...] = ()
    lawful_basis: Mapping[str, str] = field(default_factory=dict)
    default_lawful_basis: str = "legitimate_interest"
    contact_purposes: Mapping[str, str] = field(default_factory=dict)
    default_contact_purpose: str = "transparency_notice"
    opt_out_statuses: tuple[str, ...] = ()
    revalidation_days: int = 90
    notification_templates: Mapping[str, str] = field(default_factory=dict)
    audit_exports: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResearchProfile:
    """Research helper queries to seed adapters."""

    queries: tuple[str, ...] = ()
    concurrency_limit: int = 4
    cache_ttl_hours: float | None = None
    max_retries: int = 3
    retry_backoff_base_seconds: float = 0.25
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_reset_seconds: float = 30.0
    allow_personal_data: bool = False
    rate_limit_seconds: float = 0.0
    connectors: Mapping[str, ConnectorSettings] = field(default_factory=dict)


@dataclass(frozen=True)
class ConnectorSettings:
    """Profile-level overrides for connector behaviour."""

    enabled: bool = True
    rate_limit_seconds: float | None = None
    allow_personal_data: bool | None = None


@dataclass(frozen=True)
class RefinementProfile:
    """Complete profile definition."""

    identifier: str
    name: str
    description: str
    dataset: DatasetProfile
    provinces: tuple[str, ...]
    statuses: tuple[str, ...]
    default_status: str
    compliance: ComplianceProfile
    contact: ContactProfile
    research: ResearchProfile = field(default_factory=ResearchProfile)


def _load_numeric_rule(payload: Mapping[str, Any]) -> NumericUnitRule:
    column = payload.get("column")
    canonical_unit = payload.get("canonical_unit")
    allowed_units = tuple(payload.get("allowed_units", ()))
    cast_name = payload.get("cast", "float")
    if not column or not canonical_unit:
        raise ProfileError(
            "Numeric unit rules require both 'column' and 'canonical_unit'"
        )
    try:
        cast_callable = _CAST_FACTORIES[cast_name]
    except KeyError as exc:
        raise ProfileError(
            f"Unsupported cast '{cast_name}' in numeric unit rule"
        ) from exc
    return NumericUnitRule(
        column=str(column),
        canonical_unit=str(canonical_unit),
        allowed_units=tuple(str(unit) for unit in allowed_units),
        cast=cast_callable,
    )


def _load_column_descriptor(payload: Mapping[str, Any]) -> ColumnDescriptor:
    name = payload.get("name")
    if not name:
        raise ProfileError("dataset.columns entries require a 'name'")
    semantic_type = str(payload.get("type", "text"))
    required = bool(payload.get("required", False))
    allowed_values = tuple(str(item) for item in payload.get("allowed_values", ()))
    hints_raw = payload.get("format_hints") or {}
    if hints_raw and not isinstance(hints_raw, Mapping):
        raise ProfileError("dataset.columns.format_hints must be a mapping if provided")
    format_hints = {str(key): value for key, value in dict(hints_raw).items()}
    return ColumnDescriptor(
        name=str(name),
        semantic_type=semantic_type,
        required=required,
        allowed_values=allowed_values,
        format_hints=format_hints,
    )


def _load_dataset(payload: Mapping[str, Any]) -> DatasetProfile:
    expected_columns_raw = payload.get("expected_columns")
    if expected_columns_raw is None:
        expected_columns: list[str] = []
    else:
        expected_columns = [str(column) for column in expected_columns_raw]
    numeric_payload = payload.get("numeric_units") or []
    numeric_units = tuple(_load_numeric_rule(rule) for rule in numeric_payload)
    columns_payload = payload.get("columns") or []
    columns = tuple(
        _load_column_descriptor(descriptor)
        for descriptor in columns_payload
        if isinstance(descriptor, Mapping)
    )
    if not expected_columns and columns:
        expected_columns = [descriptor.name for descriptor in columns]
    elif expected_columns and columns:
        declared = {descriptor.name for descriptor in columns}
        missing = [column for column in expected_columns if column not in declared]
        if missing:
            raise ProfileError(
                "dataset.expected_columns must match dataset.columns names; missing "
                + ", ".join(missing)
            )
        expected_columns = [descriptor.name for descriptor in columns]
    if not expected_columns:
        raise ProfileError(
            "Dataset profiles require either 'expected_columns' or 'columns'"
        )
    return DatasetProfile(
        expected_columns=tuple(str(column) for column in expected_columns),
        numeric_units=numeric_units,
        columns=columns,
    )


def _load_phone(payload: Mapping[str, Any]) -> PhoneProfile:
    country_code = payload.get("country_code")
    regex = payload.get("e164_regex")
    if not country_code or not regex:
        raise ProfileError("Phone profile requires 'country_code' and 'e164_regex'")
    prefixes = tuple(str(item) for item in payload.get("national_prefixes", ()))
    length = payload.get("national_number_length")
    return PhoneProfile(
        country_code=str(country_code),
        e164_regex=str(regex),
        national_prefixes=prefixes,
        national_number_length=int(length) if length is not None else None,
    )


def _load_email(payload: Mapping[str, Any]) -> EmailProfile:
    regex = payload.get("regex")
    if not regex:
        raise ProfileError("Email profile requires 'regex'")
    prefixes = tuple(str(item) for item in payload.get("role_prefixes", ()))
    require_domain = bool(payload.get("require_domain_match", True))
    return EmailProfile(
        regex=str(regex),
        role_prefixes=prefixes,
        require_domain_match=require_domain,
    )


def _load_contact(payload: Mapping[str, Any]) -> ContactProfile:
    phone = payload.get("phone") or {}
    email = payload.get("email") or {}
    return ContactProfile(
        phone=_load_phone(phone),
        email=_load_email(email),
    )


def _load_compliance(payload: Mapping[str, Any]) -> ComplianceProfile:
    default_confidence = payload.get("default_confidence") or {}
    if not default_confidence:
        raise ProfileError("Compliance profile requires 'default_confidence'")
    min_sources = payload.get("min_evidence_sources")
    if min_sources is None:
        raise ProfileError("Compliance profile requires 'min_evidence_sources'")
    keywords = tuple(str(item) for item in payload.get("official_source_keywords", ()))
    queries = tuple(str(item) for item in payload.get("evidence_queries", ()))
    lawful_basis_raw = payload.get("lawful_basis") or {}
    lawful_basis = {str(key): str(value) for key, value in lawful_basis_raw.items()}
    default_lawful_basis = str(
        payload.get("default_lawful_basis")
        or (next(iter(lawful_basis.keys()), "legitimate_interest"))
    )
    contact_purposes_raw = payload.get("contact_purposes") or {}
    contact_purposes = {
        str(key): str(value) for key, value in contact_purposes_raw.items()
    }
    default_contact_purpose = str(
        payload.get("default_contact_purpose")
        or (next(iter(contact_purposes.keys()), "transparency_notice"))
    )
    opt_out_statuses = tuple(str(item) for item in payload.get("opt_out_statuses", ()))
    revalidation_days = int(payload.get("revalidation_days", 90))
    notification_templates_raw = payload.get("notification_templates") or {}
    notification_templates = {
        str(key): str(value) for key, value in notification_templates_raw.items()
    }
    audit_exports = tuple(str(item) for item in payload.get("audit_exports", ()))
    return ComplianceProfile(
        default_confidence={str(k): int(v) for k, v in default_confidence.items()},
        min_evidence_sources=int(min_sources),
        official_source_keywords=keywords,
        evidence_queries=queries,
        lawful_basis=lawful_basis,
        default_lawful_basis=default_lawful_basis,
        contact_purposes=contact_purposes,
        default_contact_purpose=default_contact_purpose,
        opt_out_statuses=opt_out_statuses,
        revalidation_days=revalidation_days,
        notification_templates=notification_templates,
        audit_exports=audit_exports,
    )


def _load_connector(payload: Mapping[str, Any]) -> ConnectorSettings:
    rate_limit = payload.get("rate_limit_seconds")
    rate_limit_seconds = float(rate_limit) if rate_limit is not None else None
    allow_personal = payload.get("allow_personal_data")
    if allow_personal is not None:
        allow_personal = bool(allow_personal)
    return ConnectorSettings(
        enabled=bool(payload.get("enabled", True)),
        rate_limit_seconds=rate_limit_seconds,
        allow_personal_data=allow_personal,
    )


def _load_research(payload: Mapping[str, Any]) -> ResearchProfile:
    queries = tuple(str(item) for item in payload.get("queries", ()))
    concurrency_limit = int(payload.get("concurrency_limit", 4) or 1)
    cache_ttl = payload.get("cache_ttl_hours")
    ttl_value: float | None
    if cache_ttl is None:
        ttl_value = None
    else:
        ttl_value = float(cache_ttl)
        if ttl_value < 0:
            raise ProfileError("research.cache_ttl_hours must be non-negative")
    max_retries = int(payload.get("max_retries", 3) or 0)
    retry_backoff_base = float(payload.get("retry_backoff_base_seconds", 0.25) or 0.0)
    breaker_payload = payload.get("circuit_breaker") or {}
    failure_threshold = int(breaker_payload.get("failure_threshold", 5) or 1)
    reset_seconds = float(breaker_payload.get("reset_seconds", 30.0) or 0.0)

    if concurrency_limit < 1:
        raise ProfileError("research.concurrency_limit must be at least 1")
    if max_retries < 0:
        raise ProfileError("research.max_retries cannot be negative")
    if retry_backoff_base < 0:
        raise ProfileError("research.retry_backoff_base_seconds must be non-negative")
    if failure_threshold < 1:
        raise ProfileError(
            "research.circuit_breaker.failure_threshold must be at least 1"
        )
    if reset_seconds < 0:
        raise ProfileError(
            "research.circuit_breaker.reset_seconds must be non-negative"
        )

    allow_personal = bool(payload.get("allow_personal_data", False))
    rate_limit = float(payload.get("rate_limit_seconds", 0.0) or 0.0)
    connectors_payload = payload.get("connectors") or {}
    connectors = {
        str(name): _load_connector(payload)
        for name, payload in connectors_payload.items()
        if isinstance(payload, Mapping)
    }

    return ResearchProfile(
        queries=queries,
        concurrency_limit=concurrency_limit,
        cache_ttl_hours=ttl_value,
        max_retries=max_retries,
        retry_backoff_base_seconds=retry_backoff_base,
        circuit_breaker_failure_threshold=failure_threshold,
        circuit_breaker_reset_seconds=reset_seconds,
        allow_personal_data=allow_personal,
        rate_limit_seconds=rate_limit,
        connectors=connectors,
    )


def load_profile(profile_path: Path) -> RefinementProfile:
    """Load a refinement profile from disk."""

    if not profile_path.exists():
        raise ProfileError(f"Profile file not found: {profile_path}")
    with profile_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}

    identifier = payload.get("id")
    name = payload.get("name")
    description = payload.get("description", "")
    if not identifier or not name:
        raise ProfileError("Profiles require both 'id' and 'name'")
    dataset = _load_dataset(payload.get("dataset") or {})
    geography = payload.get("geography") or {}
    provinces = tuple(str(item) for item in geography.get("provinces", ()))
    if not provinces:
        raise ProfileError(
            "Profiles require at least one province in geography.provinces"
        )
    statuses_payload = payload.get("statuses") or {}
    statuses = tuple(str(item) for item in statuses_payload.get("allowed", ()))
    if not statuses:
        raise ProfileError("Profiles require statuses.allowed entries")
    default_status = str(statuses_payload.get("default") or statuses[0])
    compliance = _load_compliance(payload.get("compliance") or {})
    contact = _load_contact(payload.get("contact") or {})
    research = _load_research(payload.get("research") or {})
    return RefinementProfile(
        identifier=str(identifier),
        name=str(name),
        description=str(description),
        dataset=dataset,
        provinces=provinces,
        statuses=statuses,
        default_status=default_status,
        compliance=compliance,
        contact=contact,
        research=research,
    )


def discover_profile(project_root: Path, profile_id: str) -> Path:
    """Resolve profile file path from an identifier."""

    candidate = project_root / "profiles" / f"{profile_id}.yaml"
    if candidate.exists():
        return candidate
    raise ProfileError(f"Unable to locate profile '{profile_id}' in {candidate.parent}")
