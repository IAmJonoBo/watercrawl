"""Backwards compatible shim for the analyst CLI and Crawlkit surfaces."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from watercrawl.core import config

try:  # pragma: no cover - optional Crawlkit dependency
    from crawlkit.adapter.firecrawl_compat import (
        fetch_markdown as _CRAWLKIT_FETCH_MARKDOWN,
    )
    from crawlkit.orchestrate.api import build_router as _CRAWLKIT_BUILD_ROUTER
    from crawlkit.orchestrate.api import create_app as _CRAWLKIT_CREATE_APP
except ImportError:  # pragma: no cover - optional dependency missing
    _CRAWLKIT_FETCH_MARKDOWN = None  # type: ignore
    _CRAWLKIT_BUILD_ROUTER = None  # type: ignore
    _CRAWLKIT_CREATE_APP = None  # type: ignore

try:  # pragma: no cover - optional FastAPI dependency
    from fastapi import APIRouter, FastAPI
except Exception:  # pragma: no cover - optional dependency missing
    APIRouter = None  # type: ignore
    FastAPI = None  # type: ignore

try:  # pragma: no cover - optional dependency for pydantic request model
    from pydantic import BaseModel
except Exception:  # pragma: no cover - fallback when pydantic unavailable
    BaseModel = None  # type: ignore

from watercrawl.integrations.adapters.firecrawl_client import (
    FirecrawlClient,
    summarize_extract_payload,
)

try:
    import pandas as pd  # noqa: F401

    from watercrawl.interfaces import analyst_cli as _analyst_cli

    cli = _analyst_cli.cli
    RichPipelineProgress = _analyst_cli.RichPipelineProgress
    LineageManager = _analyst_cli.LineageManager
    build_lakehouse_writer = _analyst_cli.build_lakehouse_writer

    def _resolve_progress_flag(output_format: str, requested: bool | None) -> bool:
        """Compatibility wrapper for the analyst progress toggle helper."""
        return _analyst_cli._resolve_progress_flag(output_format, requested)

    Progress = _analyst_cli.Progress
    asyncio = _analyst_cli.asyncio
    CopilotMCPServer = _analyst_cli.CopilotMCPServer
    Pipeline = _analyst_cli.Pipeline
    build_evidence_sink = _analyst_cli.build_evidence_sink
    read_dataset = _analyst_cli.read_dataset
    override_cli_dependencies = _analyst_cli.override_cli_dependencies
    plan_guard = _analyst_cli.CLI_ENVIRONMENT.plan_guard

except ImportError:
    # Provide dummy objects when pandas is not available
    cli = None  # type: ignore
    RichPipelineProgress = None  # type: ignore
    LineageManager = None  # type: ignore
    build_lakehouse_writer = None  # type: ignore

    def _resolve_progress_flag(output_format: str, requested: bool | None) -> bool:
        """Compatibility wrapper for the analyst progress toggle helper."""
        raise NotImplementedError("CLI functionality requires pandas (Python < 3.14)")

    Progress = None  # type: ignore
    asyncio = None  # type: ignore
    CopilotMCPServer = None  # type: ignore
    Pipeline = None  # type: ignore
    build_evidence_sink = None  # type: ignore
    read_dataset = None  # type: ignore
    override_cli_dependencies = None  # type: ignore
    plan_guard = None  # type: ignore

__all__ = [
    "cli",
    "RichPipelineProgress",
    "LineageManager",
    "build_lakehouse_writer",
    "_resolve_progress_flag",
    "Progress",
    "asyncio",
    "CopilotMCPServer",
    "Pipeline",
    "build_evidence_sink",
    "read_dataset",
    "override_cli_dependencies",
    "plan_guard",
    "fetch_markdown",
    "build_router",
    "create_app",
]


if BaseModel is not None:  # pragma: no branch - definition depends on pydantic

    class _LegacyCrawlRequest(BaseModel):  # type: ignore[misc,valid-type]
        url: str
        policy: Mapping[str, Any] | None = None

else:  # pragma: no cover - pydantic missing, router construction will fail earlier

    class _LegacyCrawlRequest:  # type: ignore[no-redef]
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("pydantic is required for the legacy router")


def _flags() -> config.FeatureFlags:
    return getattr(config, "FEATURE_FLAGS", config.FeatureFlags())


def _crawlkit_enabled() -> bool:
    return bool(_flags().enable_crawlkit)


def _firecrawl_enabled() -> bool:
    return bool(_flags().enable_firecrawl_sdk)


def _legacy_fetch_markdown(
    url: str,
    depth: int = 1,
    include_subpaths: bool = False,
    policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if depth > 1 or include_subpaths:
        raise RuntimeError(
            "Legacy Firecrawl SDK fetch does not support depth/subpath traversal."
        )

    client = FirecrawlClient()
    payload = client.scrape(url)
    markdown, text, metadata = _extract_firecrawl_fields(payload)
    entities = summarize_extract_payload(payload)

    return {
        "url": url,
        "markdown": markdown,
        "text": text,
        "metadata": metadata,
        "entities": entities,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "provenance": {
            "adapter": "firecrawl_sdk",
            "policy": dict(policy or {}),
        },
    }


def _extract_firecrawl_fields(payload: object) -> tuple[str, str, dict[str, Any]]:
    data: object = payload
    if isinstance(data, Mapping):
        data = data.get("data", data)
        if isinstance(data, Mapping) and "attributes" in data:
            data = data.get("attributes")

    markdown = ""
    text = ""
    metadata: dict[str, Any] = {}

    if isinstance(data, Mapping):
        markdown = _first_string(
            data,
            "markdown",
            "markdown_text",
            "markdownText",
        )
        text = _first_string(data, "text") or markdown
        raw_meta = data.get("metadata")
        if isinstance(raw_meta, Mapping):
            metadata = {str(key): raw_meta[key] for key in raw_meta}

    return markdown, text, metadata


def _first_string(data: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _legacy_build_router() -> "APIRouter":
    if APIRouter is None or BaseModel is None:  # pragma: no cover - FastAPI missing
        raise RuntimeError("FastAPI and pydantic are required for the legacy router")

    router = APIRouter()

    @_legacy_route(router, "/crawl")
    async def crawl(payload: _LegacyCrawlRequest) -> dict[str, Any]:
        bundle = _legacy_fetch_markdown(payload.url, policy=payload.policy)
        return _normalize_bundle(bundle)

    @_legacy_route(router, "/markdown")
    async def markdown(payload: _LegacyCrawlRequest) -> dict[str, Any]:
        bundle = _legacy_fetch_markdown(payload.url, policy=payload.policy)
        return {
            "markdown": bundle.get("markdown", ""),
            "meta": bundle.get("metadata", {}),
        }

    @_legacy_route(router, "/entities")
    async def entities(payload: _LegacyCrawlRequest) -> dict[str, Any]:
        bundle = _legacy_fetch_markdown(payload.url, policy=payload.policy)
        return bundle.get("entities", {})

    return router


def _legacy_create_app() -> "FastAPI":
    if FastAPI is None:  # pragma: no cover - FastAPI missing
        raise RuntimeError("FastAPI is required to create the legacy app")

    app = FastAPI(title="Firecrawl Compatibility Shim")
    app.include_router(_legacy_build_router(), prefix="/crawlkit")
    return app


def _legacy_route(router: "APIRouter", path: str):
    def decorator(func):
        router.post(path)(func)
        return func

    return decorator


def _normalize_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    provenance = bundle.get("provenance")
    if not isinstance(provenance, Mapping):
        provenance = {}
    return {
        "page": {
            "url": bundle.get("url"),
            "status": 200,
            "robots_allowed": True,
            "fetched_at": bundle.get("fetched_at"),
            "via": provenance.get("adapter", "firecrawl_sdk"),
            "metadata": bundle.get("metadata", {}),
        },
        "doc": {
            "url": bundle.get("url"),
            "markdown": bundle.get("markdown", ""),
            "meta": bundle.get("metadata", {}),
            "text": bundle.get("text", bundle.get("markdown", "")),
        },
        "entities": bundle.get("entities", {}),
    }


def fetch_markdown(
    url: str,
    depth: int = 1,
    include_subpaths: bool = False,
    policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if _crawlkit_enabled():
        if _CRAWLKIT_FETCH_MARKDOWN is None:
            raise RuntimeError("Crawlkit fetch adapter is not installed")
        return _CRAWLKIT_FETCH_MARKDOWN(
            url,
            depth=depth,
            include_subpaths=include_subpaths,
            policy=policy,
        )

    if _firecrawl_enabled():
        return _legacy_fetch_markdown(
            url,
            depth=depth,
            include_subpaths=include_subpaths,
            policy=policy,
        )

    raise RuntimeError(
        "Crawlkit adapters are disabled. Set FEATURE_ENABLE_CRAWLKIT=1 or "
        "FEATURE_ENABLE_FIRECRAWL_SDK=1 before invoking fetch_markdown."
    )


def build_router() -> "APIRouter":
    if _crawlkit_enabled():
        if _CRAWLKIT_BUILD_ROUTER is None:
            raise RuntimeError("Crawlkit FastAPI router is not available")
        return _CRAWLKIT_BUILD_ROUTER()

    if _firecrawl_enabled():
        return _legacy_build_router()

    raise RuntimeError(
        "Crawlkit adapters are disabled. Set FEATURE_ENABLE_CRAWLKIT=1 or "
        "FEATURE_ENABLE_FIRECRAWL_SDK=1 before building the router."
    )


def create_app() -> "FastAPI":
    if _crawlkit_enabled():
        if _CRAWLKIT_CREATE_APP is None:
            raise RuntimeError("Crawlkit FastAPI app factory is not available")
        return _CRAWLKIT_CREATE_APP()

    if _firecrawl_enabled():
        return _legacy_create_app()

    raise RuntimeError(
        "Crawlkit adapters are disabled. Set FEATURE_ENABLE_CRAWLKIT=1 or "
        "FEATURE_ENABLE_FIRECRAWL_SDK=1 before creating the app."
    )


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    if cli is not None:
        cli()
    else:
        print("CLI not available: requires pandas (Python < 3.14)")
