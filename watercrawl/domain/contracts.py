"""Pydantic-based data contracts for Watercrawl/Firecrawl enrichment pipeline.

This module provides versioned, schema-exportable contracts that replace the
legacy dataclass models in models.py, enabling:
- JSON Schema / Avro export for contract testing
- Runtime validation with detailed error messages
- Semantic versioning and schema registry integration
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, cast

from pydantic import BaseModel, Field, field_validator

# Contract version follows semantic versioning
CONTRACT_VERSION = "1.0.0"
SCHEMA_URI_BASE = "https://watercrawl.acesaero.co.za/schemas/v1"
AVRO_NAMESPACE = "za.watercrawl.contracts.v1"


class ContractDescriptor(BaseModel):
    """Metadata embedded with downstream artefacts to identify the contract."""

    name: str = Field(..., description="Canonical contract identifier")
    version: str = Field(
        default=CONTRACT_VERSION,
        description="Semantic version of the contract schema",
    )
    schema_uri: str = Field(..., description="Canonical URI for the schema definition")

    model_config = {
        "json_schema_extra": {
            "version": CONTRACT_VERSION,
            "schema_uri": f"{SCHEMA_URI_BASE}/contract-descriptor",
        }
    }


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
        from watercrawl.core import config

        valid_provinces = set(config.PROVINCES) | {"Unknown"}
        if v not in valid_provinces:
            raise ValueError(f"Province must be one of {valid_provinces}, got {v!r}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Ensure status is one of the canonical statuses."""
        from watercrawl.core import config

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


