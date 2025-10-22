from __future__ import annotations

import asyncio

import httpx

from crawlkit.fetch.polite_fetch import FetchPolicy, fetch, fetch_many


def test_fetch_respects_robots(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            body = "User-agent: *\nDisallow: /blocked"
            return httpx.Response(200, text=body)
        return httpx.Response(200, text="<html><main>allowed</main></html>")

    transport = httpx.MockTransport(handler)
    
    async def runner():
        async with httpx.AsyncClient(transport=transport) as client:
            page = await fetch("https://example.com/blocked", client=client)
            assert page.robots_allowed is False
            assert page.html == ""
            assert page.metadata["reason"] == "robots"

    asyncio.run(runner())


def test_fetch_uses_renderer_when_required():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        return httpx.Response(200, text="<html><body></body></html>")

    async def renderer(url: str) -> str:
        return "<html><main>rendered</main></html>"

    transport = httpx.MockTransport(handler)
    
    async def runner():
        async with httpx.AsyncClient(transport=transport) as client:
            page = await fetch("https://example.com/", client=client, renderer=renderer)
        assert page.via == "rendered"
        assert "rendered" in page.html

    asyncio.run(runner())


def test_fetch_many_batches_requests(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        return httpx.Response(200, text="<html><main>ok</main></html>")

    transport = httpx.MockTransport(handler)

    class DummyClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            super().__init__(transport=transport, *args, **kwargs)

    monkeypatch.setattr("crawlkit.fetch.polite_fetch.httpx.AsyncClient", DummyClient)
    pages = asyncio.run(fetch_many(["https://example.com/a", "https://example.com/b"], policy=FetchPolicy()))
    assert len(pages) == 2
    assert all(page.robots_allowed for page in pages)
