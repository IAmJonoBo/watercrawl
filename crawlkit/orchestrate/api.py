"""FastAPI endpoints for Crawlkit orchestration."""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, Field

from ..distill.distill import distill
from ..extract.entities import extract_entities
from ..fetch.polite_fetch import fetch
from ..types import FetchPolicy, serialize_for_celery

try:  # pragma: no cover - optional dependency
    from fastapi import APIRouter, FastAPI
except Exception:  # pragma: no cover - optional dependency missing
    APIRouter = None  # type: ignore
    FastAPI = None  # type: ignore


class CrawlRequest(BaseModel):
    url: str
    policy: Mapping[str, Any] | None = Field(default=None)


def build_router() -> "APIRouter":
    if APIRouter is None:  # pragma: no cover - FastAPI missing
        raise RuntimeError("FastAPI is required to build the Crawlkit router")
    router = APIRouter()

    @router.post("/crawl")
    async def crawl(payload: CrawlRequest) -> dict[str, Any]:
        policy = FetchPolicy.from_mapping(payload.policy)
        page = await fetch(payload.url, policy)
        doc = distill(page.html, page.url)
        entities = extract_entities(doc)
        return {
            "page": serialize_for_celery(page),
            "doc": serialize_for_celery(doc),
            "entities": serialize_for_celery(entities),
        }

    @router.post("/markdown")
    async def markdown(payload: CrawlRequest) -> dict[str, Any]:
        policy = FetchPolicy.from_mapping(payload.policy)
        page = await fetch(payload.url, policy)
        doc = distill(page.html, page.url)
        return {
            "markdown": doc.markdown,
            "meta": doc.meta,
        }

    @router.post("/entities")
    async def entities_endpoint(payload: CrawlRequest) -> dict[str, Any]:
        policy = FetchPolicy.from_mapping(payload.policy)
        page = await fetch(payload.url, policy)
        doc = distill(page.html, page.url)
        entities = extract_entities(doc)
        return serialize_for_celery(entities)

    return router


def create_app() -> "FastAPI":
    if FastAPI is None:  # pragma: no cover - FastAPI missing
        raise RuntimeError("FastAPI is required to create the Crawlkit app")
    app = FastAPI(title="Crawlkit")
    app.include_router(build_router(), prefix="/crawlkit")
    return app


__all__ = ["build_router", "create_app"]
