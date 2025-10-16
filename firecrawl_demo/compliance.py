"""Compliance helpers enforcing ACES Aerodynamics enrichment guardrails."""

import csv
import hashlib
import json
import re
from datetime import datetime
from typing import Optional
from collections.abc import Iterable, Sequence
from urllib.parse import urlparse

from . import config

try:  # pragma: no cover - optional dependency
    import dns.resolver  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - fallback path
    dns_resolver = None  # type: ignore[assignment]
else:  # pragma: no cover - optional dependency
    dns_resolver = dns.resolver

_PHONE_RE = re.compile(r"^\+27\d{9}$")
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_ROLE_INBOX_RE = re.compile(r"^(?:info|sales|contact|enquiries|admin|support)@", re.I)


def normalize_province(province: Optional[str]) -> str:
    if not province:
        return "Unknown"
    cleaned = province.strip()
    for candidate in config.PROVINCES:
        if cleaned.lower() == candidate.lower():
            return candidate
    return "Unknown"


def canonical_domain(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    parsed = urlparse(url.strip())
    host = parsed.hostname or ""
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def normalize_phone(raw_phone: Optional[str]) -> tuple[Optional[str], list[str]]:
    if not raw_phone:
        return None, ["Phone missing"]
    digits = re.sub(r"\D", "", raw_phone)
    normalized: Optional[str]
    if digits.startswith("27") and len(digits) == 11:
        normalized = "+27" + digits[2:]
    elif digits.startswith("0") and len(digits) == 10:
        normalized = "+27" + digits[1:]
    elif digits.startswith("27") and len(digits) == 9:
        normalized = "+27" + digits[2:]
    elif raw_phone.startswith("+27") and len(digits) == 11:
        normalized = "+27" + digits[2:]
    else:
        normalized = None
        if len(digits) >= 9:
            normalized = "+27" + digits[-9:]
    issues: list[str] = []
    if not normalized or not _PHONE_RE.fullmatch(normalized):
        issues.append("Phone is not in +27 E.164 format")
        return None, issues
    return normalized, issues


def validate_email(
    email: Optional[str], organisation_domain: Optional[str]
) -> tuple[Optional[str], list[str]]:
    if not email:
        return None, ["Email missing"]
    cleaned = email.strip()
    issues: list[str] = []
    if not _EMAIL_RE.fullmatch(cleaned):
        issues.append("Email format invalid")
        return None, issues
    domain = cleaned.split("@", 1)[-1].lower()
    if organisation_domain and not domain.endswith(organisation_domain):
        issues.append("Email domain does not match official domain")
    mx_issue = _check_mx_records(domain)
    if mx_issue:
        issues.append(mx_issue)
    if _ROLE_INBOX_RE.match(cleaned):
        issues.append("Role inbox used")
    return cleaned.lower(), issues


def _check_mx_records(domain: str) -> Optional[str]:
    if not domain:
        return "Missing email domain"
    resolver = dns_resolver
    if resolver is None:  # pragma: no cover - depends on optional package
        return "MX lookup unavailable"
    try:
        answers = resolver.resolve(domain, "MX", lifetime=config.MX_LOOKUP_TIMEOUT)
        if not list(answers):
            return "No MX records found"
    except resolver.NXDOMAIN:  # type: ignore[attr-defined]
        return "Domain has no DNS records"
    except (resolver.NoAnswer, resolver.Timeout):  # type: ignore[attr-defined]
        return "MX lookup failed"
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
    timestamp = datetime.utcnow().isoformat(timespec="seconds")
    # Enforce ≥2 sources and at least one official
    official_keywords = [".gov.za", "caa.co.za", "ac.za", "org.za"]
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


def append_evidence_log(rows: Iterable[dict[str, str]]) -> None:
    path = config.EVIDENCE_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "RowID",
                "Organisation",
                "What changed",
                "Sources",
                "Notes",
                "Timestamp",
                "Confidence",
            ],
        )
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def payload_hash(payload: dict[str, object]) -> str:
    serialised = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


def describe_changes(
    original: dict[str, Optional[str]], enriched: dict[str, Optional[str]]
) -> str:
    changes: list[str] = []
    for key, original_value in original.items():
        new_value = enriched.get(key)
        if original_value != new_value:
            changes.append(f"{key} updated")
    return ", ".join(changes) if changes else "No changes"


class ComplianceChecker:
    """Stub maintained for backward-compatible tests."""

    pass
