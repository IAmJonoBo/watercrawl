"""Tests for Pydantic contract schemas and JSON Schema generation.

These tests verify:
- Contract models validate data correctly
- JSON Schema generation is stable (regression testing)
- Backward compatibility with legacy dataclass models
- Schema versioning and URI metadata
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from watercrawl.domain.contracts import (
    CONTRACT_VERSION,
    SCHEMA_URI_BASE,
    EvidenceRecordContract,
    PipelineReportContract,
    QualityIssueContract,
    SchoolRecordContract,
    ValidationIssueContract,
    ValidationReportContract,
    export_all_avro_schemas,
    export_all_schemas,
    export_contract_registry,
    export_json_schema,
)
from watercrawl.domain.models import (
    EvidenceRecord,
    PipelineReport,
    QualityIssue,
    RollbackPlan,
    SanityCheckFinding,
    SchoolRecord,
    ValidationIssue,
    ValidationReport,
    evidence_record_from_contract,
    evidence_record_to_contract,
    pipeline_report_from_contract,
    pipeline_report_to_contract,
    quality_issue_from_contract,
    quality_issue_to_contract,
    school_record_from_contract,
    school_record_to_contract,
    validation_issue_from_contract,
    validation_issue_to_contract,
)


class TestSchoolRecordContract:
    """Tests for SchoolRecordContract."""

    def test_valid_school_record(self):
        """Test creating a valid school record contract."""
        record = SchoolRecordContract(
            name="Test Flight School",
            province="Gauteng",
            status="Verified",
            website_url="https://testflightschool.co.za",
            contact_person="Amina Dlamini",
            contact_number="+27123456789",
            contact_email="amina@testflightschool.co.za",
        )
        assert record.name == "Test Flight School"
        assert record.province == "Gauteng"
        assert record.status == "Verified"

    def test_rejects_empty_name(self):
        """Test that empty name is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SchoolRecordContract(
                name="",
                province="Gauteng",
                status="Verified",
            )
        assert "name" in str(exc_info.value)

    def test_rejects_invalid_province(self):
        """Test that invalid province is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SchoolRecordContract(
                name="Test School",
                province="Atlantis",
                status="Verified",
            )
        assert "province" in str(exc_info.value).lower()

    def test_rejects_invalid_status(self):
        """Test that invalid status is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SchoolRecordContract(
                name="Test School",
                province="Gauteng",
                status="InvalidStatus",
            )
        assert "status" in str(exc_info.value).lower()

    def test_allows_optional_fields(self):
        """Test that optional fields can be omitted."""
        record = SchoolRecordContract(
            name="Test School",
            province="Gauteng",
            status="Verified",
        )
        assert record.website_url is None
        assert record.contact_person is None

    def test_json_schema_includes_metadata(self):
        """Test that JSON schema includes version and URI."""
        schema = export_json_schema(SchoolRecordContract)
        assert schema["version"] == CONTRACT_VERSION
        assert "schema_uri" in schema
        assert "/school-record" in schema["schema_uri"]


class TestEvidenceRecordContract:
    """Tests for EvidenceRecordContract."""

    def test_valid_evidence_record(self):
        """Test creating a valid evidence record contract."""
        record = EvidenceRecordContract(
            row_id=1,
            organisation="Test School",
            changes="Updated website URL",
            sources=["https://example.com"],
            notes="Verified via website",
            confidence=85,
        )
        assert record.row_id == 1
        assert record.organisation == "Test School"
        assert len(record.sources) == 1

    def test_rejects_negative_row_id(self):
        """Test that negative row_id is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EvidenceRecordContract(
                row_id=-1,
                organisation="Test School",
                changes="Test",
                confidence=85,
            )
        assert "row_id" in str(exc_info.value)

    def test_rejects_invalid_confidence(self):
        """Test that confidence out of range is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EvidenceRecordContract(
                row_id=1,
                organisation="Test School",
                changes="Test",
                confidence=150,
            )
        assert "confidence" in str(exc_info.value)

    def test_timestamp_defaults_to_now(self):
        """Test that timestamp defaults to current time."""
        before = datetime.now(UTC)
        record = EvidenceRecordContract(
            row_id=1,
            organisation="Test School",
            changes="Test",
            confidence=85,
        )
        after = datetime.now(UTC)
        assert before <= record.timestamp <= after

    def test_allows_custom_timestamp(self):
        """Test that custom timestamp can be provided."""
        custom_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        record = EvidenceRecordContract(
            row_id=1,
            organisation="Test School",
            changes="Test",
            confidence=85,
            timestamp=custom_time,
        )
        assert record.timestamp == custom_time


