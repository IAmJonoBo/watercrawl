from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from unittest.mock import MagicMock

from watercrawl.integrations.adapters.research.connectors import (
    ConnectorObservation,
    ConnectorRequest,
    ConnectorResult,
)
from watercrawl.integrations.adapters.research.core import ResearchFinding
from watercrawl.integrations.adapters.research.multi_source import (
    MultiSourceResearchAdapter,
)
from watercrawl.integrations.adapters.research.validators import ValidationReport


@dataclass
class _FakeConnector:
    name: str
    responses: Iterable[ConnectorResult]

    def collect(self, request: ConnectorRequest) -> ConnectorResult:
        return next(iter(self.responses))


def test_multi_source_adapter_merges_observations() -> None:
    request = ConnectorRequest(
        organisation="Sky High Flight Academy",
        province="Gauteng",
        allow_personal_data=True,
        rate_limit_delay=0.0,
    )

    regulator_result = ConnectorResult(
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
        raw_payload={},
        privacy_filtered_fields=(),
    )
    press_result = ConnectorResult(
        connector="press",
        observation=ConnectorObservation(
            notes=["Press coverage: Fleet expansion"],
        ),
        sources=["https://press.example/article"],
        notes=["Press coverage located"],
        success=True,
        latency_seconds=0.3,
        raw_payload={},
        privacy_filtered_fields=(),
    )

    validator = MagicMock(
        return_value=ValidationReport(
            base_confidence=55,
            confidence_adjustment=10,
            final_confidence=65,
            checks=(),
            contradictions=(),
        )
    )

    regulator_connector = MagicMock()
    regulator_connector.name = "regulator"
    regulator_connector.collect.return_value = regulator_result
    press_connector = MagicMock()
    press_connector.name = "press"
    press_connector.collect.return_value = press_result

    adapter = MultiSourceResearchAdapter(
        connectors=(regulator_connector, press_connector),
        validator=validator,
    )

    finding = adapter.lookup(request.organisation, request.province)

    assert isinstance(finding, ResearchFinding)
    assert finding.website_url == "https://skyhigh.example.za"
    assert finding.contact_person == "Director Nomsa"
    assert finding.confidence == 65
    assert "regulator" in finding.evidence_by_connector
    assert finding.evidence_by_connector["regulator"].success is True
    assert finding.validation is not None
    validator.assert_called_once()
