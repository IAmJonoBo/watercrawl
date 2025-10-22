"""Row-level processing logic for enrichment pipeline.

Handles normalization, sanity checks, and quality gate evaluation for individual
rows without directly mutating DataFrames. Returns structured results that can be
applied in bulk vectorized operations.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urlparse

from firecrawl_demo.application.quality import QualityGate, QualityGateDecision
from firecrawl_demo.domain.compliance import (
    canonical_domain,
    confidence_for_status,
    determine_status,
    normalize_phone,
    normalize_province,
    validate_email,
)
from firecrawl_demo.domain.models import (
    QualityIssue,
    RollbackAction,
    SanityCheckFinding,
    SchoolRecord,
)
from firecrawl_demo.integrations.adapters.research import ResearchFinding


@dataclass(slots=True, frozen=True)
class RowProcessingResult:
    """Result of processing a single row.
    
    Contains the final record state and all side effects (evidence, findings, actions)
    without modifying the original DataFrame.
    """
    
    final_record: SchoolRecord
    """The final transformed record"""
    
    updated: bool
    """Whether any changes were made"""
    
    changed_columns: dict[str, tuple[str | None, str | None]]
    """Map of changed column names to (old, new) value tuples"""
    
    sanity_findings: list[SanityCheckFinding]
    """Sanity check issues discovered during processing"""
    
    quality_issues: list[QualityIssue]
    """Quality gate issues if changes were rejected"""
    
    rollback_action: RollbackAction | None
    """Rollback action if quality gate rejected changes"""
    
    cleared_columns: list[str]
    """Column names that should be cleared (set to empty string)"""
    
    sources: list[str]
    """Merged list of sources for evidence"""
    
    confidence: int
    """Confidence score for the transformation"""
    
    sanity_notes: list[str]
    """Notes from sanity checks"""
    
    source_counts: tuple[int, int, int, int]
    """(total, fresh, official, official_fresh) source counts"""


_OFFICIAL_KEYWORDS = (".gov.za", "caa.co.za", ".ac.za", ".org.za", ".mil.za")


class RowProcessor:
    """Process individual rows through normalization, validation, and quality gates."""
    
    def __init__(self, quality_gate: QualityGate) -> None:
        """Initialize the row processor.
        
        Args:
            quality_gate: Quality gate for evaluating proposed changes
        """
        self.quality_gate = quality_gate
    
    def process_row(
        self,
        *,
        original_record: SchoolRecord,
        finding: ResearchFinding,
        row_id: int,
    ) -> RowProcessingResult:
        """Process a single row through the enrichment pipeline.
        
        Args:
            original_record: The original record before enrichment
            finding: Research findings from the adapter
            row_id: Row identifier for logging
            
        Returns:
            RowProcessingResult containing the final record and all side effects
        """
        # Start with a copy of the original record
        record = replace(original_record)
        
        # Normalize province
        record.province = normalize_province(record.province)
        
        # Merge sources
        sources = self._merge_sources(record, finding)
        
        # Summarize source quality
        (
            total_source_count,
            fresh_source_count,
            official_source_count,
            official_fresh_source_count,
        ) = self._summarize_sources(original=original_record, merged_sources=sources)
        
        # Update website URL if appropriate
        if finding.website_url:
            current_domain = canonical_domain(record.website_url)
            proposed_domain = canonical_domain(finding.website_url)
            if not record.website_url or (
                proposed_domain and proposed_domain != current_domain
            ):
                record.website_url = finding.website_url
        
        # Update contact person
        if not record.contact_person and finding.contact_person:
            record.contact_person = finding.contact_person
        
        # Normalize phone number
        previous_phone = record.contact_number
        phone_candidate = finding.contact_phone or record.contact_number
        normalized_phone, phone_issues = normalize_phone(phone_candidate)
        if normalized_phone and normalized_phone != record.contact_number:
            record.contact_number = normalized_phone
        elif not normalized_phone and record.contact_number:
            record.contact_number = None
        
        # Validate email
        previous_email = record.contact_email
        email_candidate = finding.contact_email or record.contact_email
        validated_email, email_issues = validate_email(
            email_candidate, canonical_domain(record.website_url)
        )
        filtered_email_issues = [
            issue for issue in email_issues if issue != "MX lookup unavailable"
        ]
        if validated_email and validated_email != record.contact_email:
            record.contact_email = validated_email
        elif not validated_email and record.contact_email:
            record.contact_email = None
        
        # Determine status
        has_named_contact = bool(record.contact_person)
        has_official_domain = official_source_count > 0
        has_multiple_sources = total_source_count >= 2
        status = determine_status(
            bool(record.website_url),
            has_named_contact,
            phone_issues,
            filtered_email_issues,
            has_multiple_sources,
        )
        if status != record.status:
            record.status = status
        
        # Run sanity checks
        (
            _sanity_updated,
            sanity_notes,
            sanity_findings,
            sources,
            cleared_columns,
        ) = self._run_sanity_checks(
            record=record,
            row_id=row_id,
            sources=sources,
            phone_issues=phone_issues,
            email_issues=filtered_email_issues,
            previous_phone=previous_phone,
            previous_email=previous_email,
        )
        
        # Collect changed columns
        changed_columns = self._collect_changed_columns(original_record, record)
        
        # Evaluate quality gate
        decision: QualityGateDecision | None = None
        if changed_columns:
            decision = self.quality_gate.evaluate(
                original=original_record,
                proposed=record,
                finding=finding,
                changed_columns=changed_columns,
                phone_issues=phone_issues,
                email_issues=filtered_email_issues,
                total_source_count=total_source_count,
                fresh_source_count=fresh_source_count,
                official_source_count=official_source_count,
                official_fresh_source_count=official_fresh_source_count,
            )
        
        # Handle quality gate rejection
        quality_issues: list[QualityIssue] = []
        rollback_action: RollbackAction | None = None
        
        if decision and not decision.accepted:
            issues = [
                self._quality_issue_from_finding(
                    row_id=row_id,
                    organisation=original_record.name,
                    finding=finding_detail,
                )
                for finding_detail in decision.findings
            ]
            quality_issues.extend(issues)
            
            rollback_action = self._build_rollback_action(
                row_id=row_id,
                organisation=original_record.name,
                attempted_changes=changed_columns,
                issues=issues,
            )
            
            final_record = decision.fallback_record or replace(
                original_record, status="Needs Review"
            )
            updated = final_record != original_record
            confidence = 0
        else:
            final_record = record
            updated = bool(changed_columns)
            if updated:
                confidence = finding.confidence or confidence_for_status(
                    final_record.status,
                    len(phone_issues) + len(filtered_email_issues),
                )
            else:
                confidence = 0
        
        return RowProcessingResult(
            final_record=final_record,
            updated=updated,
            changed_columns=changed_columns,
            sanity_findings=sanity_findings,
            quality_issues=quality_issues,
            rollback_action=rollback_action,
            cleared_columns=cleared_columns,
            sources=sources,
            confidence=confidence,
            sanity_notes=sanity_notes,
            source_counts=(
                total_source_count,
                fresh_source_count,
                official_source_count,
                official_fresh_source_count,
            ),
        )
    
    def _merge_sources(
        self, record: SchoolRecord, finding: ResearchFinding
    ) -> list[str]:
        """Merge sources from record and finding."""
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
    
    def _summarize_sources(
        self, *, original: SchoolRecord, merged_sources: Sequence[str]
    ) -> tuple[int, int, int, int]:
        """Summarize source quality metrics."""
        original_keys = {
            self._normalize_source_key(source)
            for source in self._collect_original_sources(original)
        }
        seen_keys: set[str] = set()
        total_sources = 0
        fresh_sources = 0
        official_sources = 0
        official_fresh_sources = 0
        for source in merged_sources:
            key = self._normalize_source_key(source)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            total_sources += 1
            is_official = self._is_official_source(source)
            if is_official:
                official_sources += 1
            if key not in original_keys:
                fresh_sources += 1
                if is_official:
                    official_fresh_sources += 1
        return total_sources, fresh_sources, official_sources, official_fresh_sources
    
    def _collect_original_sources(self, record: SchoolRecord) -> Sequence[str]:
        """Collect sources from the original record."""
        sources: list[str] = []
        if record.website_url:
            sources.append(record.website_url)
        return sources
    
    def _normalize_source_key(self, source: str) -> str:
        """Normalize a source URL to a canonical key."""
        domain = canonical_domain(source)
        if domain:
            return f"domain:{domain}"
        return source.strip().lower()
    
    def _is_official_source(self, source: str) -> bool:
        """Check if a source is from an official domain."""
        candidate = source.lower()
        return any(keyword in candidate for keyword in _OFFICIAL_KEYWORDS)
    
    def _collect_changed_columns(
        self, original: SchoolRecord, proposed: SchoolRecord
    ) -> dict[str, tuple[str | None, str | None]]:
        """Collect columns that have changed."""
        changes: dict[str, tuple[str | None, str | None]] = {}
        original_map = original.as_dict()
        proposed_map = proposed.as_dict()
        for column, original_value in original_map.items():
            proposed_value = proposed_map.get(column)
            if (original_value or "") != (proposed_value or ""):
                changes[column] = (original_value, proposed_value)
        return changes
    
    def _run_sanity_checks(
        self,
        *,
        record: SchoolRecord,
        row_id: int,
        sources: list[str],
        phone_issues: Sequence[str],
        email_issues: Sequence[str],
        previous_phone: str | None,
        previous_email: str | None,
    ) -> tuple[bool, list[str], list[SanityCheckFinding], list[str], list[str]]:
        """Run sanity checks on the record."""
        updated = False
        notes: list[str] = []
        findings: list[SanityCheckFinding] = []
        normalized_sources = list(sources)
        cleared_columns: list[str] = []
        
        # Check for missing URL scheme
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
        
        # Check for invalid phone number
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
        
        # Check for invalid email
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
        
        # Check for unknown province
        if record.province == "Unknown":
            findings.append(
                SanityCheckFinding(
                    row_id=row_id,
                    organisation=record.name,
                    issue="province_unknown",
                    remediation=(
                        "Confirm the organisation's South African province and update the dataset."
                    ),
                )
            )
            notes.append("Province remains Unknown pending analyst confirmation.")
        
        return updated, notes, findings, normalized_sources, cleared_columns
    
    def _quality_issue_from_finding(
        self,
        *,
        row_id: int,
        organisation: str,
        finding: Any,
    ) -> QualityIssue:
        """Create a QualityIssue from a quality finding."""
        return QualityIssue(
            row_id=row_id,
            organisation=organisation,
            code=finding.code,
            severity=finding.severity,
            message=finding.message,
            remediation=finding.remediation,
        )
    
    def _build_rollback_action(
        self,
        *,
        row_id: int,
        organisation: str,
        attempted_changes: dict[str, tuple[str | None, str | None]],
        issues: Sequence[QualityIssue],
    ) -> RollbackAction:
        """Build a rollback action from quality issues."""
        columns = sorted(attempted_changes.keys())
        previous_values = {column: attempted_changes[column][0] for column in columns}
        reason_parts = [issue.message for issue in issues if issue.message]
        reason_text = "; ".join(reason_parts) or "Quality gate rejection"
        remediation = sorted(
            {issue.remediation for issue in issues if issue.remediation}
        )
        if remediation:
            reason_text += ". Remediation: " + "; ".join(remediation)
        return RollbackAction(
            row_id=row_id,
            organisation=organisation,
            columns=columns,
            previous_values=previous_values,
            reason=reason_text,
        )
