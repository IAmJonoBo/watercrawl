"""Quality gate regression and coverage tests."""

from __future__ import annotations

from firecrawl_demo.application.quality import QualityGate
from firecrawl_demo.domain.models import SchoolRecord
from firecrawl_demo.integrations.research.core import ResearchFinding

_BASE_RECORD = SchoolRecord(
    name="Aero Academy",
    province="Gauteng",
    status="Verified",
    website_url="https://academy.example.za",
    contact_person="John Doe",
    contact_number="+27115550000",
    contact_email="john.doe@academy.example.za",
)


def _record(**overrides: str | None) -> SchoolRecord:
    return SchoolRecord(
        name=(overrides.get("Name of Organisation") or _BASE_RECORD.name),
        province=(overrides.get("Province") or _BASE_RECORD.province),
        status=(overrides.get("Status") or _BASE_RECORD.status),
        website_url=(
            _BASE_RECORD.website_url
            if "Website URL" not in overrides
            else overrides["Website URL"]
        ),
        contact_person=(
            _BASE_RECORD.contact_person
            if "Contact Person" not in overrides
            else overrides["Contact Person"]
        ),
        contact_number=(
            _BASE_RECORD.contact_number
            if "Contact Number" not in overrides
            else overrides["Contact Number"]
        ),
        contact_email=(
            _BASE_RECORD.contact_email
            if "Contact Email Address" not in overrides
            else overrides["Contact Email Address"]
        ),
    )


def _diff(
    original: SchoolRecord, proposed: SchoolRecord
) -> dict[str, tuple[str | None, str | None]]:
    original_data = original.as_dict()
    proposed_data = proposed.as_dict()
    return {
        column: (original_data[column], proposed_data[column])
        for column in original_data
        if original_data[column] != proposed_data[column]
    }


def test_quality_gate_accepts_when_no_columns_change() -> None:
    gate = QualityGate()
    decision = gate.evaluate(
        original=_BASE_RECORD,
        proposed=_BASE_RECORD,
        finding=ResearchFinding(confidence=90),
        changed_columns={},
        phone_issues=(),
        email_issues=(),
        total_source_count=0,
        fresh_source_count=0,
        official_source_count=0,
        official_fresh_source_count=0,
    )

    assert decision.accepted is True
    assert decision.findings == []


def test_quality_gate_blocks_high_risk_without_corroboration() -> None:
    proposed = _record(
        **{
            "Contact Person": "Jane Doe",
            "Contact Email Address": "jane.doe@academy.example.za",
        }
    )

    gate = QualityGate()
    decision = gate.evaluate(
        original=_BASE_RECORD,
        proposed=proposed,
        finding=ResearchFinding(confidence=85),
        changed_columns=_diff(_BASE_RECORD, proposed),
        phone_issues=(),
        email_issues=(),
        total_source_count=1,
        fresh_source_count=0,
        official_source_count=0,
        official_fresh_source_count=0,
    )

    blocking_codes = {finding.code for finding in decision.blocking_findings}
    assert blocking_codes == {
        "insufficient_evidence",
        "no_fresh_evidence",
        "missing_official_source",
    }
    assert decision.accepted is False
    assert decision.fallback_record is not None
    assert decision.fallback_record.status == "Needs Review"


def test_quality_gate_blocks_on_low_confidence_for_high_risk_changes() -> None:
    proposed = _record(**{"Contact Email Address": "jane.doe@academy.example.za"})

    gate = QualityGate(min_confidence=70)
    decision = gate.evaluate(
        original=_BASE_RECORD,
        proposed=proposed,
        finding=ResearchFinding(confidence=40),
        changed_columns=_diff(_BASE_RECORD, proposed),
        phone_issues=(),
        email_issues=(),
        total_source_count=3,
        fresh_source_count=2,
        official_source_count=1,
        official_fresh_source_count=1,
    )

    assert decision.accepted is False
    assert [finding.code for finding in decision.blocking_findings] == [
        "low_confidence"
    ]
    assert decision.fallback_record is not None
    assert decision.fallback_record.status == "Needs Review"


def test_quality_gate_blocks_invalid_contact_details() -> None:
    proposed = _record(
        **{
            "Contact Number": "+27551122334",
            "Contact Email Address": "invalid-address",
        }
    )

    gate = QualityGate()
    decision = gate.evaluate(
        original=_BASE_RECORD,
        proposed=proposed,
        finding=ResearchFinding(confidence=90),
        changed_columns=_diff(_BASE_RECORD, proposed),
        phone_issues=("not_e164",),
        email_issues=("mx_missing", "invalid_format"),
        total_source_count=3,
        fresh_source_count=2,
        official_source_count=1,
        official_fresh_source_count=1,
    )

    blocking_codes = {finding.code for finding in decision.blocking_findings}
    assert blocking_codes == {"invalid_phone", "invalid_email"}


def test_quality_gate_requires_official_source_for_domain_change() -> None:
    proposed = _record(**{"Website URL": "https://new-domain.example.za"})

    gate = QualityGate()
    decision = gate.evaluate(
        original=_BASE_RECORD,
        proposed=proposed,
        finding=ResearchFinding(confidence=80),
        changed_columns=_diff(_BASE_RECORD, proposed),
        phone_issues=(),
        email_issues=(),
        total_source_count=2,
        fresh_source_count=1,
        official_source_count=0,
        official_fresh_source_count=0,
    )

    blocking_codes = {finding.code for finding in decision.blocking_findings}
    assert "website_domain_unverified" in blocking_codes
    assert decision.accepted is False
