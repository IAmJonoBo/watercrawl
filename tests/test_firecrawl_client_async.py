import asyncio

import pytest

from firecrawl_demo.firecrawl_client import FirecrawlClient


class DummySettings:
    class throttle:
        min_interval = 0.01

    class retry:
        initial_delay = 0.01
        max_delay = 0.1
        backoff_factor = 2.0
        max_attempts = 3

    behaviour = type(
        "behaviour", (), {"search_limit": 1, "scrape_formats": [], "map_limit": 1}
    )
    api_url = None


@pytest.mark.asyncio
async def test_search_async_basic():
    client = FirecrawlClient(api_key="dummy", settings=DummySettings())

    # Patch _client.search to a coroutine
    async def fake_search(query, limit=None):
        await asyncio.sleep(0.01)
        return {"results": [query, limit]}

    client._client.search = fake_search
    result = await client.search_async("test", limit=2)
    assert result["results"] == ["test", 2]


@pytest.mark.asyncio
async def test_scrape_async_basic():
    client = FirecrawlClient(api_key="dummy", settings=DummySettings())

    async def fake_scrape(url, formats=None):
        await asyncio.sleep(0.01)
        return {"url": url, "formats": formats}

    client._client.scrape = fake_scrape
    result = await client.scrape_async("http://x.com", formats=["html"])
    assert result["url"] == "http://x.com"
    assert result["formats"] == ["html"]


@pytest.mark.asyncio
async def test_crawl_async_basic():
    client = FirecrawlClient(api_key="dummy", settings=DummySettings())

    async def fake_crawl(url, **kwargs):
        await asyncio.sleep(0.01)
        return {"url": url, "kwargs": kwargs}

    client._client.crawl = fake_crawl
    result = await client.crawl_async("http://x.com", foo="bar")
    assert result["url"] == "http://x.com"
    assert result["kwargs"]["foo"] == "bar"


@pytest.mark.asyncio
async def test_extract_async_basic():
    client = FirecrawlClient(api_key="dummy", settings=DummySettings())

    async def fake_extract(urls, prompt):
        await asyncio.sleep(0.01)
        return {"urls": urls, "prompt": prompt}

    client._client.extract = fake_extract
    result = await client.extract_async(["http://x.com"], prompt="go")
    assert result["urls"] == ["http://x.com"]
    assert result["prompt"] == "go"
