"""Research adapter infrastructure with registry extensibility."""

from .core import (
    CompositeResearchAdapter,
    FirecrawlResearchAdapter,
    NullResearchAdapter,
    ResearchAdapter,
    ResearchFinding,
    StaticResearchAdapter,
    TriangulatingResearchAdapter,
    build_research_adapter,
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
    "TriangulatingResearchAdapter",
    "build_research_adapter",
    "merge_findings",
    "triangulate_via_sources",
    "AdapterLoaderSettings",
    "AdapterContext",
    "load_enabled_adapters",
    "register_adapter",
]
