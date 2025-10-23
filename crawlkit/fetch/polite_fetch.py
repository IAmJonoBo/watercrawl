"""Polite fetching primitives built on top of httpx and optional Playwright."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Awaitable, Callable, Literal, Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from ..types import FetchedPage, FetchPolicy, RobotsDecision

__all__ = ["FetchPolicy", "FetchedPage", "fetch"]

RenderCallable = Callable[[str], Awaitable[str]]


async def _load_robots(
    url: str, policy: FetchPolicy, client: httpx.AsyncClient
) -> RobotFileParser | None:
    if not policy.obey_robots:
        return None
    parsed = urlparse(url)
    robots_url = urljoin(f"{parsed.scheme}://{parsed.netloc}", "/robots.txt")
    parser = RobotFileParser()
    try:
        response = await client.get(
            robots_url, headers={"User-Agent": policy.user_agent}, timeout=5
        )
        if response.status_code >= 400:
            return None
        parser.parse(response.text.splitlines())
        return parser
    except httpx.HTTPError:
        return None


async def _evaluate_robots(
    url: str, policy: FetchPolicy, parser: RobotFileParser | None
) -> RobotsDecision:
    if parser is None:
        return RobotsDecision(allowed=True, user_agent=policy.user_agent, rule=None)
    allowed = parser.can_fetch(policy.user_agent, url)
    rule = None
    try:
        entry = parser.default_entry
        if entry and entry.rulelines:
            rule = "\n".join(line.path for line in entry.rulelines)
    except AttributeError:
        rule = None
    return RobotsDecision(allowed=allowed, user_agent=policy.user_agent, rule=rule)


def _should_render(html: str, response: httpx.Response, policy: FetchPolicy) -> bool:
    if policy.render_js == "always":
        return True
    if policy.render_js == "never":
        return False
    if response.headers.get("content-type", "").startswith("application/json"):
        return True
    stripped = html.strip()
    if len(stripped) < 1024:
        return True
    lowered = stripped.lower()
    if "data-server-rendered" in lowered or 'id="__next"' in lowered:
        return True
    if "<main" not in lowered and "<article" not in lowered:
        return True
    return False


async def _render_with_playwright(url: str) -> str:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Playwright is not installed") from exc

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            content = await page.content()
            return content
        finally:
            await browser.close()


@asynccontextmanager
async def _build_client(policy: FetchPolicy, client: httpx.AsyncClient | None = None):
    if client is not None:
        yield client
        return
    async with httpx.AsyncClient(headers={"User-Agent": policy.user_agent}) as created:
        yield created


async def fetch(
    url: str,
    policy: FetchPolicy | None = None,
    *,
    client: httpx.AsyncClient | None = None,
    renderer: Optional[RenderCallable] = None,
) -> FetchedPage:
    """Fetch a page politely, returning a :class:`FetchedPage`."""

    policy = policy or FetchPolicy()
    async with _build_client(policy, client) as active_client:
        robots_parser = await _load_robots(url, policy, active_client)
        robots_decision = await _evaluate_robots(url, policy, robots_parser)
        if not robots_decision.allowed:
            return FetchedPage(
                url=url,
                html="",
                status=0,
                robots_allowed=False,
                fetched_at=datetime.now(timezone.utc),
                via="http",
                metadata={"reason": "robots"},
                robots=robots_decision,
            )

        response = await active_client.get(
            url, headers={"User-Agent": policy.user_agent}, timeout=15
        )
        response.raise_for_status()
        html = response.text
        via: Literal["http", "rendered"] = "http"  # type: ignore[name-defined]

        should_render = _should_render(html, response, policy)
        if should_render:
            render_callable = renderer or _render_with_playwright
            try:
                html = await render_callable(url)
                via = "rendered"
            except Exception:  # pragma: no cover - fallback when renderer fails
                via = "http"

        return FetchedPage(
            url=url,
            html=html,
            status=response.status_code,
            robots_allowed=True,
            fetched_at=datetime.now(timezone.utc),
            via=via,
            metadata={
                "headers": dict(response.headers),
                "encoding": response.encoding,
            },
            robots=robots_decision,
        )


async def fetch_many(
    urls: list[str], policy: FetchPolicy | None = None
) -> list[FetchedPage]:
    """Convenience helper for fetching multiple URLs concurrently."""

    policy = policy or FetchPolicy()
    async with httpx.AsyncClient(headers={"User-Agent": policy.user_agent}) as client:
        tasks = [fetch(url, policy, client=client) for url in urls[: policy.max_pages]]
        return await asyncio.gather(*tasks)


__all__.extend(["fetch_many"])
