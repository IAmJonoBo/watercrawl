"""Row-level processing for enrichment pipeline.

This module isolates the transformation, sanity checks, and quality gate
evaluation performed on each row so the orchestration layer can focus on
DataFrame coordination. All helpers here avoid mutating the surrounding
DataFrame and instead return structured artefacts that downstream callers can
apply in bulk.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any
from urllib.parse import urlparse

from watercrawl.application.compliance_review import (
    ComplianceReview,
    ComplianceReviewOutcome,
)
from watercrawl.application.quality import (
    QualityFinding,
    QualityGate,
    QualityGateDecision,
)
from watercrawl.domain.compliance import (
    canonical_domain,
    confidence_for_status,
    determine_status,
    normalize_phone,
    validate_email,
)
from watercrawl.domain.models import (
    EvidenceRecord,
    QualityIssue,
    RollbackAction,
    SanityCheckFinding,
    SchoolRecord,
)
from watercrawl.integrations.adapters.research import ResearchFinding

_OFFICIAL_KEYWORDS = (".gov.za", "caa.co.za", ".ac.za", ".org.za", ".mil.za")


@dataclass(slots=True)
class RowProcessingRequest:
    row_id: int
    original_row: Mapping[str, Any]
    original_record: SchoolRecord
    working_record: SchoolRecord
    finding: ResearchFinding


@dataclass(slots=True)
class RowProcessingResult:
    row_id: int
    proposed_record: SchoolRecord
    record: SchoolRecord
    updated: bool
    sources: list[str]
    sanity_findings: list[SanityCheckFinding]
    sanity_notes: list[str]
    cleared_columns: list[str]
    changed_columns: dict[str, tuple[str | None, str | None]]
    evidence_record: EvidenceRecord | None
    quality_issues: list[QualityIssue]
    rollback_action: RollbackAction | None
    quality_rejected: bool
    decision: QualityGateDecision | None
    compliance: ComplianceReviewOutcome | None = None
    follow_up_records: list[EvidenceRecord] = field(default_factory=list)


def process_row(
    request: RowProcessingRequest, *, quality_gate: QualityGate
) -> RowProcessingResult:
    """Process a single row and return the proposed record and artefacts."""

    original_record = request.original_record
    proposed_record = replace(request.working_record)
    finding = request.finding

    sources = merge_sources(proposed_record, finding)
    (
        total_source_count,
        fresh_source_count,
        official_source_count,
        official_fresh_source_count,
    ) = summarize_sources(original_record=original_record, merged_sources=sources)

    if finding.website_url:
        proposed_url = finding.website_url.strip()
        current_url = (proposed_record.website_url or "").strip()
        current_domain = canonical_domain(current_url) if current_url else None
        proposed_domain = canonical_domain(proposed_url)
        if (
            not current_url
            or (proposed_domain and proposed_domain != current_domain)
            or proposed_url.lower() != current_url.lower()
        ):
            proposed_record.website_url = proposed_url

    if not proposed_record.contact_person and finding.contact_person:
        proposed_record.contact_person = finding.contact_person

    previous_phone = proposed_record.contact_number
    phone_candidate = finding.contact_phone or proposed_record.contact_number
    normalized_phone, phone_issues = normalize_phone(phone_candidate)
    if normalized_phone and normalized_phone != proposed_record.contact_number:
        proposed_record.contact_number = normalized_phone
    elif not normalized_phone and proposed_record.contact_number:
        proposed_record.contact_number = None

    previous_email = proposed_record.contact_email
    email_candidate = finding.contact_email or proposed_record.contact_email
    validated_email, email_issues = validate_email(
        email_candidate, canonical_domain(proposed_record.website_url)
    )
    filtered_email_issues = [
        issue for issue in email_issues if issue != "MX lookup unavailable"
    ]
    if validated_email and validated_email != proposed_record.contact_email:
        proposed_record.contact_email = validated_email
    elif not validated_email and proposed_record.contact_email:
        proposed_record.contact_email = None

    has_named_contact = bool(proposed_record.contact_person)
    has_official_source = official_source_count > 0
    has_multiple_sources = total_source_count >= 2
    status = determine_status(
        bool(proposed_record.website_url),
        has_named_contact,
        phone_issues,
        filtered_email_issues,
        has_multiple_sources,
    )
    if status != proposed_record.status:
        proposed_record.status = status

    sanity_result = run_sanity_checks(
        record=proposed_record,
        row_id=request.row_id,
        sources=sources,
        phone_issues=phone_issues,
        email_issues=filtered_email_issues,
        previous_phone=previous_phone,
        previous_email=previous_email,
    )

    changed_columns = dict(collect_changed_columns(original_record, proposed_record))
    decision: QualityGateDecision | None = None
    quality_issues: list[QualityIssue] = []
    rollback_action: RollbackAction | None = None
    quality_rejected = False
    final_record = proposed_record
    evidence_confidence: int | None = None
    evidence_notes_parts: list[str] = []

    if changed_columns:
        decision = quality_gate.evaluate(
            original=original_record,
            proposed=proposed_record,
            finding=finding,
            changed_columns=changed_columns,
            phone_issues=phone_issues,
            email_issues=filtered_email_issues,
            total_source_count=total_source_count,
            fresh_source_count=fresh_source_count,
            official_source_count=official_source_count,
            official_fresh_source_count=official_fresh_source_count,
        )

    if decision and not decision.accepted:
        quality_rejected = True
        quality_issues = [
            quality_issue_from_finding(
                row_id=request.row_id,
                organisation=original_record.name,
                finding=finding_detail,
            )
            for finding_detail in decision.findings
        ]
        rollback_action = build_rollback_action(
            row_id=request.row_id,
            organisation=original_record.name,
            attempted_changes=changed_columns,
            issues=quality_issues,
        )
        fallback_record = decision.fallback_record or replace(
            original_record, status="Needs Review"
        )
        final_record = fallback_record
        rejection_reason = format_quality_rejection_reason(quality_issues)
        attempted_changes_text = describe_changes(request.original_row, proposed_record)
        notes = compose_quality_rejection_notes(
            rejection_reason,
            attempted_changes_text,
            decision.findings,
            sanity_result.notes,
        )
        evidence_notes_parts.append(notes)
        evidence_confidence = 0
    elif changed_columns:
        evidence_confidence = finding.confidence or confidence_for_status(
            proposed_record.status, len(phone_issues) + len(filtered_email_issues)
        )
        evidence_notes_parts.append(
            compose_evidence_notes(
                finding,
                request.original_row,
                proposed_record,
                has_official_source=has_official_source,
                total_source_count=total_source_count,
                fresh_source_count=fresh_source_count,
                sanity_notes=sanity_result.notes,
            )
        )

    raw_mx_failures = request.original_row.get("MX Failure Count")
    previous_mx_failures = 0
    if raw_mx_failures is not None:
        try:
            previous_mx_failures = int(raw_mx_failures)
        except (TypeError, ValueError):  # pragma: no cover - defensive parsing
            previous_mx_failures = 0

    raw_opt_out = str(request.original_row.get("Opt-out Status", ""))
    opt_out_flag = original_record.status == "Do Not Contact (Compliance)" or (
        raw_opt_out.strip().lower() in {"1", "true", "yes", "opt-out", "suppressed"}
    )

    reviewer = ComplianceReview()
    compliance_outcome = reviewer.review(
        row_id=request.row_id,
        organisation=final_record.name or original_record.name,
        record=final_record,
        finding=finding,
        sources=sanity_result.normalized_sources,
        changed_columns=changed_columns,
        phone_issues=phone_issues,
        email_issues=filtered_email_issues,
        previous_mx_failures=previous_mx_failures,
        opt_out_flag=opt_out_flag,
    )

    follow_up_records = list(compliance_outcome.follow_up_records)
    if (
        compliance_outcome.downgraded_status
        and final_record.status != compliance_outcome.downgraded_status
    ):
        previous_status = final_record.status
        final_record = replace(
            final_record, status=compliance_outcome.downgraded_status
        )
        changed_columns["Status"] = (previous_status, final_record.status)

    if compliance_outcome.disclosures:
        evidence_notes_parts.extend(compliance_outcome.disclosures)

    evidence_record: EvidenceRecord | None = None
    if evidence_confidence is not None:
        evidence_changes = describe_changes(request.original_row, final_record)
        evidence_notes = "; ".join(
            dict.fromkeys(part for part in evidence_notes_parts if part)
        )
        evidence_record = EvidenceRecord(
            row_id=request.row_id,
            organisation=final_record.name,
            changes=evidence_changes or "No changes",
            sources=sanity_result.normalized_sources,
            notes=evidence_notes,
            confidence=evidence_confidence,
        )

    updated = final_record != original_record

    return RowProcessingResult(
        row_id=request.row_id,
        proposed_record=proposed_record,
        record=final_record,
        updated=updated,
        sources=sanity_result.normalized_sources,
        sanity_findings=sanity_result.findings,
        sanity_notes=sanity_result.notes,
        cleared_columns=sanity_result.cleared_columns,
        changed_columns=changed_columns,
        evidence_record=evidence_record,
        quality_issues=quality_issues,
        rollback_action=rollback_action,
        quality_rejected=quality_rejected,
        decision=decision,
        compliance=compliance_outcome,
        follow_up_records=follow_up_records,
    )


@dataclass(slots=True)
class SanityCheckResult:
    updated: bool
    notes: list[str]
    findings: list[SanityCheckFinding]
    normalized_sources: list[str]
    cleared_columns: list[str]


def run_sanity_checks(
    *,
    record: SchoolRecord,
    row_id: int,
    sources: Sequence[str],
    phone_issues: Sequence[str],
    email_issues: Sequence[str],
    previous_phone: str | None,
    previous_email: str | None,
) -> SanityCheckResult:
    updated = False
    notes: list[str] = []
    findings: list[SanityCheckFinding] = []
    normalized_sources = list(sources)
    cleared_columns: list[str] = []

    if record.website_url:
        parsed = urlparse(record.website_url)
        if not parsed.scheme:
            original_url = record.website_url
            normalized_url = f"https://{original_url.lstrip('/')}"
            record.website_url = normalized_url
            normalized_sources = [
                normalized_url if source == original_url else source
                for source in normalized_sources
            ]
            updated = True
            notes.append("Auto-normalised website URL to include https scheme.")
            findings.append(
                SanityCheckFinding(
                    row_id=row_id,
                    organisation=record.name,
                    issue="website_url_missing_scheme",
                    remediation="Added an https:// prefix to the website URL for consistency.",
                )
            )

    if previous_phone and record.contact_number is None and phone_issues:
        notes.append(
            "Removed invalid contact number after it failed +27 E.164 validation."
        )
        findings.append(
            SanityCheckFinding(
                row_id=row_id,
                organisation=record.name,
                issue="contact_number_invalid",
                remediation="Capture a verified +27-format contact number before publishing.",
            )
        )
        updated = True
        cleared_columns.append("Contact Number")

    if previous_email and record.contact_email is None and email_issues:
        notes.append("Removed invalid contact email after validation failures.")
        findings.append(
            SanityCheckFinding(
                row_id=row_id,
                organisation=record.name,
                issue="contact_email_invalid",
                remediation="Source a named contact email on the official organisation domain.",
            )
        )
        updated = True
        cleared_columns.append("Contact Email Address")

    if record.province == "Unknown":
        findings.append(
            SanityCheckFinding(
                row_id=row_id,
                organisation=record.name,
                issue="province_unknown",
                remediation="Confirm the organisation's South African province and update the dataset.",
            )
        )
        notes.append("Province remains Unknown pending analyst confirmation.")

    return SanityCheckResult(
        updated=updated,
        notes=notes,
        findings=findings,
        normalized_sources=normalized_sources,
        cleared_columns=cleared_columns,
    )


def merge_sources(record: SchoolRecord, finding: ResearchFinding) -> list[str]:
    sources: list[str] = []
    if record.website_url:
        sources.append(record.website_url)
    if finding.website_url and finding.website_url not in sources:
        sources.append(finding.website_url)
    for source in finding.sources:
        if source not in sources:
            sources.append(source)
    if not sources:
        sources.append("internal://record")
    return sources


def summarize_sources(
    *, original_record: SchoolRecord, merged_sources: Sequence[str]
) -> tuple[int, int, int, int]:
    original_keys = {
        normalize_source_key(source)
        for source in collect_original_sources(original_record)
    }
    seen_keys: set[str] = set()
    total_sources = 0
    fresh_sources = 0
    official_sources = 0
    official_fresh_sources = 0
    for source in merged_sources:
        key = normalize_source_key(source)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        total_sources += 1
        is_official = is_official_source(source)
        if is_official:
            official_sources += 1
        if key not in original_keys:
            fresh_sources += 1
            if is_official:
                official_fresh_sources += 1
    return total_sources, fresh_sources, official_sources, official_fresh_sources


def collect_original_sources(record: SchoolRecord) -> Sequence[str]:
    sources: list[str] = []
    if record.website_url:
        sources.append(record.website_url)
    return sources


def normalize_source_key(source: str) -> str:
    domain = canonical_domain(source)
    if domain:
        return f"domain:{domain}"
    return source.strip().lower()


def is_official_source(source: str) -> bool:
    candidate = source.lower()
    return any(keyword in candidate for keyword in _OFFICIAL_KEYWORDS)


def describe_changes(original_row: Mapping[str, Any], record: SchoolRecord) -> str:
    changes: list[str] = []
    mapping = {
        "Website URL": record.website_url,
        "Contact Person": record.contact_person,
        "Contact Number": record.contact_number,
        "Contact Email Address": record.contact_email,
        "Status": record.status,
        "Province": record.province,
    }
    for column, new_value in mapping.items():
        original_value = str(original_row.get(column, "") or "").strip()
        if new_value and original_value != new_value:
            changes.append(f"{column} -> {new_value}")
    return "; ".join(changes)


def compose_evidence_notes(
    finding: ResearchFinding,
    original_row: Mapping[str, Any],
    record: SchoolRecord,
    *,
    has_official_source: bool,
    total_source_count: int,
    fresh_source_count: int,
    sanity_notes: Sequence[str] | None = None,
) -> str:
    notes: list[str] = []
    if finding.notes:
        notes.append(finding.notes)

    if sanity_notes:
        for note in sanity_notes:
            if note and note not in notes:
                notes.append(note)

    from watercrawl.core import config  # local import to avoid cycles

    if config.FEATURE_FLAGS.investigate_rebrands:
        for note in finding.investigation_notes:
            if note and note not in notes:
                notes.append(note)

        prior_domain = canonical_domain(str(original_row.get("Website URL", "")))
        current_domain = canonical_domain(record.website_url)
        if prior_domain and current_domain and prior_domain != current_domain:
            rename_note = (
                f"Website changed from {prior_domain} to {current_domain}; "
                "investigate potential rename or ownership change."
            )
            if rename_note not in notes:
                notes.append(rename_note)

        if finding.alternate_names:
            alias_block = ", ".join(sorted(set(finding.alternate_names)))
            alias_note = f"Known aliases: {alias_block}"
            if alias_note not in notes:
                notes.append(alias_note)

        if finding.physical_address:
            address_note = f"Latest address intelligence: {finding.physical_address}"
            if address_note not in notes:
                notes.append(address_note)

    notes_text = "; ".join(notes) if notes else ""

    remediation_reasons: list[str] = []
    if total_source_count < 2:
        remediation_reasons.append("add a second independent source")
    if fresh_source_count == 0:
        remediation_reasons.append("capture a fresh supporting source")
    if not has_official_source:
        remediation_reasons.append(
            "confirm an official (.gov.za/.caa.co.za/.ac.za/.org.za/.mil.za) source"
        )
    if remediation_reasons:
        shortfall_note = "Evidence shortfall: " + "; ".join(remediation_reasons)
        if not shortfall_note.endswith("."):
            shortfall_note += "."
        if notes_text:
            notes_text = "; ".join(filter(None, [notes_text, shortfall_note]))
        else:
            notes_text = shortfall_note

    return notes_text


def collect_changed_columns(
    original: SchoolRecord, proposed: SchoolRecord
) -> dict[str, tuple[str | None, str | None]]:
    changes: dict[str, tuple[str | None, str | None]] = {}
    original_map = original.as_dict()
    proposed_map = proposed.as_dict()
    for column, original_value in original_map.items():
        proposed_value = proposed_map.get(column)
        if (original_value or "") != (proposed_value or ""):
            changes[column] = (original_value, proposed_value)
    return changes


def quality_issue_from_finding(
    *, row_id: int, organisation: str, finding: QualityFinding
) -> QualityIssue:
    return QualityIssue(
        row_id=row_id,
        organisation=organisation,
        code=finding.code,
        severity=finding.severity,
        message=finding.message,
        remediation=finding.remediation,
    )


def build_rollback_action(
    *,
    row_id: int,
    organisation: str,
    attempted_changes: Mapping[str, tuple[str | None, str | None]],
    issues: Sequence[QualityIssue],
) -> RollbackAction:
    columns = sorted(attempted_changes.keys())
    previous_values = {column: attempted_changes[column][0] for column in columns}
    reason_parts = [issue.message for issue in issues if issue.message]
    reason_text = "; ".join(reason_parts) or "Quality gate rejection"
    remediation = sorted({issue.remediation for issue in issues if issue.remediation})
    if remediation:
        reason_text += ". Remediation: " + "; ".join(remediation)
    return RollbackAction(
        row_id=row_id,
        organisation=organisation,
        columns=columns,
        previous_values=previous_values,
        reason=reason_text,
    )


def format_quality_rejection_reason(issues: Sequence[QualityIssue]) -> str:
    blocking = [issue.message for issue in issues if issue.severity == "block"]
    if blocking:
        return "; ".join(blocking)
    fallback = [issue.message for issue in issues if issue.message]
    return "; ".join(fallback) or "Quality gate rejected enrichment"


def compose_quality_rejection_notes(
    reason: str,
    attempted_changes: str,
    findings: Sequence[QualityFinding],
    sanity_notes: Sequence[str],
) -> str:
    notes: list[str] = [f"Quality gate rejected enrichment: {reason}"]
    if attempted_changes:
        notes.append(f"Attempted updates: {attempted_changes}")
    remediation = sorted(
        {finding.remediation for finding in findings if finding.remediation}
    )
    if remediation:
        notes.append("Remediation: " + "; ".join(remediation))
    if sanity_notes:
        for note in sorted(set(filter(None, sanity_notes))):
            notes.append(note)
    return "; ".join(notes)
