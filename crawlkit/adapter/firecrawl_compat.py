"""Compatibility adapter exposing the legacy Firecrawl fetch_markdown signature."""
from __future__ import annotations

import asyncio
from typing import Any, Mapping

from ..distill.distill import distill
from ..extract.entities import extract_entities
from ..fetch.polite_fetch import fetch, fetch_many
from ..types import FetchPolicy, serialize_for_celery


def _run(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:  # pragma: no cover - defensive fallback when called inside an event loop
        return loop.run_until_complete(coro)


def fetch_markdown(url: str, depth: int = 1, include_subpaths: bool = False, policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Fetch markdown content for the provided URL, mirroring Firecrawl's adapter."""

    fetch_policy = FetchPolicy.from_mapping(policy)
    if depth <= 1 and not include_subpaths:
        page = _run(fetch(url, fetch_policy))
        doc = distill(page.html, page.url)
        entities = extract_entities(doc)
        return {
            "url": page.url,
            "markdown": doc.markdown,
            "text": doc.text,
            "metadata": doc.meta,
            "entities": serialize_for_celery(entities),
            "fetched_at": page.fetched_at.isoformat(),
            "provenance": {
                "robots_allowed": page.robots_allowed,
                "via": page.via,
                "policy": fetch_policy.to_dict(),
            },
        }

    pages = _run(fetch_many([url], fetch_policy))
    bundles = []
    for page in pages:
        doc = distill(page.html, page.url)
        entities = extract_entities(doc)
        bundles.append(
            {
                "url": page.url,
                "markdown": doc.markdown,
                "text": doc.text,
                "metadata": doc.meta,
                "entities": serialize_for_celery(entities),
                "fetched_at": page.fetched_at.isoformat(),
                "provenance": {
                    "robots_allowed": page.robots_allowed,
                    "via": page.via,
                    "policy": fetch_policy.to_dict(),
                },
            }
        )
    return {"items": bundles}


__all__ = ["fetch_markdown"]
