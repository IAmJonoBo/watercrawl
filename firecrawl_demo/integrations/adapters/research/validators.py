from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Sequence

from firecrawl_demo.domain.compliance import canonical_domain, normalize_phone

from .connectors import ConnectorResult
from .core import ResearchFinding


class ValidationSeverity(Enum):
    """Severity levels for validation checks."""

    PASS = auto()
    WARN = auto()
    FAIL = auto()


@dataclass(frozen=True)
class ValidationCheck:
    """Result of an individual validation check."""

    name: str
    severity: ValidationSeverity
    detail: str


@dataclass(frozen=True)
class ValidationReport:
    """Aggregate cross-validation output."""

    base_confidence: int
    confidence_adjustment: int
    final_confidence: int
    checks: tuple[ValidationCheck, ...]
    contradictions: tuple[str, ...]


_LEADERSHIP_KEYWORDS = ("director", "chief", "head", "lead", "principal")


def cross_validate_findings(
    baseline: ResearchFinding, results: Sequence[ConnectorResult]
) -> ValidationReport:
    """Run heuristics across connector findings to score confidence."""

    base_confidence = baseline.confidence
    adjustment = 0
    checks: list[ValidationCheck] = []
    contradictions: list[str] = []

    checks.append(_phone_check(baseline, results))
    if checks[-1].severity is ValidationSeverity.PASS:
        adjustment += 5

    leader_check = _leadership_check(baseline, results)
    checks.append(leader_check)
    if leader_check.severity is ValidationSeverity.PASS:
        adjustment += 3

    domain_check = _domain_alignment_check(baseline, results, contradictions)
    checks.append(domain_check)
    if domain_check.severity is ValidationSeverity.PASS:
        adjustment += 4

    final_confidence = max(0, min(100, base_confidence + adjustment))

    return ValidationReport(
        base_confidence=base_confidence,
        confidence_adjustment=adjustment,
        final_confidence=final_confidence,
        checks=tuple(checks),
        contradictions=tuple(contradictions),
    )


def _phone_check(
    baseline: ResearchFinding, _: Sequence[ConnectorResult]
) -> ValidationCheck:
    if not baseline.contact_phone:
        return ValidationCheck(
            name="phone_e164",
            severity=ValidationSeverity.WARN,
            detail="No phone number supplied for validation.",
        )
    normalized, issues = normalize_phone(baseline.contact_phone)
    if normalized:
        return ValidationCheck(
            name="phone_e164",
            severity=ValidationSeverity.PASS,
            detail="Phone normalised to E.164 successfully.",
        )
    detail = "Unable to normalise phone number."
    if issues:
        if isinstance(issues, (list, tuple)):
            detail = "; ".join(str(item) for item in issues)
        else:
            detail = str(issues)
    return ValidationCheck(
        name="phone_e164",
        severity=ValidationSeverity.WARN,
        detail=detail,
    )


def _leadership_check(
    baseline: ResearchFinding, results: Sequence[ConnectorResult]
) -> ValidationCheck:
    person = baseline.contact_person
    if not person:
        for result in results:
            candidate = result.observation.contact_person
            if candidate:
                person = candidate
                break
    person = person or ""
    lowered = person.casefold()
    for keyword in _LEADERSHIP_KEYWORDS:
        if keyword in lowered:
            return ValidationCheck(
                name="leadership_title",
                severity=ValidationSeverity.PASS,
                detail="Leadership title contains senior keyword.",
            )
    severity = ValidationSeverity.WARN if person else ValidationSeverity.FAIL
    detail = (
        "Leadership contact missing."
        if not person
        else "Leadership title not recognised."
    )
    return ValidationCheck("leadership_title", severity, detail)


def _domain_alignment_check(
    baseline: ResearchFinding,
    results: Sequence[ConnectorResult],
    contradictions: list[str],
) -> ValidationCheck:
    website_domain = canonical_domain(baseline.website_url)
    email_domain: str | None = None
    if baseline.contact_email and "@" in baseline.contact_email:
        email_domain = baseline.contact_email.split("@", 1)[-1]

    connector_domains = {
        canonical_domain(result.observation.website_url)
        for result in results
        if result.observation.website_url
    }
    connector_domains.discard(None)

    if website_domain:
        connector_domains.add(website_domain)
    if len({domain for domain in connector_domains if domain}) > 1:
        contradictions.append(
            "Multiple website domains observed across connectors; investigate potential rebrands."
        )
    if website_domain and email_domain and email_domain.endswith(website_domain):
        return ValidationCheck(
            name="email_domain_alignment",
            severity=ValidationSeverity.PASS,
            detail="Email domain aligns with website domain.",
        )
    if website_domain and email_domain:
        contradictions.append(
            "Email domain differs from website domain; confirm legitimate inbox."
        )
        return ValidationCheck(
            name="email_domain_alignment",
            severity=ValidationSeverity.WARN,
            detail="Email domain mismatch detected.",
        )
    return ValidationCheck(
        name="email_domain_alignment",
        severity=ValidationSeverity.WARN,
        detail="Insufficient data to validate email domain alignment.",
    )


__all__ = [
    "ValidationCheck",
    "ValidationReport",
    "ValidationSeverity",
    "cross_validate_findings",
]
