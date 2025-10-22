"""Watercrawl enrichment stack exposing layered application surfaces."""

import warnings
from importlib import import_module

try:
    # Some Marshmallow versions expose a specific warning class introduced
    # in later releases. Import it if present and filter it; otherwise fall
    # back to ignoring generic Marshmallow deprecation warnings so tests
    # and tools remain resilient across minor version differences.
    from marshmallow.warnings import ChangedInMarshmallow4Warning  # type: ignore

    warnings.filterwarnings("ignore", category=ChangedInMarshmallow4Warning)
except Exception:
    # Best-effort fallback: ignore known Marshmallow deprecation warnings by
    # message text to avoid import failures on older/newer versions.
    warnings.filterwarnings("ignore", "marshmallow", category=Warning)

_SUBMODULES = (
    "core",
    "governance",
    "infrastructure",
    "integrations",
    "interfaces",
)

for _module_name in _SUBMODULES:
    globals()[_module_name] = import_module(f"{__name__}.{_module_name}")

__all__ = list(_SUBMODULES)
