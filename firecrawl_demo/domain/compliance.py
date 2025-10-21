"""Compliance helpers enforcing ACES Aerodynamics enrichment guardrails."""

import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import urlparse

from firecrawl_demo.core import config

from .models import EvidenceRecord

if TYPE_CHECKING:
    from firecrawl_demo.application.interfaces import EvidenceSink
else:  # pragma: no cover - runtime protocol for loose coupling

    class EvidenceSink(Protocol):
        def record(self, entries: Iterable[EvidenceRecord]) -> None: ...


try:  # pragma: no cover - optional dependency
    import dns.resolver
except ImportError:  # pragma: no cover - fallback path
    dns_resolver: Any = None
else:  # pragma: no cover - optional dependency
    # Use the dns.resolver module directly so exception types such as
    # NXDOMAIN remain accessible. The resolver module exposes a `resolve`
    # function with the same signature used throughout the codebase while
    # also exporting the typed exception classes that our callers expect to
    # catch. Instantiating Resolver() hides these attributes on the returned
    # object, leading to AttributeError when trying to access
    # ``resolver.NXDOMAIN`` under newer dnspython releases.
    dns_resolver = dns.resolver


_PHONE_RE = re.compile(config.PHONE_E164_REGEX)
_EMAIL_RE = re.compile(config.EMAIL_REGEX)
_ROLE_INBOX_RE = (
    re.compile(
        rf"^(?:{'|'.join(re.escape(prefix) for prefix in config.ROLE_INBOX_PREFIXES)})@",
        re.I,
    )
    if config.ROLE_INBOX_PREFIXES
    else None
)


def normalize_province(province: str | None) -> str:
    if not province:
        return "Unknown"
    cleaned = province.strip()
    for candidate in config.PROVINCES:
        if cleaned.lower() == candidate.lower():
            return candidate
    return "Unknown"


def canonical_domain(url: str | None) -> str | None:
    if not url:
        return None
    cleaned = url.strip()
    if not cleaned:
        return None
    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"
    parsed = urlparse(cleaned)
    host = parsed.hostname or ""
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def normalize_phone(raw_phone: str | None) -> tuple[str | None, list[str]]:
    if not raw_phone:
        return None, ["Phone missing"]
    digits = re.sub(r"\D", "", raw_phone)
    normalized: str | None = None
    stripped = raw_phone.strip()
    country_code = config.PHONE_COUNTRY_CODE
    country_digits = country_code.lstrip("+")
    national_length = config.PHONE_NATIONAL_NUMBER_LENGTH
    prefixes = [str(prefix).lstrip("+") for prefix in config.PHONE_NATIONAL_PREFIXES]

    def _normalize_local(local_digits: str) -> str | None:
        candidate = local_digits
        if national_length is not None:
            candidate = candidate[-national_length:]
            if len(candidate) != national_length:
                return None
        candidate = candidate.lstrip("0") if not national_length else candidate
        if national_length is None and not candidate:
            return None
        return f"+{country_digits}{candidate}"

    has_profile_prefix = False

    if stripped.startswith(country_code) and digits.startswith(country_digits):
        has_profile_prefix = True
        normalized = _normalize_local(digits[len(country_digits) :])
    elif digits.startswith(country_digits):
        has_profile_prefix = True
        normalized = _normalize_local(digits[len(country_digits) :])
    else:
        for prefix in prefixes:
            if digits.startswith(prefix):
                has_profile_prefix = True
                normalized = _normalize_local(digits[len(prefix) :])
                break

    issues: list[str] = []
    if not normalized or not _PHONE_RE.fullmatch(normalized):
        if not has_profile_prefix:
            issues.append(
                f"Phone must use the {country_code} country prefix or configured national prefixes"
            )
        issues.append(f"Phone is not in {country_code} E.164 format")
        return None, issues
    return normalized, issues


def validate_email(
    email: str | None, organisation_domain: str | None
) -> tuple[str | None, list[str]]:
    if not email:
        return None, ["Email missing"]
    cleaned = email.strip()
    issues: list[str] = []
    if not _EMAIL_RE.fullmatch(cleaned):
        issues.append("Email format invalid")
        return None, issues
    domain = cleaned.split("@", 1)[-1].lower()
    if (
        config.EMAIL_REQUIRE_DOMAIN_MATCH
        and organisation_domain
        and not domain.endswith(organisation_domain.lower())
    ):
        issues.append("Email domain does not match official domain")
    mx_issue = _check_mx_records(domain)
    if mx_issue:
        issues.append(mx_issue)
    if _ROLE_INBOX_RE and _ROLE_INBOX_RE.match(cleaned):
        issues.append("Role inbox used")
    return cleaned.lower(), issues


