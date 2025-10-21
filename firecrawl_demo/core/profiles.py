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
class DatasetProfile:
    """Dataset-level configuration for refinement."""

    expected_columns: tuple[str, ...]
    numeric_units: tuple[NumericUnitRule, ...] = ()


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


@dataclass(frozen=True)
class ResearchProfile:
    """Research helper queries to seed adapters."""

    queries: tuple[str, ...] = ()


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


def _load_dataset(payload: Mapping[str, Any]) -> DatasetProfile:
    expected_columns = payload.get("expected_columns") or []
    if not expected_columns:
        raise ProfileError("Dataset profiles require 'expected_columns'")
    numeric_payload = payload.get("numeric_units") or []
    numeric_units = tuple(_load_numeric_rule(rule) for rule in numeric_payload)
    return DatasetProfile(
        expected_columns=tuple(str(column) for column in expected_columns),
        numeric_units=numeric_units,
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
    return ComplianceProfile(
        default_confidence={str(k): int(v) for k, v in default_confidence.items()},
        min_evidence_sources=int(min_sources),
        official_source_keywords=keywords,
        evidence_queries=queries,
    )


def _load_research(payload: Mapping[str, Any]) -> ResearchProfile:
    queries = tuple(str(item) for item in payload.get("queries", ()))
    return ResearchProfile(queries=queries)


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
