from __future__ import annotations

from datetime import datetime, timezone

from crawlkit.adapter.firecrawl_compat import fetch_markdown
from crawlkit.types import FetchedPage


def test_fetch_markdown_single(monkeypatch):
    async def fake_fetch(url, policy):
        return FetchedPage(
            url=url,
            html="<html><main>Info info@acesaero.co.za</main></html>",
            status=200,
            robots_allowed=True,
            fetched_at=datetime.now(timezone.utc),
            via="http",
            metadata={},
        )

    async def fake_fetch_many(urls, policy):
        return [await fake_fetch(urls[0], policy)]

    monkeypatch.setattr("crawlkit.adapter.firecrawl_compat.fetch", fake_fetch)
    monkeypatch.setattr("crawlkit.adapter.firecrawl_compat.fetch_many", fake_fetch_many)

    result = fetch_markdown("https://example.com")
    assert result["url"] == "https://example.com"
    assert "markdown" in result

    bundle = fetch_markdown("https://example.com", depth=2, include_subpaths=True)
    assert bundle["items"]
