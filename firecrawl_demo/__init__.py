"""Watercrawl enrichment stack exposing layered application surfaces."""

import warnings
from importlib import import_module

from marshmallow.warnings import ChangedInMarshmallow4Warning

warnings.filterwarnings("ignore", category=ChangedInMarshmallow4Warning)

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
