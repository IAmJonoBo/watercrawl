"""Research adapter infrastructure with registry extensibility."""

from firecrawl_demo.integrations.integration_plugins import (
    IntegrationPlugin,
    PluginConfigSchema,
    PluginContext,
    PluginHealthStatus,
    register_plugin,
)

from . import exemplars as _exemplar_adapters  # noqa: F401
from .connectors import (
    ConnectorEvidence,
    ConnectorObservation,
    ConnectorRequest,
    ConnectorResult,
    CorporateFilingsConnector,
    PressConnector,
    RegulatorConnector,
    ResearchConnector,
    SocialConnector,
)
from .core import (
    CompositeResearchAdapter,
    CrawlkitResearchAdapter,
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
from .multi_source import MultiSourceResearchAdapter, build_default_connectors
from .registry import (
    AdapterContext,
    AdapterLoaderSettings,
    load_enabled_adapters,
    register_adapter,
)
from .validators import (
    ValidationCheck,
    ValidationReport,
    ValidationSeverity,
    cross_validate_findings,
)

__all__ = [
    "CompositeResearchAdapter",
    "ConnectorEvidence",
    "ConnectorObservation",
    "ConnectorRequest",
    "ConnectorResult",
    "CorporateFilingsConnector",
    "CrawlkitResearchAdapter",
    "MultiSourceResearchAdapter",
    "NullResearchAdapter",
    "PressConnector",
    "RegulatorConnector",
    "ResearchAdapter",
    "ResearchConnector",
    "ResearchFinding",
    "SocialConnector",
    "StaticResearchAdapter",
    "SupportsAsyncLookup",
    "TriangulatingResearchAdapter",
    "ValidationCheck",
    "ValidationReport",
    "ValidationSeverity",
    "build_default_connectors",
    "build_research_adapter",
    "cross_validate_findings",
    "lookup_with_adapter_async",
    "merge_findings",
    "triangulate_via_sources",
    "AdapterLoaderSettings",
    "AdapterContext",
    "load_enabled_adapters",
    "register_adapter",
]


def _research_health_probe(context: PluginContext) -> PluginHealthStatus:
    adapters = load_enabled_adapters()
    enable_crawlkit = bool(
        getattr(context.config.FEATURE_FLAGS, "enable_crawlkit", False)
    )
    allow_network_research = bool(
        getattr(context.config, "ALLOW_NETWORK_RESEARCH", False)
    )
    details = {
        "adapter_count": len(adapters),
        "adapters": [type(adapter).__name__ for adapter in adapters],
        "feature_flags": {
            "enable_crawlkit": enable_crawlkit,
            "allow_network_research": allow_network_research,
        },
    }

    healthy = bool(adapters)
    reason = "Adapters loaded" if healthy else "No research adapters enabled"

    return PluginHealthStatus(healthy=healthy, reason=reason, details=details)


register_plugin(
    IntegrationPlugin(
        name="research",
        category="adapters",
        factory=lambda ctx: build_research_adapter(),
        config_schema=PluginConfigSchema(
            feature_flags=("FEATURE_ENABLE_CRAWLKIT", "ALLOW_NETWORK_RESEARCH"),
            environment_variables=("RESEARCH_ADAPTERS", "RESEARCH_ADAPTERS_FILE"),
            description=(
                "Composite research adapter stack combining registry-managed "
                "intelligence sources with Crawlkit enrichment."
            ),
        ),
        health_probe=_research_health_probe,
        summary="Composite research adapter orchestrating enrichment sources.",
    )
)
