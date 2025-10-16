from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


class Organisation:
    """Stub for Organisation to satisfy tests."""

    pass


"""Dataclasses representing flight school records and enrichment results."""


@dataclass
class SchoolRecord:
    """Represents a single organisation row from the enrichment worksheet."""

    name: str
    province: str
    status: str
    website_url: Optional[str]
    contact_person: Optional[str]
    contact_number: Optional[str]
    contact_email: Optional[str]

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "SchoolRecord":
        """Create a SchoolRecord instance from a worksheet row dictionary."""
        return cls(
            name=str(row.get("Name of Organisation", "")).strip(),
            province=str(row.get("Province", "")).strip(),
            status=str(row.get("Status", "")).strip(),
            website_url=_clean_value(row.get("Website URL")),
            contact_person=_clean_value(row.get("Contact Person")),
            contact_number=_clean_value(row.get("Contact Number")),
            contact_email=_clean_value(row.get("Contact Email Address")),
        )


@dataclass
class EnrichmentResult:
    def as_dict(self) -> Dict[str, Any]:
        # Flatten org_details into top-level columns for sheet export
        base = {
            "Source URL": self.source_url,
            "Status": self.status,
            "Confidence": self.confidence,
            "Updated At": self.updated_at.isoformat(timespec="seconds"),
            "Payload Hash": self.payload_hash,
        }
        # Map org_details to expected columns
        details = {
            "Website URL": self.org_details.get("website_url"),
            "Contact Person": self.org_details.get("contact_person"),
            "Contact Number": self.org_details.get("contact_phone"),
            "Contact Email Address": self.org_details.get("contact_email"),
            "Physical Address": self.org_details.get("physical_address"),
            "Accreditation": self.org_details.get("accreditation"),
            "Fleet Overview": self.org_details.get("fleet_overview"),
            "LinkedIn URL": self.org_details.get("linkedin_url"),
            "Facebook URL": self.org_details.get("facebook_url"),
        }
        base.update(details)
        return base

    """Represents enrichment results for a flight school record, including evidence and compliance details."""

    source_url: Optional[str] = None
    status: str = "Candidate"
    confidence: int = 0
    updated_at: datetime = field(default_factory=datetime.utcnow)
    payload_hash: Optional[str] = None

    # Grouped contact and organisation details
    org_details: Dict[str, Optional[str]] = field(
        default_factory=lambda: {
            "website_url": None,
            "contact_person": None,
            "contact_email": None,
            "contact_phone": None,
            "physical_address": None,
            "accreditation": None,
            "fleet_overview": None,
            "linkedin_url": None,
            "facebook_url": None,
        }
    )


def _clean_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
