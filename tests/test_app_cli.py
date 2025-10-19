"""Tests for the end-user CLI wrapper in apps.analyst.cli."""

from __future__ import annotations

from click.testing import CliRunner

from apps.analyst import cli as analyst_cli


def test_app_cli_exposes_expected_commands() -> None:
    command_names = set(analyst_cli.cli.commands)
    assert {"validate", "enrich", "contracts", "mcp-server", "overview"}.issubset(
        command_names
    )


def test_overview_renders_table() -> None:
    runner = CliRunner()
    result = runner.invoke(analyst_cli.cli, ["overview"])
    assert result.exit_code == 0
    assert "ACES Aerodynamics dataset workflow" in result.output
    assert "Sample dataset" in result.output
