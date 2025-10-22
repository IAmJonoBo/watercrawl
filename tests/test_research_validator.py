from __future__ import annotations

from firecrawl_demo.integrations.adapters.research.connectors import (
    ConnectorObservation,
    ConnectorResult,
)
from firecrawl_demo.integrations.adapters.research.core import ResearchFinding
from firecrawl_demo.integrations.adapters.research.validators import (
    ValidationReport,
    ValidationSeverity,
    cross_validate_findings,
)


def test_cross_validation_identifies_contradictions() -> None:
    regulator = ConnectorResult(
        connector="regulator",
        observation=ConnectorObservation(
            website_url="https://skyhigh.example.za",
            contact_person="Director Nomsa",
            contact_email="nomsa@skyhigh.example.za",
            contact_phone="+27 11 555 0101",
        ),
        sources=["https://regulator.gov.za/sky-high"],
        notes=["Regulator registry corroboration"],
        success=True,
        latency_seconds=0.2,
        raw_payload={"mx": True},
        privacy_filtered_fields=(),
    )
    press = ConnectorResult(
        connector="press",
        observation=ConnectorObservation(
            website_url="https://skyhigh.co.za",
            notes=["Press coverage: Fleet expansion"],
        ),
        sources=["https://press.example/article"],
        notes=["Press coverage located"],
        success=True,
        latency_seconds=0.3,
        raw_payload={},
        privacy_filtered_fields=(),
    )

    base_finding = ResearchFinding(
        website_url="https://skyhigh.example.za",
        contact_email="info@skyhigh.example.za",
        contact_phone="+27 11 555 0101",
        confidence=60,
    )

    report = cross_validate_findings(base_finding, [regulator, press])

    assert isinstance(report, ValidationReport)
    assert report.final_confidence >= report.base_confidence
    contradiction = next(
        (c for c in report.contradictions if "domain" in c.lower()),
        None,
    )
    assert contradiction is not None
    severities = {check.name: check.severity for check in report.checks}
    assert severities["phone_e164"] is ValidationSeverity.PASS
    assert severities["leadership_title"] is ValidationSeverity.PASS
