"""Tests for the automation/developer experience CLI."""

from __future__ import annotations

from typing import Any, cast

from click.testing import CliRunner

from apps.automation import cli as automation_cli


def test_qa_plan_outputs_table() -> None:
    runner = CliRunner()
    result = runner.invoke(automation_cli.cli, ["qa", "plan"])
    assert result.exit_code == 0
    assert "QA execution plan" in result.output
    assert "Pytest" in result.output


class _RecordingRunner:
    """Test helper implementing the CommandRunner protocol."""

    def __init__(self, capture: dict[str, Any]):
        self.capture = capture

    def __call__(
        self,
        specs,
        *,
        dry_run: bool,
        fail_fast: bool = False,
        console=None,
    ) -> int:
        self.capture["specs"] = specs
        self.capture["dry_run"] = dry_run
        self.capture["fail_fast"] = fail_fast
        self.capture["console"] = console
        return 0

    def describe(self) -> str:
        return "recording test runner"


def test_qa_all_dry_run_skips_dbt() -> None:
    captured: dict[str, Any] = {}

    with automation_cli.override_command_runner(_RecordingRunner(captured)):
        runner = CliRunner()
        result = runner.invoke(
            automation_cli.cli, ["qa", "all", "--dry-run", "--skip-dbt"]
        )
    assert result.exit_code == 0
    assert captured["dry_run"] is True
    assert captured["fail_fast"] is False
    specs = cast(list[automation_cli.CommandSpec], captured["specs"])
    assert specs  # ensure commands were provided
    assert all("dbt" not in spec.tags for spec in specs)


def test_qa_security_skip_secrets() -> None:
    captured: dict[str, Any] = {}

    with automation_cli.override_command_runner(_RecordingRunner(captured)):
        runner = CliRunner()
        result = runner.invoke(
            automation_cli.cli,
            ["qa", "security", "--dry-run", "--skip-secrets"],
        )
    assert result.exit_code == 0
    specs = cast(list[automation_cli.CommandSpec], captured["specs"])
    assert all("secrets" not in spec.tags for spec in specs)
