from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

import pandas as pd

from . import config

_CANONICAL_PROVINCES = {province.lower(): province for province in config.PROVINCES}
_UNKNOWN_PROVINCE = "Unknown"
_CANONICAL_STATUSES = {status.lower(): status for status in config.CANONICAL_STATUSES}
_STATUS_FALLBACK = "Needs Review"


def normalize_province(value: Any) -> str:
    if value is None:
        return _UNKNOWN_PROVINCE
    text = str(value).strip()
    if not text:
        return _UNKNOWN_PROVINCE
    return _CANONICAL_PROVINCES.get(text.lower(), _UNKNOWN_PROVINCE)


def normalize_status(value: Any) -> str:
    if value is None:
        return _STATUS_FALLBACK
    text = str(value).strip()
    if not text:
        return _STATUS_FALLBACK
    return _CANONICAL_STATUSES.get(text.lower(), _STATUS_FALLBACK)


@dataclass
class Organisation:
    name: str
    province: str | None = None
    status: str | None = None


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    row: int | None = None
    column: str | None = None


@dataclass(frozen=True)
class ValidationReport:
    issues: list[ValidationIssue]
    rows: int

    @property
    def is_valid(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class EvidenceRecord:
    row_id: int
    organisation: str
    changes: str
    sources: list[str]
    notes: str
    confidence: int
    timestamp: datetime = field(default_factory=lambda: datetime.utcnow())

    def as_dict(self) -> dict[str, str]:
        return {
            "RowID": str(self.row_id),
            "Organisation": self.organisation,
            "What changed": self.changes,
            "Sources": "; ".join(self.sources),
            "Notes": self.notes,
            "Timestamp": self.timestamp.isoformat(timespec="seconds"),
            "Confidence": str(self.confidence),
        }


@dataclass(frozen=True)
class QualityIssue:
    row_id: int
    organisation: str
    code: str
    severity: Literal["block", "warn"]
    message: str
    remediation: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "organisation": self.organisation,
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "remediation": self.remediation or "",
        }


@dataclass(frozen=True)
class SanityCheckFinding:
    row_id: int
    organisation: str
    issue: str
    remediation: str

    def as_dict(self) -> dict[str, str]:
        return {
            "row_id": str(self.row_id),
            "organisation": self.organisation,
            "issue": self.issue,
            "remediation": self.remediation,
        }


@dataclass
class SchoolRecord:
    name: str
    province: str
    status: str
    website_url: str | None
    contact_person: str | None
    contact_number: str | None
    contact_email: str | None

    @classmethod
    def from_dataframe_row(cls, row: pd.Series) -> SchoolRecord:
        return cls(
            name=str(row.get("Name of Organisation", "")).strip(),
            province=normalize_province(row.get("Province")),
            status=normalize_status(row.get("Status")),
            website_url=_clean_value(row.get("Website URL")),
            contact_person=_clean_value(row.get("Contact Person")),
            contact_number=_clean_value(row.get("Contact Number")),
            contact_email=_clean_value(row.get("Contact Email Address")),
        )

    def as_dict(self) -> dict[str, str | None]:
        return {
            "Name of Organisation": self.name,
            "Province": self.province,
            "Status": self.status,
            "Website URL": self.website_url,
            "Contact Person": self.contact_person,
            "Contact Number": self.contact_number,
            "Contact Email Address": self.contact_email,
        }


@dataclass
class EnrichmentResult:
    record: SchoolRecord
    issues: list[str] = field(default_factory=list)
    evidence: EvidenceRecord | None = None

    def apply(self, frame: pd.DataFrame, index: int) -> None:
        for key, value in self.record.as_dict().items():
            if value is not None:
                frame.at[index, key] = value


@dataclass(frozen=True)
class RollbackAction:
    row_id: int
    organisation: str
    columns: list[str]
    previous_values: dict[str, str | None]
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "organisation": self.organisation,
            "columns": list(self.columns),
            "previous_values": dict(self.previous_values),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RollbackPlan:
    actions: list[RollbackAction]

    def as_dict(self) -> dict[str, Any]:
        return {"actions": [action.as_dict() for action in self.actions]}


@dataclass(frozen=True)
class PipelineReport:
    refined_dataframe: pd.DataFrame
    validation_report: ValidationReport
    evidence_log: list[EvidenceRecord]
    metrics: dict[str, int]
    sanity_findings: list[SanityCheckFinding] = field(default_factory=list)
    quality_issues: list[QualityIssue] = field(default_factory=list)
    rollback_plan: RollbackPlan | None = None

    @property
    def issues(self) -> list[ValidationIssue]:
        return self.validation_report.issues


def _clean_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
