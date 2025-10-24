from __future__ import annotations

import importlib
from collections.abc import Iterator
from typing import Any

import pytest

from watercrawl.integrations.integration_plugins import (
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


class _ExplodingError(RuntimeError):
    """Sentinel exception raised by test plugin factories."""


class _ExplodingProbeError(RuntimeError):
    """Sentinel exception raised by health probes in tests."""


@pytest.fixture()
def plugin_registry_snapshot() -> Iterator[list[str]]:
    """Snapshot the plugin registry and restore it after the test."""

    modules_to_reload: list[str] = [
        "watercrawl.integrations.adapters.research",
        "watercrawl.integrations.storage.lakehouse",
        "watercrawl.integrations.storage.versioning",
        "watercrawl.integrations.telemetry.drift",
        "watercrawl.integrations.telemetry.graph_semantics",
        "watercrawl.integrations.telemetry.lineage",
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


def test_builtin_contracts_plugin_discovered() -> None:
    contracts = discover_plugins("contracts")
    assert "contracts" in contracts
    plugin = contracts["contracts"]
    assert "CONTRACTS_ARTIFACT_DIR" in plugin.config_schema.environment_variables
    assert "CONTRACTS_CANONICAL_JSON" in plugin.config_schema.environment_variables
    assert "great_expectations" in plugin.config_schema.optional_dependencies


def test_instantiate_missing_plugin_returns_none_when_allowed() -> None:
    assert instantiate_plugin("storage", "unknown", allow_missing=True) is None
    with pytest.raises(PluginLookupError):
        instantiate_plugin("storage", "unknown", allow_missing=False)


def test_custom_plugin_registration_and_health_probe(
    plugin_registry_snapshot: list[Any],
) -> None:
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


def test_plugin_factory_exception_does_not_poison_registry(
    plugin_registry_snapshot: list[Any],
) -> None:
    reset_registry()

    def _factory(context: PluginContext) -> str:
        raise _ExplodingError("boom")

    register_plugin(
        IntegrationPlugin(
            name="unstable",
            category="telemetry",
            factory=_factory,
            config_schema=PluginConfigSchema(description="Explodes for testing"),
        )
    )

    with pytest.raises(_ExplodingError):
        instantiate_plugin("telemetry", "unstable")

    # Registry should still be intact and allow registering additional plugins.
    register_plugin(
        IntegrationPlugin(
            name="stable",
            category="telemetry",
            factory=lambda ctx: "ok",
            config_schema=PluginConfigSchema(description="Stable plugin"),
        )
    )

    assert "stable" in available_plugin_names("telemetry")


def test_plugin_health_probe_failure_isolated(
    plugin_registry_snapshot: list[Any],
) -> None:
    reset_registry()

    def _probe(context: PluginContext) -> PluginHealthStatus:
        raise _ExplodingProbeError("probe failed")

    register_plugin(
        IntegrationPlugin(
            name="fragile",
            category="telemetry",
            factory=lambda ctx: "noop",
            config_schema=PluginConfigSchema(description="Fragile probe"),
            health_probe=_probe,
        )
    )

    plugin = discover_plugins("telemetry")["fragile"]
    status = plugin.probe()
    assert status is not None
    assert status.healthy is False
    assert status.reason == "probe failed"
