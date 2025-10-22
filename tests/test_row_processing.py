"""Tests for row processing module."""

from __future__ import annotations

import pytest

from firecrawl_demo.application.quality import QualityGate
from firecrawl_demo.application.row_processing import RowProcessor
from firecrawl_demo.domain.models import SchoolRecord
from firecrawl_demo.integrations.adapters.research import ResearchFinding


def test_row_processor_normalizes_province():
    """Test that province is normalized."""
    processor = RowProcessor(
        quality_gate=QualityGate(min_confidence=0, require_official_source=False)
    )
    original = SchoolRecord(
        name="Test School",
        province="gauteng",  # lowercase
        status="Candidate",
        website_url="",
        contact_person="",
        contact_number="",
        contact_email="",
    )
    finding = ResearchFinding()
    
    result = processor.process_row(
        original_record=original,
        finding=finding,
        row_id=1,
    )
    
    assert result.final_record.province == "Gauteng"


def test_row_processor_enriches_from_finding():
    """Test that finding data enriches the record."""
    processor = RowProcessor(
        quality_gate=QualityGate(min_confidence=0, require_official_source=False)
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
    finding = ResearchFinding(
        website_url="https://test.co.za",
        contact_person="John Doe",
        contact_phone="+27105550100",
        contact_email="john@test.co.za",
        sources=["https://test.co.za", "https://caa.co.za/test"],
        confidence=90,
    )
    
    result = processor.process_row(
        original_record=original,
        finding=finding,
        row_id=1,
    )
    
    assert result.updated is True
    assert result.final_record.website_url == "https://test.co.za"
    assert result.final_record.contact_person == "John Doe"
    assert result.final_record.contact_number == "+27105550100"
    assert result.final_record.contact_email == "john@test.co.za"
    assert result.final_record.status == "Verified"
    assert result.confidence == 90


def test_row_processor_normalizes_phone():
    """Test that phone numbers are normalized."""
    processor = RowProcessor(
        quality_gate=QualityGate(min_confidence=0, require_official_source=False)
    )
    original = SchoolRecord(
        name="Test School",
        province="Gauteng",
        status="Candidate",
        website_url="",
        contact_person="",
        contact_number="011 555 0100",  # Not in E.164 format
        contact_email="",
    )
    finding = ResearchFinding(
        sources=["https://test.co.za", "https://caa.co.za/test"],
    )
    
    result = processor.process_row(
        original_record=original,
        finding=finding,
        row_id=1,
    )
    
    assert result.final_record.contact_number == "+27115550100"


def test_row_processor_removes_invalid_phone():
    """Test that invalid phone numbers are removed."""
    processor = RowProcessor(
        quality_gate=QualityGate(min_confidence=0, require_official_source=False)
    )
    original = SchoolRecord(
        name="Test School",
        province="Gauteng",
        status="Candidate",
        website_url="",
        contact_person="",
        contact_number="invalid",
        contact_email="",
    )
    finding = ResearchFinding(
        sources=["https://test.co.za", "https://caa.co.za/test"],
    )
    
    result = processor.process_row(
        original_record=original,
        finding=finding,
        row_id=1,
    )
    
    assert result.final_record.contact_number is None
    assert "Contact Number" in result.cleared_columns
    assert any(
        f.issue == "contact_number_invalid" for f in result.sanity_findings
    )


def test_row_processor_validates_email():
    """Test that email addresses are validated."""
    processor = RowProcessor(
        quality_gate=QualityGate(min_confidence=0, require_official_source=False)
    )
    original = SchoolRecord(
        name="Test School",
        province="Gauteng",
        status="Candidate",
        website_url="https://test.co.za",
        contact_person="",
        contact_number="",
        contact_email="invalid-email",
    )
    finding = ResearchFinding(
        sources=["https://test.co.za", "https://caa.co.za/test"],
    )
    
    result = processor.process_row(
        original_record=original,
        finding=finding,
        row_id=1,
    )
    
    assert result.final_record.contact_email is None
    assert "Contact Email Address" in result.cleared_columns
    assert any(
        f.issue == "contact_email_invalid" for f in result.sanity_findings
    )


def test_row_processor_adds_url_scheme():
    """Test that missing URL schemes are added."""
    processor = RowProcessor(
        quality_gate=QualityGate(min_confidence=0, require_official_source=False)
    )
    original = SchoolRecord(
        name="Test School",
        province="Gauteng",
        status="Candidate",
        website_url="test.co.za",  # Missing scheme
        contact_person="",
        contact_number="",
        contact_email="",
    )
    finding = ResearchFinding(
        sources=["https://test.co.za", "https://caa.co.za/test"],
    )
    
    result = processor.process_row(
        original_record=original,
        finding=finding,
        row_id=1,
    )
    
    assert result.final_record.website_url == "https://test.co.za"
    assert any(
        f.issue == "website_url_missing_scheme" for f in result.sanity_findings
    )


def test_row_processor_quality_gate_rejection():
    """Test that quality gate rejections work correctly."""
    processor = RowProcessor(
        quality_gate=QualityGate(
            min_confidence=80,
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
    # Finding with low confidence and no official source
    finding = ResearchFinding(
        website_url="https://test.com",
        contact_person="John Doe",
        sources=["https://test.com"],  # Not official
        confidence=50,  # Below threshold
    )
    
    result = processor.process_row(
        original_record=original,
        finding=finding,
        row_id=1,
    )
    
    # Changes should be rejected
    assert result.quality_issues
    assert result.rollback_action is not None
    assert result.final_record.status == "Needs Review"
    assert result.final_record.website_url == ""  # Rolled back


def test_row_processor_quality_gate_acceptance():
    """Test that quality gate accepts good changes."""
    processor = RowProcessor(
        quality_gate=QualityGate(
            min_confidence=80,
            require_official_source=False,
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
    finding = ResearchFinding(
        website_url="https://test.co.za",
        contact_person="John Doe",
        sources=["https://test.co.za", "https://other.co.za"],
        confidence=90,
    )
    
    result = processor.process_row(
        original_record=original,
        finding=finding,
        row_id=1,
    )
    
    # Changes should be accepted
    assert not result.quality_issues
    assert result.rollback_action is None
    assert result.final_record.website_url == "https://test.co.za"
    assert result.confidence == 90


def test_row_processor_source_counting():
    """Test that sources are counted correctly."""
    processor = RowProcessor(
        quality_gate=QualityGate(min_confidence=0, require_official_source=False)
    )
    original = SchoolRecord(
        name="Test School",
        province="Gauteng",
        status="Candidate",
        website_url="https://test.co.za",
        contact_person="",
        contact_number="",
        contact_email="",
    )
    finding = ResearchFinding(
        sources=[
            "https://test.co.za",  # Existing source
            "https://caa.co.za/test",  # Official fresh source
            "https://other.co.za",  # Fresh source
        ],
    )
    
    result = processor.process_row(
        original_record=original,
        finding=finding,
        row_id=1,
    )
    
    total, fresh, official, official_fresh = result.source_counts
    assert total == 3
    assert fresh == 2  # Two new sources
    assert official == 1  # One official source
    assert official_fresh == 1  # One official fresh source


def test_row_processor_unknown_province_finding():
    """Test that unknown province is flagged."""
    processor = RowProcessor(
        quality_gate=QualityGate(min_confidence=0, require_official_source=False)
    )
    original = SchoolRecord(
        name="Test School",
        province="",  # Will become Unknown
        status="Candidate",
        website_url="",
        contact_person="",
        contact_number="",
        contact_email="",
    )
    finding = ResearchFinding(
        sources=["https://test.co.za"],
    )
    
    result = processor.process_row(
        original_record=original,
        finding=finding,
        row_id=1,
    )
    
    assert result.final_record.province == "Unknown"
    assert any(
        f.issue == "province_unknown" for f in result.sanity_findings
    )


def test_row_processor_no_changes():
    """Test processing when no changes are made."""
    processor = RowProcessor(
        quality_gate=QualityGate(min_confidence=0, require_official_source=False)
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
    finding = ResearchFinding()  # Empty finding
    
    result = processor.process_row(
        original_record=original,
        finding=finding,
        row_id=1,
    )
    
    assert result.updated is False
    assert not result.changed_columns
    assert result.confidence == 0