def _check_mx_records(domain: str) -> str | None:
    if not domain:
        return "Missing email domain"
    resolver = dns_resolver
    if resolver is None:  # pragma: no cover - depends on optional package
        return "MX lookup unavailable"
    try:
        answers = resolver.resolve(domain, "MX", lifetime=config.MX_LOOKUP_TIMEOUT)
        if not list(answers):
            return "No MX records found"
    except Exception as error:  # pragma: no cover - exercised via integration tests
        nxdomain_exc = getattr(resolver, "NXDOMAIN", None)
        if nxdomain_exc and isinstance(error, nxdomain_exc):
            return "Domain has no DNS records"

        no_nameservers_exc = getattr(resolver, "NoNameservers", None)
        if no_nameservers_exc and isinstance(error, no_nameservers_exc):
            return "MX lookup unavailable"

        transient_exceptions = tuple(
            exc
            for exc in (
                getattr(resolver, "NoAnswer", None),
                getattr(resolver, "Timeout", None),
            )
            if exc is not None
        )
        if transient_exceptions and isinstance(error, transient_exceptions):
            return "MX lookup failed"

        fallback_exc = getattr(resolver, "NoResolverConfiguration", None)
        if fallback_exc and isinstance(error, fallback_exc):
            return "MX lookup unavailable"

        raise
    return None


def determine_status(
    has_website: bool,
    has_named_contact: bool,
    phone_issues: Sequence[str],
    email_issues: Sequence[str],
    evidence_ok: bool,
) -> str:
    if not has_website or not evidence_ok:
        return "Needs Review"
    if email_issues:
        if any("Role inbox" in issue for issue in email_issues):
            return "Candidate"
        if any("MX" in issue or "Domain" in issue for issue in email_issues):
            return "Needs Review"
        return "Candidate"
    if phone_issues:
        return "Candidate"
    if not has_named_contact:
        return "Candidate"
    return "Verified"


def confidence_for_status(status: str, deductions: int) -> int:
    base = config.DEFAULT_CONFIDENCE_BY_STATUS.get(status, 50)
    penalty = min(deductions * 5, 30)
    return max(base - penalty, 0)


def evidence_entry(
    row_id: int,
    organisation: str,
    changes: str,
    sources: Sequence[str],
    notes: str,
    confidence: int,
) -> dict[str, str]:
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    # Enforce ≥2 sources and at least one official
    official_keywords = config.OFFICIAL_SOURCE_KEYWORDS or (".gov.za", "ac.za")
    official_present = any(any(k in s for k in official_keywords) for s in sources)
    if len(sources) < 2 or not official_present:
        notes = (
            (notes + "; Evidence shortfall: <2 sources or no official/regulatory.")
            if notes
            else "Evidence shortfall: <2 sources or no official/regulatory."
        )
    # Source freshness check (max age 12 months)
    # This is a stub: in real use, parse source dates if available
    # For now, just log a warning if any source contains 'archive' or 'wayback'
    if any("archive" in s or "wayback" in s for s in sources):
        notes = (notes + "; Source may be stale.") if notes else "Source may be stale."
    return {
        "RowID": str(row_id),
        "Organisation": organisation,
        "What changed": changes,
        "Sources": "; ".join(sources),
        "Notes": notes,
        "Timestamp": timestamp,
        "Confidence": str(confidence),
    }


def append_evidence_log(
    rows: Iterable[dict[str, str]],
    sink: EvidenceSink,
) -> None:
    """Normalise raw evidence rows and forward them to the provided sink."""

    entries = list(rows)
    if not entries:
        return

    evidence_rows: list[EvidenceRecord] = []
    for row in entries:
        try:
            row_id = int(row.get("RowID", "0") or 0)
        except ValueError:
            row_id = 0

        raw_sources = row.get("Sources", "")
        sources = [part.strip() for part in raw_sources.split(";") if part.strip()]

        try:
            confidence = int(row.get("Confidence", "0") or 0)
        except ValueError:
            confidence = 0

        timestamp_value = row.get("Timestamp")
        timestamp = None
        if isinstance(timestamp_value, str) and timestamp_value:
            try:
                timestamp = datetime.fromisoformat(timestamp_value)
            except ValueError:
                timestamp = None

        evidence_rows.append(
            EvidenceRecord(
                row_id=row_id,
                organisation=row.get("Organisation", ""),
                changes=row.get("What changed", ""),
                sources=sources,
                notes=row.get("Notes", ""),
                confidence=confidence,
                timestamp=timestamp or datetime.now(UTC),
            )
        )

    sink.record(evidence_rows)


def payload_hash(payload: dict[str, object]) -> str:
    serialised = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


def describe_changes(
    original: dict[str, str | None], enriched: dict[str, str | None]
) -> str:
    changes: list[str] = []
    for key, original_value in original.items():
        new_value = enriched.get(key)
        if original_value != new_value:
            changes.append(f"{key} updated")
    return ", ".join(changes) if changes else "No changes"


class ComplianceChecker:
    """Stub maintained for backward-compatible tests."""
