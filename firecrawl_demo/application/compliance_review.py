"""Compliance review helpers for POPIA-aligned enrichment decisions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from firecrawl_demo.core import config
from firecrawl_demo.domain.models import EvidenceRecord, SchoolRecord
from firecrawl_demo.integrations.adapters.research.core import ResearchFinding


@dataclass(slots=True)
class ComplianceReviewOutcome:
    """Result of reviewing a row for POPIA compliance."""

    disclosures: list[str] = field(default_factory=list)
    follow_up_records: list[EvidenceRecord] = field(default_factory=list)
    downgraded_status: str | None = None
    mx_failure_count: int = 0
    last_verified_at: datetime | None = None
    next_review_due: datetime | None = None
    lawful_basis: str | None = None
    contact_purpose: str | None = None
    opt_out: bool = False
    recommended_tasks: list[str] = field(default_factory=list)


class ComplianceReview:
    """Evaluate an enrichment update against POPIA compliance rules."""

    def __init__(self, *, now: datetime | None = None) -> None:
        self._now = now or datetime.now(UTC)

    def review(
        self,
        *,
        row_id: int,
        organisation: str,
        record: SchoolRecord,
        finding: ResearchFinding,
        sources: Sequence[str],
        changed_columns: Mapping[str, tuple[str | None, str | None]],
        phone_issues: Sequence[str],
        email_issues: Sequence[str],
        previous_mx_failures: int = 0,
        opt_out_flag: bool = False,
    ) -> ComplianceReviewOutcome:
        """Return compliance annotations for a processed row."""

        outcome = ComplianceReviewOutcome(opt_out=opt_out_flag)
        lawful_basis_key = config.COMPLIANCE_DEFAULT_LAWFUL_BASIS
        lawful_basis_desc = config.COMPLIANCE_LAWFUL_BASES.get(
            lawful_basis_key, lawful_basis_key.replace("_", " ").title()
        )
        contact_purpose_key = config.COMPLIANCE_DEFAULT_CONTACT_PURPOSE
        contact_purpose_desc = config.COMPLIANCE_CONTACT_PURPOSES.get(
            contact_purpose_key, contact_purpose_key.replace("_", " ").title()
        )
        outcome.lawful_basis = lawful_basis_key
        outcome.contact_purpose = contact_purpose_key
        outcome.disclosures.extend(
            [
                f"Lawful basis: {lawful_basis_desc}",
                f"Contact purpose: {contact_purpose_desc}",
            ]
        )

        if finding.investigation_notes:
            for note in finding.investigation_notes:
                outcome.disclosures.append(f"Investigation note: {note}")
        elif finding.notes:
            outcome.disclosures.append(f"Research note: {finding.notes}")

        mx_failure_count = self._update_mx_failures(previous_mx_failures, email_issues)
        outcome.mx_failure_count = mx_failure_count

        if mx_failure_count >= 2 and record.status != "Do Not Contact (Compliance)":
            outcome.downgraded_status = "Do Not Contact (Compliance)"
            outcome.disclosures.append(
                "MX lookups failed repeatedly; downgrade to Do Not Contact (Compliance)."
            )

        if opt_out_flag:
            outcome.disclosures.append(
                "Opt-out status present; restrict outreach until transparency notice logged."
            )
            outcome.recommended_tasks.append(
                "Ensure suppression list updated for opt-out"
            )
            outcome.follow_up_records.append(
                EvidenceRecord(
                    row_id=row_id,
                    organisation=organisation,
                    changes="Compliance follow-up",
                    sources=list(sources),
                    notes="Opt-out recorded; update suppression list and confirm audit log.",
                    confidence=0,
                )
            )

        transparency_required = self._requires_transparency_notice(
            changed_columns, opt_out_flag
        )
        if transparency_required:
            template_path = config.COMPLIANCE_NOTIFICATION_TEMPLATES.get(
                "transparency_notice"
            )
            note = "Send transparency notice to the contact"
            if template_path:
                note += f" using template {template_path}"
            outcome.recommended_tasks.append("Send transparency notice")
            outcome.follow_up_records.append(
                EvidenceRecord(
                    row_id=row_id,
                    organisation=organisation,
                    changes="Compliance follow-up",
                    sources=list(sources),
                    notes=note,
                    confidence=0,
                )
            )

        if (
            not outcome.downgraded_status
            and not opt_out_flag
            and not self._has_active_contact_issues(phone_issues, email_issues)
            and record.status == "Verified"
        ):
            outcome.last_verified_at = self._now
            outcome.next_review_due = self._now + timedelta(
                days=config.COMPLIANCE_REVALIDATION_DAYS
            )
            assert (
                outcome.next_review_due is not None
            ), "next_review_due should not be None here"
            outcome.disclosures.append(
                f"Verification logged {self._now.date().isoformat()} with revalidation due "
                f"{outcome.next_review_due.date().isoformat()}"
            )
        elif outcome.downgraded_status:
            outcome.recommended_tasks.append(
                "Investigate MX failure root cause before future outreach"
            )

        return outcome

    @staticmethod
    def _update_mx_failures(previous: int, email_issues: Sequence[str]) -> int:
        if not email_issues:
            return 0
        lowered = [issue.lower() for issue in email_issues]
        mx_related = any(
            "mx" in issue or "dns" in issue or "domain" in issue for issue in lowered
        )
        if mx_related:
            return previous + 1
        return previous

    @staticmethod
    def _has_active_contact_issues(
        phone_issues: Sequence[str], email_issues: Sequence[str]
    ) -> bool:
        def _material(issue: str) -> bool:
            return issue not in {"Phone missing", "Email missing"}

        return any(_material(issue) for issue in phone_issues) or any(
            _material(issue) for issue in email_issues
        )

    @staticmethod
    def _requires_transparency_notice(
        changed_columns: Mapping[str, tuple[str | None, str | None]],
        opt_out_flag: bool,
    ) -> bool:
        if opt_out_flag:
            return False
        monitored_columns = {
            "Contact Person",
            "Contact Email Address",
            "Contact Number",
        }
        return any(column in monitored_columns for column in changed_columns)
