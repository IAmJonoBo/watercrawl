import pytest

from firecrawl_demo.integrations.firecrawl_client import (
    FirecrawlClient,
    summarize_extract_payload,
)


def test_firecrawl_client_without_sdk_raises(monkeypatch):
    import firecrawl_demo.integrations.firecrawl_client as fc_mod

    monkeypatch.setattr(fc_mod, "Firecrawl", None)
    client = FirecrawlClient(api_key="dummy")
    with pytest.raises(RuntimeError):
        client.scrape("https://example.com")


def test_summarize_extract_payload_normalises_fields():
    payload = {
        "data": {
            "attributes": {
                "contactPerson": "Jane Dlamini",
                "contactEmail": "jane.dlamini@example.com",
                "contactPhone": "+27 11 555 0000",
                "website": "https://example.com",
            }
        }
    }
    summary = summarize_extract_payload(payload)
    assert summary["contact_person"] == "Jane Dlamini"
    assert summary["contact_email"] == "jane.dlamini@example.com"
    assert summary["contact_phone"] == "+27 11 555 0000"
    assert summary["website_url"] == "https://example.com"
