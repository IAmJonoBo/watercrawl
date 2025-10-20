"""Expose the analyst CLI under the legacy ``app.cli`` namespace."""

from __future__ import annotations

from apps.analyst.cli import cli as _analyst_cli

cli = _analyst_cli

__all__ = ["cli"]


if __name__ == "__main__":  # pragma: no cover - compatibility entry point
    cli()
