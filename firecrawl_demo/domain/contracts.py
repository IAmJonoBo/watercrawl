"""Pydantic-based data contracts for Watercrawl/Firecrawl enrichment pipeline.

This module provides versioned, schema-exportable contracts that replace the
legacy dataclass models in models.py, enabling:
- JSON Schema / Avro export for contract testing
- Runtime validation with detailed error messages
- Semantic versioning and schema registry integration
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Contract version follows semantic versioning
CONTRACT_VERSION = "1.0.0"
SCHEMA_URI_BASE = "https://watercrawl.acesaero.co.za/schemas/v1"


class SchoolRecordContract(BaseModel):
    """Contract for school/organisation enrichment records.

    Maps to the legacy SchoolRecord dataclass for backward compatibility.
    """

    name: str = Field(..., min_length=1, description="Organisation name")
    province: str = Field(..., description="South African province")
    status: str = Field(..., description="Verification status")
    website_url: str | None = Field(None, description="Organisation website URL")
    contact_person: str | None = Field(None, description="Primary contact person")
    contact_number: str | None = Field(None, description="Contact phone number")
    contact_email: str | None = Field(None, description="Contact email address")

    model_config = {
        "json_schema_extra": {
            "version": CONTRACT_VERSION,
            "schema_uri": f"{SCHEMA_URI_BASE}/school-record",
        }
    }

    @field_validator("province")
    @classmethod
    def validate_province(cls, v: str) -> str:
        """Ensure province is one of the canonical South African provinces."""
        from firecrawl_demo.core import config

        valid_provinces = set(config.PROVINCES) | {"Unknown"}
        if v not in valid_provinces:
            raise ValueError(f"Province must be one of {valid_provinces}, got {v!r}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Ensure status is one of the canonical statuses."""
        from firecrawl_demo.core import config

        valid_statuses = set(config.CANONICAL_STATUSES)
        if v not in valid_statuses:
            raise ValueError(f"Status must be one of {valid_statuses}, got {v!r}")
        return v


class EvidenceRecordContract(BaseModel):
    """Contract for evidence log entries.

    Maps to the legacy EvidenceRecord dataclass for backward compatibility.
    """

    row_id: int = Field(..., ge=0, description="Row identifier")
    organisation: str = Field(..., min_length=1, description="Organisation name")
    changes: str = Field(..., description="Description of changes made")
    sources: list[str] = Field(
        default_factory=list, description="Data source URLs or references"
    )
    notes: str = Field(default="", description="Additional notes or context")
    confidence: int = Field(..., ge=0, le=100, description="Confidence score (0-100)")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Record creation timestamp",
    )

    model_config = {
        "json_schema_extra": {
            "version": CONTRACT_VERSION,
            "schema_uri": f"{SCHEMA_URI_BASE}/evidence-record",
        }
    }


class QualityIssueContract(BaseModel):
    """Contract for quality gate issues.

    Maps to the legacy QualityIssue dataclass for backward compatibility.
    """

    row_id: int = Field(..., ge=0, description="Row identifier")
    organisation: str = Field(..., min_length=1, description="Organisation name")
    code: str = Field(..., min_length=1, description="Issue code/identifier")
    severity: Literal["block", "warn"] = Field(..., description="Issue severity level")
    message: str = Field(..., min_length=1, description="Human-readable issue message")
    remediation: str | None = Field(None, description="Suggested remediation steps")

    model_config = {
        "json_schema_extra": {
            "version": CONTRACT_VERSION,
            "schema_uri": f"{SCHEMA_URI_BASE}/quality-issue",
        }
    }


class ValidationIssueContract(BaseModel):
    """Contract for validation issues."""

    code: str = Field(..., min_length=1, description="Issue code")
    message: str = Field(..., min_length=1, description="Issue description")
    row: int | None = Field(None, ge=0, description="Row number if applicable")
    column: str | None = Field(None, description="Column name if applicable")

    model_config = {
        "json_schema_extra": {
            "version": CONTRACT_VERSION,
            "schema_uri": f"{SCHEMA_URI_BASE}/validation-issue",
        }
    }


class ValidationReportContract(BaseModel):
    """Contract for validation reports."""

    issues: list[ValidationIssueContract] = Field(
        default_factory=list, description="List of validation issues"
    )
    rows: int = Field(..., ge=0, description="Total number of rows validated")

    @property
    def is_valid(self) -> bool:
        """Check if validation passed (no issues)."""
        return not self.issues

    model_config = {
        "json_schema_extra": {
            "version": CONTRACT_VERSION,
            "schema_uri": f"{SCHEMA_URI_BASE}/validation-report",
        }
    }


class SanityCheckFindingContract(BaseModel):
    """Contract for sanity check findings."""

    row_id: int = Field(..., ge=0, description="Row identifier")
    organisation: str = Field(..., min_length=1, description="Organisation name")
    issue: str = Field(..., min_length=1, description="Issue description")
    remediation: str = Field(..., min_length=1, description="Remediation steps")

    model_config = {
        "json_schema_extra": {
            "version": CONTRACT_VERSION,
            "schema_uri": f"{SCHEMA_URI_BASE}/sanity-check-finding",
        }
    }


class PipelineReportContract(BaseModel):
    """Contract for pipeline execution reports.

    Maps to the legacy PipelineReport dataclass for backward compatibility.
    Note: This is a simplified version that doesn't include all optional
    telemetry fields (lineage, lakehouse, version info, etc.) as those
    would create circular dependencies.
    """

    validation_report: ValidationReportContract = Field(
        ..., description="Validation results"
    )
    evidence_log: list[EvidenceRecordContract] = Field(
        default_factory=list, description="Evidence log entries"
    )
    metrics: dict[str, int] = Field(
        default_factory=dict, description="Pipeline execution metrics"
    )
    sanity_findings: list[SanityCheckFindingContract] = Field(
        default_factory=list, description="Sanity check findings"
    )
    quality_issues: list[QualityIssueContract] = Field(
        default_factory=list, description="Quality gate issues"
    )

    @property
    def issues(self) -> list[ValidationIssueContract]:
        """Get validation issues from the report."""
        return self.validation_report.issues

    model_config = {
        "json_schema_extra": {
            "version": CONTRACT_VERSION,
            "schema_uri": f"{SCHEMA_URI_BASE}/pipeline-report",
        }
    }


# Schema export helpers
def export_json_schema(contract_class: type[BaseModel]) -> dict:
    """Export JSON Schema for a contract class."""
    return contract_class.model_json_schema()


def export_all_schemas() -> dict[str, dict]:
    """Export JSON Schemas for all contract classes."""
    return {
        "SchoolRecord": export_json_schema(SchoolRecordContract),
        "EvidenceRecord": export_json_schema(EvidenceRecordContract),
        "QualityIssue": export_json_schema(QualityIssueContract),
        "ValidationIssue": export_json_schema(ValidationIssueContract),
        "ValidationReport": export_json_schema(ValidationReportContract),
        "SanityCheckFinding": export_json_schema(SanityCheckFindingContract),
        "PipelineReport": export_json_schema(PipelineReportContract),
    }
