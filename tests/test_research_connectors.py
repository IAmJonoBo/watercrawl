from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from firecrawl_demo.integrations.adapters.research.connectors import (
    ConnectorRequest,
    ConnectorResult,
    PressConnector,
    RegulatorConnector,
)


@pytest.fixture()
def sample_request() -> ConnectorRequest:
    return ConnectorRequest(
        organisation="Sky High Flight Academy",
        province="Gauteng",
        allow_personal_data=False,
        rate_limit_delay=0.0,
    )


def test_regulator_connector_filters_personal_data(
    sample_request: ConnectorRequest,
) -> None:
    payload = {
        "officialWebsite": "https://skyhigh.example.za",
        "contactPerson": "Ms. Test",
        "contactEmail": "leader@skyhigh.example.za",
        "contactPhone": "+27 11 555 0101",
        "address": "Hangar 1, Lanseria",
        "sources": ["https://regulator.gov.za/sky-high"],
    }
    requester = MagicMock(return_value=payload)
    connector = RegulatorConnector(requester=requester)

    result = connector.collect(sample_request)

    assert isinstance(result, ConnectorResult)
    assert result.success is True
    assert result.observation.website_url == "https://skyhigh.example.za"
    # POPIA: personal fields removed when allow_personal_data=False
    assert result.observation.contact_email is None
    assert result.observation.contact_phone is None
    assert result.observation.contact_person is None
    assert result.observation.physical_address == "Hangar 1, Lanseria"
    assert result.sources == ["https://regulator.gov.za/sky-high"]


def test_press_connector_collects_articles(sample_request: ConnectorRequest) -> None:
    payload = {
        "articles": [
            {
                "url": "https://press.example/sky-high-expands",
                "title": "Sky High expands fleet",
                "description": "New aircraft arriving",
            }
        ]
    }
    requester = MagicMock(return_value=payload)
    connector = PressConnector(requester=requester)

    result = connector.collect(sample_request)

    assert result.success is True
    assert result.observation.notes == ["Press coverage: Sky High expands fleet"]
    assert result.sources == ["https://press.example/sky-high-expands"]
