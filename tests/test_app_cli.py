"""Tests for the end-user CLI compatibility wrapper."""

from __future__ import annotations

from importlib import import_module

from click.testing import CliRunner

from app.cli import cli as app_cli
from apps.analyst import cli as analyst_cli


def test_app_cli_exposes_expected_commands() -> None:
    command_names = set(app_cli.commands)
    assert {"validate", "enrich", "contracts", "mcp-server", "overview"}.issubset(
        command_names
    )


def test_overview_renders_table() -> None:
    runner = CliRunner()
    result = runner.invoke(app_cli, ["overview"])
    assert result.exit_code == 0
    assert "ACES Aerodynamics dataset workflow" in result.output
    assert "Sample dataset" in result.output


def test_app_cli_is_alias_for_apps_analyst_cli() -> None:
    assert app_cli is analyst_cli.cli


def test_app_module_reexports_cli_group() -> None:
    module = import_module("app")
    nested_module = import_module("app.cli")
    assert hasattr(module, "cli")
    assert nested_module is module.cli
    assert nested_module.cli is app_cli
