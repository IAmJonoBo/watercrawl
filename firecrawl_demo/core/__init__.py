"""Core utilities shared across application and domain layers."""

try:
    import pandas as pd  # noqa: F401

    _PANDAS_AVAILABLE = True
except ImportError:
    _PANDAS_AVAILABLE = False

if _PANDAS_AVAILABLE:
    from . import cache, config, excel, external_sources, presets

    __all__ = ["cache", "config", "excel", "external_sources", "presets"]
else:
    from . import cache, config, external_sources, presets

    __all__ = ["cache", "config", "external_sources", "presets"]
