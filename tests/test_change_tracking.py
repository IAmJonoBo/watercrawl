"""Tests for change tracking utilities."""

from __future__ import annotations

import pandas as pd
import pytest

from firecrawl_demo.application.change_tracking import (
    build_rollback_action,
    collect_changed_columns,
    describe_changes,
)
from firecrawl_demo.domain.models import QualityIssue, SchoolRecord


def test_collect_changed_columns_detects_changes():
    """Test that changed columns are correctly detected."""
    original = SchoolRecord(
        name="Test School",
        province="Gauteng",
        status="Candidate",
        website_url="",
        contact_person="",
        contact_number="",
        contact_email="",
    )
    proposed = SchoolRecord(
        name="Test School",
        province="Gauteng",
        status="Verified",
        website_url="https://test.co.za",
        contact_person="John Doe",
        contact_number="+27105550100",
        contact_email="john@test.co.za",
    )
    
    changes = collect_changed_columns(original, proposed)
    
    assert "Status" in changes
    assert changes["Status"] == ("Candidate", "Verified")
    assert "Website URL" in changes
    assert changes["Website URL"] == ("", "https://test.co.za")
    assert "Contact Person" in changes
    assert "Contact Number" in changes
    assert "Contact Email Address" in changes


def test_collect_changed_columns_no_changes():
    """Test that no changes returns empty dict."""
    record = SchoolRecord(
        name="Test School",
        province="Gauteng",
        status="Candidate",
        website_url="",
        contact_person="",
        contact_number="",
        contact_email="",
    )
    
    changes = collect_changed_columns(record, record)
    
    assert changes == {}


def test_describe_changes_formats_correctly():
    """Test that changes are formatted as semicolon-separated strings."""
    original_row = pd.Series({
        "Name of Organisation": "Test School",
        "Province": "Gauteng",
        "Status": "Candidate",
        "Website URL": "",
        "Contact Person": "",
        "Contact Number": "",
        "Contact Email Address": "",
    })
    record = SchoolRecord(
        name="Test School",
        province="Gauteng",
        status="Verified",
        website_url="https://test.co.za",
        contact_person="John Doe",
        contact_number="+27105550100",
        contact_email="john@test.co.za",
    )
    
    description = describe_changes(original_row, record)
    
    assert "Website URL -> https://test.co.za" in description
    assert "Contact Person -> John Doe" in description
    assert "Contact Number -> +27105550100" in description
    assert "Contact Email Address -> john@test.co.za" in description
    assert "Status -> Verified" in description
    assert description.count(";") == 4  # 5 changes


def test_describe_changes_no_changes():
    """Test that no changes returns 'No changes'."""
    original_row = pd.Series({
        "Name of Organisation": "Test School",
        "Province": "Gauteng",
        "Status": "Candidate",
        "Website URL": "",
        "Contact Person": "",
        "Contact Number": "",
        "Contact Email Address": "",
    })
    record = SchoolRecord(
        name="Test School",
        province="Gauteng",
        status="Candidate",
        website_url="",
        contact_person="",
        contact_number="",
        contact_email="",
    )
    
    description = describe_changes(original_row, record)
    
    assert description == "No changes"


def test_build_rollback_action_deterministic_ordering():
    """Test that rollback actions have deterministically sorted columns."""
    attempted_changes = {
        "Website URL": ("", "https://test.co.za"),
        "Contact Email Address": ("", "test@example.com"),
        "Contact Person": ("", "John Doe"),
    }
    issues = [
        QualityIssue(
            row_id=1,
            organisation="Test School",
            code="low_confidence",
            severity="block",
            message="Confidence too low",
            remediation="Add more sources",
        ),
        QualityIssue(
            row_id=1,
            organisation="Test School",
            code="no_official_source",
            severity="warn",
            message="No official source",
            remediation="Find official source",
        ),
    ]
    
    action = build_rollback_action(
        row_id=1,
        organisation="Test School",
        attempted_changes=attempted_changes,
        issues=issues,
    )
    
    # Columns should be sorted
    assert action.columns == [
        "Contact Email Address",
        "Contact Person",
        "Website URL",
    ]
    
    # Previous values should match
    assert action.previous_values["Website URL"] == ""
    assert action.previous_values["Contact Email Address"] == ""
    assert action.previous_values["Contact Person"] == ""
    
    # Reason should include all messages
    assert "Confidence too low" in action.reason
    assert "No official source" in action.reason
    
    # Remediation should be sorted and included
    assert "Add more sources" in action.reason
    assert "Find official source" in action.reason


def test_build_rollback_action_no_remediation():
    """Test rollback action without remediation."""
    attempted_changes = {
        "Status": ("Candidate", "Verified"),
    }
    issues = [
        QualityIssue(
            row_id=1,
            organisation="Test School",
            code="test_issue",
            severity="block",
            message="Test message",
            remediation=None,
        ),
    ]
    
    action = build_rollback_action(
        row_id=1,
        organisation="Test School",
        attempted_changes=attempted_changes,
        issues=issues,
    )
    
    assert action.reason == "Test message"
    assert "Remediation" not in action.reason


def test_build_rollback_action_fallback_reason():
    """Test fallback reason when no messages provided."""
    attempted_changes = {
        "Status": ("Candidate", "Verified"),
    }
    issues = [
        QualityIssue(
            row_id=1,
            organisation="Test School",
            code="test_issue",
            severity="block",
            message=None,
            remediation=None,
        ),
    ]
    
    action = build_rollback_action(
        row_id=1,
        organisation="Test School",
        attempted_changes=attempted_changes,
        issues=issues,
    )
    
    assert action.reason == "Quality gate rejection"
