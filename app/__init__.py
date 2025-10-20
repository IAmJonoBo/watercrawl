"""Compatibility shims for legacy `app` namespace imports."""

from __future__ import annotations

from apps.analyst.cli import cli as cli

__all__ = ["cli"]