class ComplianceScheduleEntryContract(BaseModel):
    """Contract describing compliance verification metadata for a row."""

    row_id: int = Field(..., ge=0, description="Row identifier")
    organisation: str = Field(..., min_length=1, description="Organisation name")
    status: str = Field(..., min_length=1, description="Current status value")
    last_verified_at: datetime | None = Field(
        None, description="Timestamp when the contact was last verified"
    )
    next_review_due: datetime | None = Field(
        None, description="Timestamp when re-validation should occur"
    )
    mx_failure_count: int = Field(
        0, ge=0, description="Consecutive MX validation failures"
    )
    tasks: list[str] = Field(
        default_factory=list,
        description="Follow-up tasks required to regain compliance",
    )
    lawful_basis: str | None = Field(
        None, description="Active lawful basis key for processing"
    )
    contact_purpose: str | None = Field(None, description="Current contact purpose key")

    model_config = {
        "json_schema_extra": {
            "version": CONTRACT_VERSION,
            "schema_uri": f"{SCHEMA_URI_BASE}/compliance-schedule-entry",
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
    metrics: dict[str, float] = Field(
        default_factory=dict,
        description="Pipeline execution metrics where values may be counts or rates",
    )
    sanity_findings: list[SanityCheckFindingContract] = Field(
        default_factory=list, description="Sanity check findings"
    )
    quality_issues: list[QualityIssueContract] = Field(
        default_factory=list, description="Quality gate issues"
    )
    compliance_schedule: list[ComplianceScheduleEntryContract] = Field(
        default_factory=list,
        description="Compliance re-validation schedule entries",
    )

    @property
    def issues(self) -> list[ValidationIssueContract]:
        """Get validation issues from the report."""
        # Access via object.__getattribute__ to avoid the class-level FieldInfo
        report = cast(
            ValidationReportContract,
            object.__getattribute__(self, "validation_report"),
        )
        return report.issues

    model_config = {
        "json_schema_extra": {
            "version": CONTRACT_VERSION,
            "schema_uri": f"{SCHEMA_URI_BASE}/pipeline-report",
        }
    }


class PlanArtifactContract(BaseModel):
    """Contract describing saved plan artefacts used by the plan→commit guard."""

    changes: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Ordered list of intended changes",
    )
    instructions: str = Field(..., description="Natural language summary of the plan")
    generated_at: datetime | None = Field(
        None, description="Optional timestamp recording plan creation time"
    )
    contract: ContractDescriptor = Field(
        ..., description="Embedded contract metadata for registry lookup"
    )

    model_config = {
        "json_schema_extra": {
            "version": CONTRACT_VERSION,
            "schema_uri": f"{SCHEMA_URI_BASE}/plan-artifact",
        }
    }


class CommitArtifactContract(BaseModel):
    """Contract describing commit artefacts captured during plan→commit."""

    if_match: str = Field(..., description="Opaque diff approval token")
    diff_summary: str = Field(..., description="Reviewer-facing summary of the diff")
    diff_format: str = Field(
        default="markdown", description="Format identifier for diff_summary"
    )
    rag: dict[str, float] = Field(
        default_factory=dict,
        description="Recorded Retrieval-Augmented Generation metrics",
    )
    contract: ContractDescriptor = Field(
        ..., description="Embedded contract metadata for registry lookup"
    )

    model_config = {
        "json_schema_extra": {
            "version": CONTRACT_VERSION,
            "schema_uri": f"{SCHEMA_URI_BASE}/commit-artifact",
        }
    }


# Schema export helpers
def export_json_schema(contract_class: type[BaseModel]) -> dict[str, Any]:
    """Export JSON Schema for a contract class."""

    return contract_class.model_json_schema(ref_template="{model}")


def export_all_schemas() -> dict[str, dict[str, Any]]:
    """Export JSON Schemas for all contract classes."""

    return {name: export_json_schema(model) for name, model in _CONTRACT_MODELS.items()}


def export_avro_schema(contract_class: type[BaseModel]) -> dict[str, Any]:
    """Generate an Avro schema for a contract class using JSON Schema metadata."""

    json_schema = contract_class.model_json_schema(ref_template="{model}")
    required_fields = set(json_schema.get("required", []))
    properties = json_schema.get("properties", {})

    fields: list[dict[str, Any]] = []
    for field_name, definition in properties.items():
        avro_type = _json_definition_to_avro_type(definition)
        if field_name not in required_fields:
            avro_type = _ensure_optional_type(avro_type)
        field_doc = definition.get("description")
        entry: dict[str, Any] = {"name": field_name, "type": avro_type}
        if field_doc:
            entry["doc"] = field_doc
        fields.append(entry)

    schema_uri = (
        json_schema.get("schema_uri")
        or f"{SCHEMA_URI_BASE}/{contract_class.__name__.lower()}"
    )

    return {
        "type": "record",
        "name": contract_class.__name__,
        "namespace": AVRO_NAMESPACE,
        "doc": (contract_class.__doc__ or "").strip(),
        "fields": fields,
        "watercrawl_version": CONTRACT_VERSION,
        "schema_uri": schema_uri,
    }


def export_all_avro_schemas() -> dict[str, dict[str, Any]]:
    """Export Avro schemas for all contract classes."""

    return {name: export_avro_schema(model) for name, model in _CONTRACT_MODELS.items()}


def export_contract_registry() -> dict[str, dict[str, Any]]:
    """Expose metadata used by CLI/MCP surfaces for schema discovery."""

    json_schemas = export_all_schemas()
    avro_schemas = export_all_avro_schemas()
    registry: dict[str, dict[str, Any]] = {}
    for name in _CONTRACT_MODELS:
        json_schema = json_schemas[name]
        registry[name] = {
            "version": json_schema.get("version", CONTRACT_VERSION),
            "schema_uri": json_schema.get("schema_uri"),
            "json_schema": json_schema,
            "avro_schema": avro_schemas[name],
        }
    return registry


def _json_definition_to_avro_type(definition: dict[str, Any]) -> Any:
    """Convert a JSON Schema property definition into an Avro type declaration."""

    if isinstance(definition, bool):
        # ``additionalProperties`` may be declared as false/true. Map to string values
        # to preserve compatibility with Avro's map semantics.
        return "string"

    if "$ref" in definition:
        ref = definition["$ref"]
        return ref.split("/")[-1]

    schema_type = definition.get("type")
    if schema_type == "string":
        return "string"
    if schema_type == "integer":
        return "int"
    if schema_type == "number":
        return "double"
    if schema_type == "boolean":
        return "boolean"
    if schema_type == "array":
        items = definition.get("items", {})
        return {"type": "array", "items": _json_definition_to_avro_type(items)}
    if schema_type == "object":
        additional = definition.get("additionalProperties")
        if not isinstance(additional, dict):
            additional = {"type": "string"}
        return {
            "type": "map",
            "values": _json_definition_to_avro_type(additional),
        }

    variants = definition.get("anyOf") or definition.get("oneOf")
    if variants:
        avro_members = [_json_definition_to_avro_type(item) for item in variants]
        return _ensure_optional_type(avro_members)

    if schema_type is None and "enum" in definition:
        return {
            "type": "enum",
            "name": definition.get("title", "Enum"),
            "symbols": definition["enum"],
        }

    return "string"


def _ensure_optional_type(avro_type: Any) -> Any:
    """Wrap an Avro type in a null union when representing optional fields."""

    if isinstance(avro_type, list):
        members = [value for value in avro_type if value != "null"]
        return ["null", *members]
    if isinstance(avro_type, dict) and avro_type.get("type") == "union":
        return ["null", *avro_type.get("types", [])]
    return ["null", avro_type]


_CONTRACT_MODELS: dict[str, type[BaseModel]] = {
    "ContractDescriptor": ContractDescriptor,
    "SchoolRecord": SchoolRecordContract,
    "EvidenceRecord": EvidenceRecordContract,
    "ComplianceScheduleEntry": ComplianceScheduleEntryContract,
    "QualityIssue": QualityIssueContract,
    "ValidationIssue": ValidationIssueContract,
    "ValidationReport": ValidationReportContract,
    "SanityCheckFinding": SanityCheckFindingContract,
    "PipelineReport": PipelineReportContract,
    "PlanArtifact": PlanArtifactContract,
    "CommitArtifact": CommitArtifactContract,
}


__all__ = [
    "CONTRACT_VERSION",
    "ContractDescriptor",
    "SchoolRecordContract",
    "EvidenceRecordContract",
    "ComplianceScheduleEntryContract",
    "QualityIssueContract",
    "ValidationIssueContract",
    "ValidationReportContract",
    "SanityCheckFindingContract",
    "PipelineReportContract",
    "PlanArtifactContract",
    "CommitArtifactContract",
    "export_json_schema",
    "export_all_schemas",
    "export_avro_schema",
    "export_all_avro_schemas",
    "export_contract_registry",
]
