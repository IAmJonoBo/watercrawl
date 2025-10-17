"""Research adapter infrastructure with registry extensibility."""

# Import exemplar adapters for registration side effects.
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
