"""Automation hooks for compliance-aware QA scheduling."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from watercrawl.domain.models import ComplianceScheduleEntry


@dataclass(slots=True)
class RevalidationTask:
    """Task describing how to re-queue a row for compliance verification."""

    row_id: int
    organisation: str
    status: str
    reason: str
    next_review_due: datetime | None
    recommended_tasks: Sequence[str]


def due_for_revalidation(
    entries: Iterable[ComplianceScheduleEntry], *, now: datetime | None = None
) -> list[ComplianceScheduleEntry]:
    """Return entries whose revalidation date is in the past."""

    current = now or datetime.now(UTC)
    result: list[ComplianceScheduleEntry] = []
    for entry in entries:
        if entry.next_review_due and entry.next_review_due <= current:
            result.append(entry)
    return result


def build_revalidation_tasks(
    entries: Iterable[ComplianceScheduleEntry], *, now: datetime | None = None
) -> list[RevalidationTask]:
    """Build actionable tasks for QA automation to enqueue."""

    current = now or datetime.now(UTC)
    tasks: list[RevalidationTask] = []
    for entry in entries:
        overdue = entry.next_review_due and entry.next_review_due <= current
        mx_exhausted = entry.mx_failure_count >= 2
        if not overdue and not mx_exhausted:
            continue
        reasons: list[str] = []
        if overdue:
            reasons.append("evidence stale")
        if mx_exhausted:
            reasons.append("MX validation failures")
        reason = ", ".join(reasons) if reasons else "scheduled check"
        tasks.append(
            RevalidationTask(
                row_id=entry.row_id,
                organisation=entry.organisation,
                status=entry.status,
                reason=reason,
                next_review_due=entry.next_review_due,
                recommended_tasks=entry.tasks,
            )
        )
    return tasks


def suppressed_contacts(entries: Iterable[ComplianceScheduleEntry]) -> list[int]:
    """Return row IDs currently marked as Do Not Contact (Compliance)."""

    return [
        entry.row_id
        for entry in entries
        if entry.status == "Do Not Contact (Compliance)"
    ]
