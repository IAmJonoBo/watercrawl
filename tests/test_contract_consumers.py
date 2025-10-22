"""Contract consumer tests ensuring outputs validate against published schemas.

These tests verify:
- MCP responses validate against schemas
- Evidence logs validate against EvidenceRecordContract
- Plan→commit artefacts validate against their respective contracts
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from firecrawl_demo.domain.contracts import (
    EvidenceRecordContract,
    PipelineReportContract,
    SchoolRecordContract,
    ValidationReportContract,
)


@pytest.mark.contract
def test_evidence_record_contract_validation() -> None:
    """Test that EvidenceRecordContract validates correctly."""
    valid_record = {
        "row_id": 1,
        "organisation": "Test School",
        "changes": "Status -> Verified",
        "sources": ["https://test.co.za"],
        "notes": "Test note",
        "timestamp": "2025-01-01T00:00:00+00:00",
        "confidence": 90,
    }
    
    # Should validate without errors
    contract = EvidenceRecordContract(**valid_record)
    assert contract.row_id == 1
    assert contract.organisation == "Test School"
    assert contract.confidence == 90


@pytest.mark.contract
def test_evidence_record_contract_rejects_invalid() -> None:
    """Test that EvidenceRecordContract rejects invalid data."""
    invalid_record = {
        "row_id": "not_a_number",  # Should be int
        "organisation": "Test School",
        "changes": "Status -> Verified",
        "sources": ["https://test.co.za"],
        "notes": "Test note",
        "timestamp": "2025-01-01T00:00:00+00:00",
        "confidence": 90,
    }
    
    with pytest.raises((ValueError, TypeError)):
        EvidenceRecordContract(**invalid_record)


@pytest.mark.contract
def test_school_record_contract_validation() -> None:
    """Test that SchoolRecordContract validates correctly."""
    valid_record = {
        "name": "Test School",
        "province": "Gauteng",
        "status": "Verified",
        "website_url": "https://test.co.za",
        "contact_person": "John Doe",
        "contact_number": "+27105550100",
        "contact_email": "john@test.co.za",
    }
    
    contract = SchoolRecordContract(**valid_record)
    assert contract.name == "Test School"
    assert contract.province == "Gauteng"
    assert contract.status == "Verified"


@pytest.mark.contract
def test_pipeline_report_contract_validation() -> None:
    """Test that PipelineReportContract validates with minimal data."""
    # Create minimal valid report
    minimal_report = {
        "metrics": {
            "rows_total": 1,
            "enriched_rows": 0,
            "verified_rows": 0,
            "issues_found": 0,
        },
        "validation_issues": [],
        "evidence_log": [],
        "sanity_findings": [],
        "quality_issues": [],
    }
    
    contract = PipelineReportContract(**minimal_report)
    assert contract.metrics["rows_total"] == 1


@pytest.mark.contract
def test_validation_report_contract() -> None:
    """Test ValidationReportContract."""
    report = {
        "issues": [
            {
                "code": "test_code",
                "message": "Test message",
                "row": 1,
                "column": "TestColumn",
            }
        ],
        "rows": 10,
    }
    
    contract = ValidationReportContract(**report)
    assert contract.rows == 10
    assert len(contract.issues) == 1


@pytest.mark.contract
def test_mcp_response_schema_validation(tmp_path: Path) -> None:
    """Test that MCP responses include schema URIs and validate."""
    # Simulate MCP response with embedded contract
    mcp_response = {
        "status": "ok",
        "result": {
            "name": "Test School",
            "province": "Gauteng",
            "status": "Candidate",
            "website_url": "",
            "contact_person": "",
            "contact_number": "",
            "contact_email": "",
        },
        "schema_uri": "https://watercrawl.acesaero.co.za/schemas/v1/school-record",
        "schema_version": "1.0.0",
    }
    
    # Validate the embedded record
    record_contract = SchoolRecordContract(**mcp_response["result"])
    assert record_contract.name == "Test School"
    
    # Verify schema metadata is present
    assert "schema_uri" in mcp_response
    assert "schema_version" in mcp_response


@pytest.mark.contract
def test_plan_commit_artifact_structure(tmp_path: Path) -> None:
    """Test that plan→commit artifacts follow expected structure."""
    # Simulate plan artifact
    plan_artifact = {
        "action": "enrich",
        "dataset": "flight_schools",
        "proposed_changes": [
            {
                "row_id": 1,
                "field": "Status",
                "old_value": "Candidate",
                "new_value": "Verified",
                "reason": "Quality gate passed",
            }
        ],
        "timestamp": "2025-01-01T00:00:00+00:00",
    }
    
    # Write and read back
    plan_path = tmp_path / "test.plan"
    plan_path.write_text(json.dumps(plan_artifact, indent=2))
    
    loaded = json.loads(plan_path.read_text())
    assert loaded["action"] == "enrich"
    assert len(loaded["proposed_changes"]) == 1


@pytest.mark.contract
def test_evidence_log_csv_format(tmp_path: Path) -> None:
    """Test that evidence log CSV matches expected format."""
    import pandas as pd
    
    # Create sample evidence log
    evidence_data = {
        "RowID": [1, 2],
        "Organisation": ["School 1", "School 2"],
        "What changed": ["Status -> Verified", "Phone -> +27105550100"],
        "Sources": ["https://test.co.za", "https://test2.co.za"],
        "Notes": ["Note 1", "Note 2"],
        "Timestamp": ["2025-01-01T00:00:00+00:00", "2025-01-01T00:00:00+00:00"],
        "Confidence": [90, 85],
    }
    
    df = pd.DataFrame(evidence_data)
    evidence_path = tmp_path / "evidence.csv"
    df.to_csv(evidence_path, index=False)
    
    # Read back and validate
    loaded = pd.read_csv(evidence_path)
    assert len(loaded) == 2
    assert "RowID" in loaded.columns
    assert "Confidence" in loaded.columns
    
    # Validate each row can be converted to contract
    for _, row in loaded.iterrows():
        contract = EvidenceRecordContract(
            row_id=int(row["RowID"]),
            organisation=row["Organisation"],
            changes=row["What changed"],
            sources=[row["Sources"]],  # Single source for simplicity
            notes=row["Notes"],
            timestamp=row["Timestamp"],
            confidence=int(row["Confidence"]),
        )
        assert contract.row_id > 0


@pytest.mark.contract
def test_schema_export_completeness() -> None:
    """Test that all schemas can be exported."""
    from firecrawl_demo.domain.contracts import export_all_schemas
    
    schemas = export_all_schemas()
    
    # Verify key schemas are present
    assert "SchoolRecord" in schemas
    assert "EvidenceRecord" in schemas
    assert "PipelineReport" in schemas
    assert "ValidationReport" in schemas
    
    # Each schema should have required fields
    for schema_name, schema in schemas.items():
        assert "properties" in schema or "type" in schema, f"{schema_name} missing structure"
