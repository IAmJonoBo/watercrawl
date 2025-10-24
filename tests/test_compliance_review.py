from __future__ import annotations

from datetime import UTC, datetime, timedelta

from watercrawl.application.compliance_review import ComplianceReview
from watercrawl.domain.models import ComplianceScheduleEntry, SchoolRecord
from watercrawl.integrations.adapters.research.core import ResearchFinding


def _record(status: str = "Verified") -> SchoolRecord:
    return SchoolRecord(
        name="Test Flight School",
        province="Gauteng",
        status=status,
        website_url="https://example.com",
        contact_person="Nomsa Analyst",
        contact_number="+27110000000",
        contact_email="contact@example.com",
    )


def test_compliance_review_annotations_include_disclosures() -> None:
    now = datetime(2025, 1, 1, tzinfo=UTC)
    reviewer = ComplianceReview(now=now)
    record = _record()
    finding = ResearchFinding(
        contact_email="contact@example.com",
        sources=["https://example.com/about"],
        notes="Corporate registry entry",
    )

    outcome = reviewer.review(
        row_id=10,
        organisation=record.name,
        record=record,
        finding=finding,
        sources=["https://example.com/about"],
        changed_columns={"Contact Email Address": (None, "contact@example.com")},
        phone_issues=[],
        email_issues=[],
    )

    assert any("Lawful basis" in disclosure for disclosure in outcome.disclosures)
    assert outcome.last_verified_at == now
    assert outcome.next_review_due == now + timedelta(days=120)
    assert any("transparency notice" in note.lower() for note in outcome.disclosures)
    assert outcome.follow_up_records
    assert "Send transparency notice" in outcome.recommended_tasks[0]


def test_compliance_review_downgrades_on_repeated_mx_failures() -> None:
    reviewer = ComplianceReview(now=datetime(2025, 1, 1, tzinfo=UTC))
    record = _record(status="Candidate")
    finding = ResearchFinding(sources=["https://example.com"], notes="MX failure")

    outcome = reviewer.review(
        row_id=5,
        organisation=record.name,
        record=record,
        finding=finding,
        sources=["https://example.com"],
        changed_columns={},
        phone_issues=[],
        email_issues=["MX lookup failed"],
        previous_mx_failures=1,
    )

    assert outcome.mx_failure_count == 2
    assert outcome.downgraded_status == "Do Not Contact (Compliance)"
    assert any("Investigate" in task for task in outcome.recommended_tasks)


def test_automation_helpers_identify_overdue_entries() -> None:
    from apps.automation.qa_tasks import (
        RevalidationTask,
        build_revalidation_tasks,
        due_for_revalidation,
        suppressed_contacts,
    )

    now = datetime(2025, 1, 1, tzinfo=UTC)
    overdue = ComplianceScheduleEntry(
        row_id=1,
        organisation="Aero Academy",
        status="Verified",
        last_verified_at=now - timedelta(days=200),
        next_review_due=now - timedelta(days=1),
        tasks=("Send transparency notice",),
    )
    mx_blocked = ComplianceScheduleEntry(
        row_id=2,
        organisation="MX Blocked",
        status="Candidate",
        mx_failure_count=3,
        next_review_due=now + timedelta(days=5),
        tasks=(),
    )
    compliant = ComplianceScheduleEntry(
        row_id=3,
        organisation="Future Review",
        status="Verified",
        next_review_due=now + timedelta(days=30),
        tasks=(),
    )

    entries = [overdue, mx_blocked, compliant]
    overdue_entries = due_for_revalidation(entries, now=now)
    assert overdue_entries == [overdue]

    tasks = build_revalidation_tasks(entries, now=now)
    assert {task.row_id for task in tasks} == {1, 2}
    assert all(isinstance(task, RevalidationTask) for task in tasks)
    suppressed = suppressed_contacts(entries)
    assert suppressed == []

    mx_blocked_dc = ComplianceScheduleEntry(
        row_id=4,
        organisation="Suppressed Org",
        status="Do Not Contact (Compliance)",
    )
    assert suppressed_contacts(entries + [mx_blocked_dc]) == [4]
