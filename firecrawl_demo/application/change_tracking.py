"""Change tracking utilities for row-level transformations.

Provides reusable functions for:
- Detecting column-level differences between records
- Generating deterministic string descriptions of changes
- Building rollback actions with sorted outputs
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from firecrawl_demo.domain.models import QualityIssue, RollbackAction, SchoolRecord


def collect_changed_columns(
    original: SchoolRecord, proposed: SchoolRecord
) -> dict[str, tuple[str | None, str | None]]:
    """Detect which columns have changed between two records.
    
    Args:
        original: The original record before transformation
        proposed: The proposed record after transformation
        
    Returns:
        Dictionary mapping column names to (original_value, proposed_value) tuples
    """
    changes: dict[str, tuple[str | None, str | None]] = {}
    original_map = original.as_dict()
    proposed_map = proposed.as_dict()
    for column, original_value in original_map.items():
        proposed_value = proposed_map.get(column)
        if (original_value or "") != (proposed_value or ""):
            changes[column] = (original_value, proposed_value)
    return changes


def describe_changes(original_row: Any, record: SchoolRecord) -> str:
    """Generate a deterministic string description of changes.
    
    Args:
        original_row: The original pandas Series/dict-like row
        record: The transformed SchoolRecord
        
    Returns:
        A semicolon-separated string of changes, or "No changes"
    """
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
    return "; ".join(changes) or "No changes"


def build_rollback_action(
    *,
    row_id: int,
    organisation: str,
    attempted_changes: dict[str, tuple[str | None, str | None]],
    issues: Sequence[QualityIssue],
) -> RollbackAction:
    """Build a rollback action from quality issues with deterministic ordering.
    
    Args:
        row_id: The row identifier
        organisation: The organisation name
        attempted_changes: Dictionary of attempted column changes
        issues: Sequence of quality issues that triggered the rollback
        
    Returns:
        A RollbackAction with sorted columns and deterministic reason text
    """
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