class TestQualityIssueContract:
    """Tests for QualityIssueContract."""

    def test_valid_quality_issue(self):
        """Test creating a valid quality issue contract."""
        issue = QualityIssueContract(
            row_id=1,
            organisation="Test School",
            code="MISSING_EMAIL",
            severity="warn",
            message="Email address is missing",
            remediation="Add email address",
        )
        assert issue.code == "MISSING_EMAIL"
        assert issue.severity == "warn"

    def test_rejects_invalid_severity(self):
        """Test that invalid severity is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            QualityIssueContract(
                row_id=1,
                organisation="Test School",
                code="TEST",
                severity="critical",  # Invalid, must be 'block' or 'warn'
                message="Test message",
            )
        assert "severity" in str(exc_info.value)

    def test_allows_null_remediation(self):
        """Test that remediation can be None."""
        issue = QualityIssueContract(
            row_id=1,
            organisation="Test School",
            code="TEST",
            severity="warn",
            message="Test message",
            remediation=None,
        )
        assert issue.remediation is None


class TestValidationContracts:
    """Tests for validation-related contracts."""

    def test_validation_issue_contract(self):
        """Test ValidationIssueContract."""
        issue = ValidationIssueContract(
            code="INVALID_DATA",
            message="Data is invalid",
            row=5,
            column="Email",
        )
        assert issue.code == "INVALID_DATA"
        assert issue.row == 5

    def test_validation_report_is_valid_property(self):
        """Test is_valid property on ValidationReportContract."""
        # Valid report (no issues)
        report = ValidationReportContract(issues=[], rows=10)
        assert report.is_valid

        # Invalid report (has issues)
        issue = ValidationIssueContract(
            code="TEST", message="Test", row=1, column="test"
        )
        report = ValidationReportContract(issues=[issue], rows=10)
        assert not report.is_valid


class TestPipelineReportContract:
    """Tests for PipelineReportContract."""

    def test_valid_pipeline_report(self):
        """Test creating a valid pipeline report contract."""
        validation = ValidationReportContract(issues=[], rows=10)
        report = PipelineReportContract(
            validation_report=validation,
            evidence_log=[],
            metrics={"rows_processed": 10, "rows_updated": 5},
        )
        assert report.metrics["rows_processed"] == 10
        assert len(report.evidence_log) == 0

    def test_issues_property(self):
        """Test that issues property returns validation issues."""
        issue = ValidationIssueContract(
            code="TEST", message="Test", row=1, column="test"
        )
        validation = ValidationReportContract(issues=[issue], rows=10)
        report = PipelineReportContract(
            validation_report=validation,
            evidence_log=[],
            metrics={},
        )
        assert len(report.issues) == 1
        assert report.issues[0].code == "TEST"


class TestContractAdapters:
    """Tests for contract adapter functions."""

    def test_school_record_roundtrip(self):
        """Test converting SchoolRecord to contract and back."""
        original = SchoolRecord(
            name="Test School",
            province="Gauteng",
            status="Verified",
            website_url="https://test.co.za",
            contact_person="John Doe",
            contact_number="+27123456789",
            contact_email="john@test.co.za",
        )
        contract = school_record_to_contract(original)
        converted = school_record_from_contract(contract)

        assert converted.name == original.name
        assert converted.province == original.province
        assert converted.status == original.status
        assert converted.website_url == original.website_url

    def test_evidence_record_roundtrip(self):
        """Test converting EvidenceRecord to contract and back."""
        timestamp = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        original = EvidenceRecord(
            row_id=1,
            organisation="Test School",
            changes="Updated contact",
            sources=["https://source.com"],
            notes="Test notes",
            confidence=85,
            timestamp=timestamp,
        )
        contract = evidence_record_to_contract(original)
        converted = evidence_record_from_contract(contract)

        assert converted.row_id == original.row_id
        assert converted.organisation == original.organisation
        assert converted.timestamp == original.timestamp

    def test_quality_issue_roundtrip(self):
        """Test converting QualityIssue to contract and back."""
        original = QualityIssue(
            row_id=1,
            organisation="Test School",
            code="TEST_CODE",
            severity="warn",
            message="Test message",
            remediation="Fix it",
        )
        contract = quality_issue_to_contract(original)
        converted = quality_issue_from_contract(contract)

        assert converted.row_id == original.row_id
        assert converted.code == original.code
        assert converted.severity == original.severity

    def test_validation_issue_roundtrip(self):
        """Test converting ValidationIssue to contract and back."""
        original = ValidationIssue(
            code="TEST_CODE",
            message="Test message",
            row=5,
            column="email",
        )
        contract = validation_issue_to_contract(original)
        converted = validation_issue_from_contract(contract)

        assert converted.code == original.code
        assert converted.message == original.message
        assert converted.row == original.row

    def test_adapter_type_checking(self):
        """Test that adapters reject wrong types."""
        with pytest.raises(TypeError):
            school_record_from_contract("not a contract")

        with pytest.raises(TypeError):
            evidence_record_from_contract("not a contract")

        with pytest.raises(TypeError):
            quality_issue_from_contract("not a contract")


SNAPSHOT_DIR = Path(__file__).resolve().parents[1] / "data_contracts" / "registry"
JSON_SCHEMA_SNAPSHOT = SNAPSHOT_DIR / "json_schemas_v1.json"
AVRO_SCHEMA_SNAPSHOT = SNAPSHOT_DIR / "avro_schemas_v1.json"
REGISTRY_SNAPSHOT = SNAPSHOT_DIR / "registry_v1.json"


class TestSchemaExport:
    """Tests for JSON Schema export functionality."""

    def test_export_json_schema(self):
        """Test exporting JSON schema for a single contract."""
        schema = export_json_schema(SchoolRecordContract)
        assert isinstance(schema, dict)
        assert "properties" in schema
        assert "name" in schema["properties"]
        assert "province" in schema["properties"]

    def test_export_all_schemas(self):
        """Test exporting all contract schemas."""
        all_schemas = export_all_schemas()
        assert isinstance(all_schemas, dict)
        assert "SchoolRecord" in all_schemas
        assert "EvidenceRecord" in all_schemas
        assert "QualityIssue" in all_schemas
        assert "ValidationIssue" in all_schemas
        assert "PipelineReport" in all_schemas

    def test_schema_stability_regression(self):
        """Compare exported JSON schemas against the checked-in snapshot."""

        all_schemas = export_all_schemas()
        snapshot = json.loads(JSON_SCHEMA_SNAPSHOT.read_text(encoding="utf-8"))
        assert json.dumps(all_schemas, sort_keys=True) == json.dumps(
            snapshot, sort_keys=True
        )

    def test_avro_schema_regression(self):
        """Compare exported Avro schemas against the snapshot."""

        all_avro = export_all_avro_schemas()
        snapshot = json.loads(AVRO_SCHEMA_SNAPSHOT.read_text(encoding="utf-8"))
        assert json.dumps(all_avro, sort_keys=True) == json.dumps(
            snapshot, sort_keys=True
        )

    def test_all_schemas_include_version(self):
        """Test that all exported schemas include version metadata."""
        all_schemas = export_all_schemas()
        for schema_name, schema in all_schemas.items():
            assert "version" in schema, f"{schema_name} missing version"
            assert schema["version"] == CONTRACT_VERSION

    def test_all_schemas_include_schema_uri(self):
        """Ensure each exported JSON schema exposes a canonical URI."""

        all_schemas = export_all_schemas()
        for schema_name, schema in all_schemas.items():
            uri = schema.get("schema_uri")
            assert uri, f"{schema_name} missing schema URI"
            assert str(uri).startswith(SCHEMA_URI_BASE)

    def test_avro_schemas_include_metadata(self):
        """Avro exports should include schema URIs and the contract version."""

        all_avro = export_all_avro_schemas()
        for schema_name, schema in all_avro.items():
            assert schema.get("watercrawl_version") == CONTRACT_VERSION
            uri = schema.get("schema_uri")
            assert uri, f"{schema_name} missing schema URI"
            assert str(uri).startswith(SCHEMA_URI_BASE)

    def test_registry_snapshot(self):
        """Ensure the public registry metadata remains stable."""

        registry = export_contract_registry()
        snapshot = json.loads(REGISTRY_SNAPSHOT.read_text(encoding="utf-8"))
        assert json.dumps(registry, sort_keys=True) == json.dumps(
            snapshot, sort_keys=True
        )


class TestContractSerialization:
    """Tests for contract serialization to JSON."""

    def test_school_record_serialization(self):
        """Test serializing SchoolRecordContract to JSON."""
        record = SchoolRecordContract(
            name="Test School",
            province="Gauteng",
            status="Verified",
            website_url="https://test.co.za",
        )
        data = record.model_dump()
        assert data["name"] == "Test School"
        assert data["province"] == "Gauteng"

        # Test JSON roundtrip
        json_str = record.model_dump_json()
        parsed = SchoolRecordContract.model_validate_json(json_str)
        assert parsed.name == record.name

    def test_evidence_record_serialization(self):
        """Test serializing EvidenceRecordContract to JSON."""
        timestamp = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        record = EvidenceRecordContract(
            row_id=1,
            organisation="Test School",
            changes="Test changes",
            sources=["https://source.com"],
            confidence=85,
            timestamp=timestamp,
        )
        data = record.model_dump()
        assert data["row_id"] == 1
        assert isinstance(data["sources"], list)

        # Test JSON roundtrip with datetime
        json_str = record.model_dump_json()
        parsed = EvidenceRecordContract.model_validate_json(json_str)
        assert parsed.timestamp == timestamp

    def test_pipeline_report_serialization(self):
        """Test serializing complete PipelineReportContract to JSON."""
        validation = ValidationReportContract(issues=[], rows=10)
        evidence = EvidenceRecordContract(
            row_id=1,
            organisation="Test",
            changes="Test",
            confidence=85,
        )
        report = PipelineReportContract(
            validation_report=validation,
            evidence_log=[evidence],
            metrics={"processed": 10},
        )

        json_str = report.model_dump_json()
        parsed = PipelineReportContract.model_validate_json(json_str)
        assert len(parsed.evidence_log) == 1
        assert parsed.metrics["processed"] == 10


class TestPipelineReportAdapters:
    """Tests for converting pipeline reports between legacy and contracts."""

    def test_pipeline_report_roundtrip(self):
        """PipelineReport converts to contract and back without loss."""

        validation = ValidationReport(issues=[], rows=5)
        evidence = [
            EvidenceRecord(
                row_id=1,
                organisation="Test School",
                changes="Updated website",
                sources=["https://example.com"],
                notes="Confirmed",
                confidence=90,
            )
        ]
        quality = [
            QualityIssue(
                row_id=1,
                organisation="Test School",
                code="missing_phone",
                severity="warn",
                message="Missing phone",
                remediation="Call back",
            )
        ]
        sanity = [
            SanityCheckFinding(
                row_id=1,
                organisation="Test School",
                issue="Duplicate",
                remediation="Merge duplicates",
            )
        ]
        report = PipelineReport(
            refined_dataframe=None,
            validation_report=validation,
            evidence_log=evidence,
            metrics={"rows_total": 1},
            sanity_findings=sanity,
            quality_issues=quality,
            rollback_plan=RollbackPlan(actions=[]),
        )

        contract = pipeline_report_to_contract(report)
        restored = pipeline_report_from_contract(contract)

        assert restored.validation_report.rows == report.validation_report.rows
        assert restored.metrics == report.metrics
        assert restored.quality_issues[0].code == quality[0].code
        assert restored.sanity_findings[0].issue == sanity[0].issue
