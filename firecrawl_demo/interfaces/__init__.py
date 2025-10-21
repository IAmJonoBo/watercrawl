"""Interfaces for human and automation entrypoints."""

try:
    import pandas as pd  # noqa: F401
    import streamlit  # noqa: F401

    PANDAS_AND_STREAMLIT_AVAILABLE = True
    from . import analyst_ui, cli, mcp, telemetry

    __all__ = [
        "analyst_ui",
        "cli",
        "mcp",
        "telemetry",
    ]
except ImportError:
    PANDAS_AND_STREAMLIT_AVAILABLE = False
    from . import cli, mcp, telemetry

    __all__ = [
        "cli",
        "mcp",
        "telemetry",
    ]
