from __future__ import annotations

from datetime import datetime, timezone

import pytest

from crawlkit.orchestrate.tasks import (
    distill_page_task,
    extract_entities_task,
    fetch_page_task,
    full_pipeline_task,
)
from crawlkit.types import FetchedPage


@pytest.fixture(autouse=True)
def patch_fetch(monkeypatch):
    async def fake_fetch(url, policy, **kwargs):
        return FetchedPage(
            url=url,
            html="<html><main>Contact info@acesaero.co.za or +27 21 555 0000.</main></html>",
            status=200,
            robots_allowed=True,
            fetched_at=datetime.now(timezone.utc),
            via="http",
            metadata={},
        )

    monkeypatch.setattr("crawlkit.orchestrate.tasks.fetch", fake_fetch)


def test_fetch_page_task_returns_serialised_page():
    result = fetch_page_task("https://example.com", policy={"render_js": "never"})
    assert result["url"] == "https://example.com"
    assert result["robots_allowed"] is True


def test_distill_and_extract_tasks_chain():
    page = fetch_page_task("https://example.com")
    doc = distill_page_task(page)
    assert "markdown" in doc
    entities = extract_entities_task(doc)
    assert entities["emails"]
    pipeline = full_pipeline_task("https://example.com")
    assert pipeline["entities"]["emails"]
