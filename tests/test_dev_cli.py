"""Tests for the developer experience CLI."""

from __future__ import annotations

from typing import Any, cast

from click.testing import CliRunner

from dev import cli as dev_cli


def test_qa_plan_outputs_table() -> None:
    runner = CliRunner()
    result = runner.invoke(dev_cli.cli, ["qa", "plan"])
    assert result.exit_code == 0
    assert "QA execution plan" in result.output
    assert "Pytest" in result.output


def test_qa_all_dry_run_skips_dbt() -> None:
    captured: dict[str, Any] = {}

    def fake_run(specs, *, dry_run: bool, fail_fast: bool = False, console=None):  # type: ignore[override]
        captured["specs"] = specs
        captured["dry_run"] = dry_run
        captured["fail_fast"] = fail_fast
        return 0

    with dev_cli.override_command_runner(fake_run):
        runner = CliRunner()
        result = runner.invoke(dev_cli.cli, ["qa", "all", "--dry-run", "--skip-dbt"])
    assert result.exit_code == 0
    assert captured["dry_run"] is True
    assert captured["fail_fast"] is False
    specs = cast(list[dev_cli.CommandSpec], captured["specs"])
    assert specs  # ensure commands were provided
    assert all("dbt" not in spec.tags for spec in specs)


def test_qa_security_skip_secrets() -> None:
    captured: dict[str, Any] = {}

    def fake_run(specs, *, dry_run: bool, fail_fast: bool = False, console=None):  # type: ignore[override]
        captured["specs"] = specs
        captured["dry_run"] = dry_run
        return 0

    with dev_cli.override_command_runner(fake_run):
        runner = CliRunner()
        result = runner.invoke(
            dev_cli.cli,
            ["qa", "security", "--dry-run", "--skip-secrets"],
        )
    assert result.exit_code == 0
    specs = cast(list[dev_cli.CommandSpec], captured["specs"])
    assert all("secrets" not in spec.tags for spec in specs)
