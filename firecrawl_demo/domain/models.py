from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from firecrawl_demo.core import config

if TYPE_CHECKING:
    from firecrawl_demo.integrations.storage.lakehouse import LakehouseManifest
    from firecrawl_demo.integrations.storage.versioning import VersionInfo
    from firecrawl_demo.integrations.telemetry.drift import DriftReport
    from firecrawl_demo.integrations.telemetry.graph_semantics import (
        GraphSemanticsReport,
    )
    from firecrawl_demo.integrations.telemetry.lineage import LineageArtifacts

EXPECTED_COLUMNS = list(config.EXPECTED_COLUMNS)

_CANONICAL_PROVINCES = {province.lower(): province for province in config.PROVINCES}
_UNKNOWN_PROVINCE = "Unknown"
_CANONICAL_STATUSES = {status.lower(): status for status in config.CANONICAL_STATUSES}
_STATUS_FALLBACK = config.DEFAULT_STATUS


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
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

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
    def from_dataframe_row(cls, row: Any) -> SchoolRecord:
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

    def apply(self, frame: Any, index: int) -> None:
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


@dataclass
class PipelineReport:
    refined_dataframe: Any
    validation_report: ValidationReport
    evidence_log: list[EvidenceRecord]
    metrics: dict[str, int]
    sanity_findings: list[SanityCheckFinding] = field(default_factory=list)
    quality_issues: list[QualityIssue] = field(default_factory=list)
    rollback_plan: RollbackPlan | None = None
    lineage_artifacts: LineageArtifacts | None = None
    lakehouse_manifest: LakehouseManifest | None = None
    version_info: VersionInfo | None = None
    graph_semantics: GraphSemanticsReport | None = None
    drift_report: DriftReport | None = None

    @property
    def issues(self) -> list[ValidationIssue]:
        return self.validation_report.issues


def _clean_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


# Adapter functions for contract migration
def school_record_to_contract(record: SchoolRecord):
    """Convert legacy SchoolRecord dataclass to contract model."""
    from firecrawl_demo.domain.contracts import SchoolRecordContract

    return SchoolRecordContract(
        name=record.name,
        province=record.province,
        status=record.status,
        website_url=record.website_url,
        contact_person=record.contact_person,
        contact_number=record.contact_number,
        contact_email=record.contact_email,
    )


def school_record_from_contract(contract):
    """Convert contract model to legacy SchoolRecord dataclass."""
    from firecrawl_demo.domain.contracts import SchoolRecordContract

    if not isinstance(contract, SchoolRecordContract):
        raise TypeError(f"Expected SchoolRecordContract, got {type(contract)}")

    return SchoolRecord(
        name=contract.name,
        province=contract.province,
        status=contract.status,
        website_url=contract.website_url,
        contact_person=contract.contact_person,
        contact_number=contract.contact_number,
        contact_email=contract.contact_email,
    )


def evidence_record_to_contract(record: EvidenceRecord):
    """Convert legacy EvidenceRecord dataclass to contract model."""
    from firecrawl_demo.domain.contracts import EvidenceRecordContract

    return EvidenceRecordContract(
        row_id=record.row_id,
        organisation=record.organisation,
        changes=record.changes,
        sources=list(record.sources),
        notes=record.notes,
        confidence=record.confidence,
        timestamp=record.timestamp,
    )


def evidence_record_from_contract(contract):
    """Convert contract model to legacy EvidenceRecord dataclass."""
    from firecrawl_demo.domain.contracts import EvidenceRecordContract

    if not isinstance(contract, EvidenceRecordContract):
        raise TypeError(f"Expected EvidenceRecordContract, got {type(contract)}")

    return EvidenceRecord(
        row_id=contract.row_id,
        organisation=contract.organisation,
        changes=contract.changes,
        sources=contract.sources,
        notes=contract.notes,
        confidence=contract.confidence,
        timestamp=contract.timestamp,
    )


def quality_issue_to_contract(issue: QualityIssue):
    """Convert legacy QualityIssue dataclass to contract model."""
    from firecrawl_demo.domain.contracts import QualityIssueContract

    return QualityIssueContract(
        row_id=issue.row_id,
        organisation=issue.organisation,
        code=issue.code,
        severity=issue.severity,
        message=issue.message,
        remediation=issue.remediation,
    )


def quality_issue_from_contract(contract):
    """Convert contract model to legacy QualityIssue dataclass."""
    from firecrawl_demo.domain.contracts import QualityIssueContract

    if not isinstance(contract, QualityIssueContract):
        raise TypeError(f"Expected QualityIssueContract, got {type(contract)}")

    return QualityIssue(
        row_id=contract.row_id,
        organisation=contract.organisation,
        code=contract.code,
        severity=contract.severity,
        message=contract.message,
        remediation=contract.remediation,
    )


def validation_issue_to_contract(issue: ValidationIssue):
    """Convert legacy ValidationIssue dataclass to contract model."""
    from firecrawl_demo.domain.contracts import ValidationIssueContract

    return ValidationIssueContract(
        code=issue.code,
        message=issue.message,
        row=issue.row,
        column=issue.column,
    )


def validation_issue_from_contract(contract):
    """Convert contract model to legacy ValidationIssue dataclass."""
    from firecrawl_demo.domain.contracts import ValidationIssueContract

    if not isinstance(contract, ValidationIssueContract):
        raise TypeError(f"Expected ValidationIssueContract, got {type(contract)}")

    return ValidationIssue(
        code=contract.code,
        message=contract.message,
        row=contract.row,
        column=contract.column,
    )
