from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from watercrawl.core import config


def _set_flags(
    monkeypatch, *, enable_crawlkit: bool, enable_firecrawl_sdk: bool
) -> None:
    monkeypatch.setattr(
        config,
        "FEATURE_FLAGS",
        config.FeatureFlags(
            enable_crawlkit=enable_crawlkit,
            enable_firecrawl_sdk=enable_firecrawl_sdk,
            enable_press_research=True,
            enable_regulator_lookup=True,
            enable_ml_inference=True,
            investigate_rebrands=True,
        ),
        raising=False,
    )


@pytest.fixture(autouse=True)
def _reload_cli_module():
    module = importlib.import_module("watercrawl.interfaces.cli")
    importlib.reload(module)
    yield


def test_fetch_markdown_uses_crawlkit_when_flag_enabled(monkeypatch):
    import watercrawl.interfaces.cli as shim

    _set_flags(monkeypatch, enable_crawlkit=True, enable_firecrawl_sdk=False)

    captured: dict[str, tuple[object, ...]] = {}

    def fake_fetch(
        url: str, depth: int = 1, include_subpaths: bool = False, policy=None
    ):
        captured["args"] = (url, depth, include_subpaths, policy)
        return {"markdown": "ok", "metadata": {}, "entities": {}}

    monkeypatch.setattr(shim, "_CRAWLKIT_FETCH_MARKDOWN", fake_fetch)

    result = shim.fetch_markdown("https://example.com")

    assert result["markdown"] == "ok"
    assert captured["args"][0] == "https://example.com"


def test_fetch_markdown_requires_feature_flag(monkeypatch):
    import watercrawl.interfaces.cli as shim

    _set_flags(monkeypatch, enable_crawlkit=False, enable_firecrawl_sdk=False)

    with pytest.raises(RuntimeError, match="FEATURE_ENABLE_CRAWLKIT"):
        shim.fetch_markdown("https://example.com")


def test_fetch_markdown_uses_legacy_when_sdk_enabled(monkeypatch):
    import watercrawl.interfaces.cli as shim

    _set_flags(monkeypatch, enable_crawlkit=False, enable_firecrawl_sdk=True)

    called = False

    def fake_legacy(
        url: str, depth: int = 1, include_subpaths: bool = False, policy=None
    ):
        nonlocal called
        called = True
        return {"markdown": "legacy", "metadata": {}, "entities": {}}

    monkeypatch.setattr(shim, "_legacy_fetch_markdown", fake_legacy)

    result = shim.fetch_markdown("https://example.com")

    assert called
    assert result["markdown"] == "legacy"


def test_build_router_prefers_crawlkit(monkeypatch):
    import watercrawl.interfaces.cli as shim

    _set_flags(monkeypatch, enable_crawlkit=True, enable_firecrawl_sdk=False)

    sentinel = object()
    monkeypatch.setattr(shim, "_CRAWLKIT_BUILD_ROUTER", lambda: sentinel)

    assert shim.build_router() is sentinel


def test_build_router_uses_legacy_when_only_sdk_enabled(monkeypatch):
    import watercrawl.interfaces.cli as shim

    _set_flags(monkeypatch, enable_crawlkit=False, enable_firecrawl_sdk=True)

    sentinel = object()
    monkeypatch.setattr(shim, "_legacy_build_router", lambda: sentinel)

    assert shim.build_router() is sentinel


def test_crawlkit_status_reports_router(monkeypatch):
    import apps.analyst.cli as analyst_cli

    flags = config.FeatureFlags(enable_crawlkit=True, enable_firecrawl_sdk=False)
    monkeypatch.setattr(analyst_cli, "_feature_flags", lambda: flags)

    router = SimpleNamespace(
        routes=[
            SimpleNamespace(path="/crawlkit/crawl"),
            SimpleNamespace(path="/crawlkit/entities"),
        ]
    )
    monkeypatch.setattr(analyst_cli, "_build_crawlkit_router", lambda: router)

    result = CliRunner().invoke(analyst_cli.crawlkit_status)

    assert result.exit_code == 0
    assert "Crawlkit router ready" in result.output
    assert "/crawlkit/crawl" in result.output
    assert "Targeted QA:" in result.output


def test_crawlkit_status_warns_on_legacy_flag_without_crawlkit(monkeypatch):
    import apps.analyst.cli as analyst_cli

    flags = config.FeatureFlags(enable_crawlkit=False, enable_firecrawl_sdk=True)
    monkeypatch.setattr(analyst_cli, "_feature_flags", lambda: flags)

    result = CliRunner().invoke(analyst_cli.crawlkit_status)

    assert result.exit_code == 0
    assert "Set FEATURE_ENABLE_CRAWLKIT=1" in result.output
    assert "Enable FEATURE_ENABLE_CRAWLKIT" in result.output
