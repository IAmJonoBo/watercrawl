from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd  # type: ignore[import-untyped]


@dataclass
class Organisation:
    name: str
    province: Optional[str] = None
    status: Optional[str] = None


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    row: Optional[int] = None
    column: Optional[str] = None


@dataclass(frozen=True)
class ValidationReport:
    issues: List[ValidationIssue]
    rows: int

    @property
    def is_valid(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class EvidenceRecord:
    row_id: int
    organisation: str
    changes: str
    sources: List[str]
    notes: str
    confidence: int
    timestamp: datetime = field(default_factory=lambda: datetime.utcnow())

    def as_dict(self) -> Dict[str, str]:
        return {
            "RowID": str(self.row_id),
            "Organisation": self.organisation,
            "What changed": self.changes,
            "Sources": "; ".join(self.sources),
            "Notes": self.notes,
            "Timestamp": self.timestamp.isoformat(timespec="seconds"),
            "Confidence": str(self.confidence),
        }


@dataclass
class SchoolRecord:
    name: str
    province: str
    status: str
    website_url: Optional[str]
    contact_person: Optional[str]
    contact_number: Optional[str]
    contact_email: Optional[str]

    @classmethod
    def from_dataframe_row(cls, row: pd.Series) -> "SchoolRecord":
        return cls(
            name=str(row.get("Name of Organisation", "")).strip(),
            province=str(row.get("Province", "")).strip(),
            status=str(row.get("Status", "")).strip() or "Candidate",
            website_url=_clean_value(row.get("Website URL")),
            contact_person=_clean_value(row.get("Contact Person")),
            contact_number=_clean_value(row.get("Contact Number")),
            contact_email=_clean_value(row.get("Contact Email Address")),
        )

    def as_dict(self) -> Dict[str, Optional[str]]:
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
    issues: List[str] = field(default_factory=list)
    evidence: Optional[EvidenceRecord] = None

    def apply(self, frame: pd.DataFrame, index: int) -> None:
        for key, value in self.record.as_dict().items():
            if value is not None:
                frame.at[index, key] = value


@dataclass(frozen=True)
class PipelineReport:
    refined_dataframe: pd.DataFrame
    validation_report: ValidationReport
    evidence_log: List[EvidenceRecord]
    metrics: Dict[str, int]

    @property
    def issues(self) -> List[ValidationIssue]:
        return self.validation_report.issues


def _clean_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
