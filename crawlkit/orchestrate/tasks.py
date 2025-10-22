"""Celery task wiring for Crawlkit pipelines."""
from __future__ import annotations

import asyncio
from typing import Any, Mapping

from ..distill.distill import distill
from ..extract.entities import extract_entities
from ..fetch.polite_fetch import fetch
from ..types import DistilledDoc, Entities, FetchPolicy, FetchedPage, serialize_for_celery

try:  # pragma: no cover - optional dependency
    from celery import shared_task
except Exception:  # pragma: no cover - optional dependency missing
    def shared_task(*_args, **_kwargs):
        def decorator(func):
            return func

        return decorator


def _run(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:  # pragma: no cover - defensive fallback when loop exists
        return asyncio.ensure_future(coro, loop=loop)


@shared_task(name="crawlkit.fetch_page")
def fetch_page_task(url: str, policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    policy_obj = FetchPolicy.from_mapping(policy)
    result = _run(fetch(url, policy_obj))
    if asyncio.isfuture(result):
        result = asyncio.get_event_loop().run_until_complete(result)  # pragma: no cover
    assert isinstance(result, FetchedPage)
    return serialize_for_celery(result)


@shared_task(name="crawlkit.distill_page")
def distill_page_task(page: Mapping[str, Any]) -> dict[str, Any]:
    fetched = FetchedPage.from_mapping(page)
    doc = distill(fetched.html, fetched.url)
    assert isinstance(doc, DistilledDoc)
    return serialize_for_celery(doc)


@shared_task(name="crawlkit.extract_entities")
def extract_entities_task(doc: Mapping[str, Any]) -> dict[str, Any]:
    distilled = DistilledDoc.from_mapping(doc)
    entities = extract_entities(distilled)
    assert isinstance(entities, Entities)
    return serialize_for_celery(entities)


@shared_task(name="crawlkit.full_pipeline")
def full_pipeline_task(url: str, policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    page = fetch_page_task(url, policy)
    doc = distill_page_task(page)
    entities = extract_entities_task(doc)
    return {
        "page": page,
        "doc": doc,
        "entities": entities,
    }


__all__ = [
    "fetch_page_task",
    "distill_page_task",
    "extract_entities_task",
    "full_pipeline_task",
]
