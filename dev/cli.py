"""Compatibility shim exposing the developer QA CLI at ``python -m dev.cli``."""

from __future__ import annotations

from apps.automation.cli import cli as _automation_cli

cli = _automation_cli


if __name__ == "__main__":  # pragma: no cover - convenience entry point
    cli()
