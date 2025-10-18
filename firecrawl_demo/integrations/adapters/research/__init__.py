"""Research adapter infrastructure with registry extensibility."""

# Import exemplar adapters for registration side effects.
from importlib import util as importlib_util

from firecrawl_demo.integrations.integration_plugins import (
    IntegrationPlugin,
    PluginConfigSchema,
    PluginContext,
    PluginHealthStatus,
    register_plugin,
)

from . import exemplars as _exemplar_adapters  # noqa: F401
from .core import (
    CompositeResearchAdapter,
    FirecrawlResearchAdapter,
    NullResearchAdapter,
    ResearchAdapter,
    ResearchFinding,
    StaticResearchAdapter,
    SupportsAsyncLookup,
    TriangulatingResearchAdapter,
    build_research_adapter,
    lookup_with_adapter_async,
    merge_findings,
    triangulate_via_sources,
)
from .registry import (
    AdapterContext,
    AdapterLoaderSettings,
    load_enabled_adapters,
    register_adapter,
)

__all__ = [
    "CompositeResearchAdapter",
    "FirecrawlResearchAdapter",
    "NullResearchAdapter",
    "ResearchAdapter",
    "ResearchFinding",
    "StaticResearchAdapter",
    "SupportsAsyncLookup",
    "TriangulatingResearchAdapter",
    "build_research_adapter",
    "lookup_with_adapter_async",
    "merge_findings",
    "triangulate_via_sources",
    "AdapterLoaderSettings",
    "AdapterContext",
    "load_enabled_adapters",
    "register_adapter",
]


def _firecrawl_dependency_available() -> bool:
    return importlib_util.find_spec("firecrawl") is not None


def _research_health_probe(context: PluginContext) -> PluginHealthStatus:
    adapters = load_enabled_adapters()
    enable_firecrawl_sdk = bool(
        getattr(context.config.FEATURE_FLAGS, "enable_firecrawl_sdk", False)
    )
    allow_network_research = bool(
        getattr(context.config, "ALLOW_NETWORK_RESEARCH", False)
    )
    details = {
        "adapter_count": len(adapters),
        "adapters": [type(adapter).__name__ for adapter in adapters],
        "feature_flags": {
            "enable_firecrawl_sdk": enable_firecrawl_sdk,
            "allow_network_research": allow_network_research,
        },
    }

    healthy = bool(adapters)
    reason = "Adapters loaded" if healthy else "No research adapters enabled"

    if enable_firecrawl_sdk and not _firecrawl_dependency_available():
        healthy = False
        reason = "Firecrawl SDK enabled but dependency missing"

    return PluginHealthStatus(healthy=healthy, reason=reason, details=details)


register_plugin(
    IntegrationPlugin(
        name="research",
        category="adapters",
        factory=lambda ctx: build_research_adapter(),
        config_schema=PluginConfigSchema(
            feature_flags=("FEATURE_ENABLE_FIRECRAWL_SDK", "ALLOW_NETWORK_RESEARCH"),
            environment_variables=("RESEARCH_ADAPTERS", "RESEARCH_ADAPTERS_FILE"),
            optional_dependencies=("firecrawl",),
            description=(
                "Composite research adapter stack combining registry-managed "
                "intelligence sources with Firecrawl when enabled."
            ),
        ),
        health_probe=_research_health_probe,
        summary="Composite research adapter orchestrating enrichment sources.",
    )
)
