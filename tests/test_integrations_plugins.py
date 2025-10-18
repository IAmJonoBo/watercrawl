from __future__ import annotations

import importlib
from typing import Any, Iterator

import pytest

from firecrawl_demo.integrations.integration_plugins import (
    IntegrationPlugin,
    PluginConfigSchema,
    PluginContext,
    PluginHealthStatus,
    PluginLookupError,
    available_plugin_names,
    discover_plugins,
    instantiate_plugin,
    register_plugin,
    reset_registry,
)


@pytest.fixture()
def plugin_registry_snapshot() -> Iterator[list[str]]:
    """Snapshot the plugin registry and restore it after the test."""

    modules_to_reload: list[str] = [
        "firecrawl_demo.integrations.adapters.research",
        "firecrawl_demo.integrations.storage.lakehouse",
        "firecrawl_demo.integrations.storage.versioning",
        "firecrawl_demo.integrations.telemetry.drift",
        "firecrawl_demo.integrations.telemetry.graph_semantics",
        "firecrawl_demo.integrations.telemetry.lineage",
    ]
    yield modules_to_reload
    reset_registry()
    for module_name in modules_to_reload:
        importlib.reload(importlib.import_module(module_name))


def test_builtin_research_plugin_discovered() -> None:
    adapters = discover_plugins("adapters")
    assert "research" in adapters
    plugin = adapters["research"]
    assert plugin.config_schema.feature_flags == (
        "FEATURE_ENABLE_FIRECRAWL_SDK",
        "ALLOW_NETWORK_RESEARCH",
    )


def test_instantiate_missing_plugin_returns_none_when_allowed() -> None:
    assert instantiate_plugin("storage", "unknown", allow_missing=True) is None
    with pytest.raises(PluginLookupError):
        instantiate_plugin("storage", "unknown", allow_missing=False)


def test_custom_plugin_registration_and_health_probe(plugin_registry_snapshot: list[Any]) -> None:
    reset_registry()

    def _factory(context: PluginContext) -> str:
        return "demo"

    def _probe(context: PluginContext) -> PluginHealthStatus:
        return PluginHealthStatus(healthy=True, reason="ok")

    register_plugin(
        IntegrationPlugin(
            name="demo",
            category="telemetry",
            factory=_factory,
            config_schema=PluginConfigSchema(
                description="Demo plugin for testing",
            ),
            health_probe=_probe,
        )
    )

    names = list(available_plugin_names("telemetry"))
    assert "demo" in names

    instance = instantiate_plugin("telemetry", "demo")
    assert instance == "demo"

    plugin = discover_plugins("telemetry")["demo"]
    status = plugin.probe()
    assert status is not None
    assert status.healthy is True
    assert status.reason == "ok"
