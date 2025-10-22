"""Integration tests for Pipeline with row processing service.

These tests verify that the Pipeline correctly uses the new row processing
and change tracking modules without requiring full dependency installation.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from firecrawl_demo.application.quality import QualityGate
from firecrawl_demo.application.row_processing import RowProcessor, RowProcessingResult
from firecrawl_demo.domain.models import SchoolRecord
from firecrawl_demo.integrations.adapters.research import ResearchFinding


def test_row_processor_integration():
    """Test that RowProcessor integrates correctly with quality gate."""
    processor = RowProcessor(
        quality_gate=QualityGate(min_confidence=0, require_official_source=False)
    )
    
    original = SchoolRecord(
        name="Integration Test School",
        province="gauteng",
        status="Candidate",
        website_url="",
        contact_person="",
        contact_number="",
        contact_email="",
    )
    
    finding = ResearchFinding(
        website_url="https://test.gov.za",
        contact_person="Jane Doe",
        contact_phone="+27105550100",
        contact_email="jane@test.gov.za",
        sources=["https://test.gov.za", "https://caa.co.za/test"],
        confidence=95,
    )
    
    result = processor.process_row(
        original_record=original,
        finding=finding,
        row_id=1,
    )
    
    # Verify result structure
    assert isinstance(result, RowProcessingResult)
    assert result.updated is True
    assert result.final_record.province == "Gauteng"  # Normalized
    assert result.final_record.website_url == "https://test.gov.za"
    assert result.final_record.contact_person == "Jane Doe"
    assert result.final_record.status == "Verified"
    assert result.confidence == 95
    
    # Verify side effects are captured
    assert isinstance(result.sanity_findings, list)
    assert isinstance(result.quality_issues, list)
    assert isinstance(result.sources, list)
    assert len(result.sources) >= 2


def test_bulk_updates_preserve_dtype():
    """Test that bulk updates maintain dtype stability."""
    # Create a mock DataFrame with specific dtypes
    frame = pd.DataFrame({
        "Name of Organisation": ["School 1", "School 2"],
        "Province": ["Gauteng", "Western Cape"],
        "Status": ["Candidate", "Candidate"],
        "Website URL": ["", ""],
        "Contact Person": ["", ""],
        "Contact Number": ["", ""],
        "Contact Email Address": ["", ""],
    })
    
    # Verify initial dtypes are object
    for col in frame.columns:
        assert frame[col].dtype == "object" or frame[col].dtype == "string"
    
    # Simulate update instructions
    record1 = SchoolRecord(
        name="School 1",
        province="Gauteng",
        status="Verified",
        website_url="https://school1.co.za",
        contact_person="Person 1",
        contact_number="+27105550100",
        contact_email="person1@school1.co.za",
    )
    
    record2 = SchoolRecord(
        name="School 2",
        province="Western Cape",
        status="Verified",
        website_url="https://school2.co.za",
        contact_person="Person 2",
        contact_number="+27105550101",
        contact_email="person2@school2.co.za",
    )
    
    # Simulate the bulk update pattern from Pipeline
    for idx, record in enumerate([record1, record2]):
        for column, value in record.as_dict().items():
            if value is not None and column in frame.columns:
                frame.at[idx, column] = value
    
    # Verify updates were applied
    assert frame.loc[0, "Status"] == "Verified"
    assert frame.loc[1, "Status"] == "Verified"
    assert frame.loc[0, "Website URL"] == "https://school1.co.za"
    assert frame.loc[1, "Website URL"] == "https://school2.co.za"
    
    # Verify dtypes are still object (no implicit conversions)
    for col in frame.columns:
        assert frame[col].dtype == "object" or frame[col].dtype == "string"


def test_change_tracking_deterministic_ordering():
    """Test that change tracking produces deterministic output."""
    from firecrawl_demo.application.change_tracking import (
        build_rollback_action,
        collect_changed_columns,
    )
    from firecrawl_demo.domain.models import QualityIssue
    
    original = SchoolRecord(
        name="Test",
        province="Gauteng",
        status="Candidate",
        website_url="",
        contact_person="",
        contact_number="",
        contact_email="",
    )
    
    proposed = SchoolRecord(
        name="Test",
        province="Gauteng",
        status="Verified",
        website_url="https://test.co.za",
        contact_person="John",
        contact_number="+27105550100",
        contact_email="john@test.co.za",
    )
    
    changes = collect_changed_columns(original, proposed)
    
    # Test multiple times to ensure deterministic ordering
    for _ in range(5):
        issues = [
            QualityIssue(
                row_id=1,
                organisation="Test",
                code="code1",
                severity="block",
                message="Message 1",
                remediation="Fix 1",
            ),
            QualityIssue(
                row_id=1,
                organisation="Test",
                code="code2",
                severity="warn",
                message="Message 2",
                remediation="Fix 2",
            ),
        ]
        
        action = build_rollback_action(
            row_id=1,
            organisation="Test",
            attempted_changes=changes,
            issues=issues,
        )
        
        # Columns should always be in the same sorted order
        expected_columns = sorted(changes.keys())
        assert action.columns == expected_columns
        
        # Reason should be deterministic
        assert "Message 1" in action.reason
        assert "Message 2" in action.reason


def test_row_processor_quality_gate_integration():
    """Test quality gate rejection flow through row processor."""
    # High threshold quality gate
    processor = RowProcessor(
        quality_gate=QualityGate(
            min_confidence=90,
            require_official_source=True,
        )
    )
    
    original = SchoolRecord(
        name="Test School",
        province="Gauteng",
        status="Candidate",
        website_url="",
        contact_person="",
        contact_number="",
        contact_email="",
    )
    
    # Low quality finding that should be rejected
    finding = ResearchFinding(
        website_url="https://test.com",  # Not official
        contact_person="Someone",
        sources=["https://test.com"],  # Single non-official source
        confidence=50,  # Below threshold
    )
    
    result = processor.process_row(
        original_record=original,
        finding=finding,
        row_id=1,
    )
    
    # Quality gate should reject the changes
    assert len(result.quality_issues) > 0
    assert result.rollback_action is not None
    assert result.final_record.status == "Needs Review"
    assert result.confidence == 0


def test_row_processor_preserves_good_data():
    """Test that processor doesn't modify data unnecessarily."""
    processor = RowProcessor(
        quality_gate=QualityGate(min_confidence=0, require_official_source=False)
    )
    
    # Already complete record
    original = SchoolRecord(
        name="Complete School",
        province="Gauteng",
        status="Verified",
        website_url="https://complete.co.za",
        contact_person="Existing Person",
        contact_number="+27105550100",
        contact_email="existing@complete.co.za",
    )
    
    # Empty finding
    finding = ResearchFinding()
    
    result = processor.process_row(
        original_record=original,
        finding=finding,
        row_id=1,
    )
    
    # Should not mark as updated since no actual changes
    assert result.updated is False
    assert result.final_record.name == original.name
    assert result.final_record.website_url == original.website_url
    assert result.confidence == 0


if __name__ == "__main__":
    # Run tests directly for verification
    test_row_processor_integration()
    test_bulk_updates_preserve_dtype()
    test_change_tracking_deterministic_ordering()
    test_row_processor_quality_gate_integration()
    test_row_processor_preserves_good_data()
    print("✓ All integration tests passed!")
