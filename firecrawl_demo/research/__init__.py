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

# Import exemplar adapters for registration side effects.
from . import exemplars as _exemplar_adapters  # noqa: F401

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
