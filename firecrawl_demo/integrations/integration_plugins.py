"""Shared plugin discovery utilities for integration components."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from importlib import metadata
from typing import Any

from firecrawl_demo.governance.secrets import SecretsProvider

logger = logging.getLogger(__name__)

ENTRYPOINT_GROUP_PREFIX = "firecrawl_demo.integrations"


@dataclass(frozen=True)
class PluginConfigSchema:
    """Describe configuration expectations for a plugin."""

    feature_flags: tuple[str, ...] = ()
    environment_variables: tuple[str, ...] = ()
    optional_dependencies: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class PluginHealthStatus:
    """Outcome of a plugin health probe."""

    healthy: bool
    reason: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PluginContext:
    """Context passed to plugin factories and probes."""

    config: Any
    secrets: SecretsProvider | None = None

    @classmethod
    def default(cls) -> PluginContext:
        from firecrawl_demo.core import config as core_config

        return cls(
            config=core_config, secrets=getattr(core_config, "SECRETS_PROVIDER", None)
        )


PluginFactory = Callable[[PluginContext], Any]
PluginHealthProbe = Callable[[PluginContext], PluginHealthStatus]


@dataclass
class IntegrationPlugin:
    """Description of a plugin available to the integration layer."""

    name: str
    category: str
    factory: PluginFactory
    config_schema: PluginConfigSchema = field(default_factory=PluginConfigSchema)
    health_probe: PluginHealthProbe | None = None
    summary: str = ""

    def instantiate(self, context: PluginContext | None = None) -> Any:
        active_context = context or PluginContext.default()
        logger.debug("Instantiating %s plugin '%s'", self.category, self.name)
        return self.factory(active_context)

    def probe(self, context: PluginContext | None = None) -> PluginHealthStatus | None:
        if self.health_probe is None:
            return None
        active_context = context or PluginContext.default()
        try:
            return self.health_probe(active_context)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Health probe for plugin '%s' failed", self.name)
            return PluginHealthStatus(healthy=False, reason=str(exc))


_registry: dict[str, dict[str, IntegrationPlugin]] = defaultdict(dict)
_entrypoint_cache: dict[str, dict[str, IntegrationPlugin]] = {}


class PluginRegistrationError(RuntimeError):
    """Raised when plugin registration fails."""


class PluginLookupError(RuntimeError):
    """Raised when a plugin cannot be located."""


def register_plugin(plugin: IntegrationPlugin) -> None:
    """Register a plugin for discovery."""

    category = plugin.category.strip().lower()
    name = plugin.name.strip().lower()
    if not category or not name:
        raise PluginRegistrationError("Plugin name and category must be non-empty")
    _registry[category][name] = plugin
    logger.debug("Registered plugin '%s' in category '%s'", name, category)


def discover_plugins(category: str) -> Mapping[str, IntegrationPlugin]:
    """Return all plugins available for the requested category."""

    normalized = category.strip().lower()
    plugins: dict[str, IntegrationPlugin] = {}
    plugins.update(_registry.get(normalized, {}))
    plugins.update(_load_entrypoint_plugins(normalized))
    return plugins


def _load_entrypoint_plugins(category: str) -> Mapping[str, IntegrationPlugin]:
    if category in _entrypoint_cache:
        return _entrypoint_cache[category]

    group = f"{ENTRYPOINT_GROUP_PREFIX}.{category}"
    discovered: dict[str, IntegrationPlugin] = {}
    try:
        for entry_point in metadata.entry_points().select(group=group):
            plugin = entry_point.load()
            if isinstance(plugin, IntegrationPlugin):
                discovered[plugin.name.strip().lower()] = plugin
            else:
                logger.warning(
                    "Entry point %s did not return an IntegrationPlugin (got %s)",
                    entry_point.name,
                    type(plugin),
                )
    except Exception as exc:  # pragma: no cover - metadata guard
        logger.debug("Entry point discovery for %s failed: %s", group, exc)
    _entrypoint_cache[category] = discovered
    return discovered


def instantiate_plugin(
    category: str,
    name: str,
    *,
    context: PluginContext | None = None,
    allow_missing: bool = False,
) -> Any:
    """Instantiate a plugin by category and name."""

    plugins = discover_plugins(category)
    key = name.strip().lower()
    plugin = plugins.get(key)
    if plugin is None:
        if allow_missing:
            return None
        raise PluginLookupError(f"Plugin '{name}' not found in category '{category}'")
    try:
        return plugin.instantiate(context=context)
    except Exception:  # pragma: no cover - instantiation guard
        logger.exception("Plugin '%s' instantiation failed", name)
        raise


def available_plugin_names(category: str) -> Iterable[str]:
    """List plugin names for a given category."""

    return discover_plugins(category).keys()


def reset_registry() -> None:
    """Reset in-memory plugin registrations (primarily for tests)."""

    _registry.clear()
    _entrypoint_cache.clear()


__all__ = [
    "ENTRYPOINT_GROUP_PREFIX",
    "IntegrationPlugin",
    "PluginConfigSchema",
    "PluginContext",
    "PluginFactory",
    "PluginHealthProbe",
    "PluginHealthStatus",
    "PluginLookupError",
    "PluginRegistrationError",
    "available_plugin_names",
    "discover_plugins",
    "instantiate_plugin",
    "register_plugin",
    "reset_registry",
]
