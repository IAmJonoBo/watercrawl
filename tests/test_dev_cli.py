"""Tests for the automation/developer experience CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from click.testing import CliRunner

from apps.automation import cli as automation_cli


def _write_plan(tmp_path: Path) -> Path:
    plan_path = tmp_path / "qa.plan"
    plan_payload = {
        "changes": [
            {
                "field": "Command",
                "value": "qa cleanup",
            }
        ],
        "instructions": "Execute QA cleanup plan",
    }
    plan_path.write_text(json.dumps(plan_payload), encoding="utf-8")
    return plan_path


def _write_commit(tmp_path: Path) -> Path:
    commit_path = tmp_path / "qa.commit"
    commit_payload = {
        "if_match": '"etag-qa"',
        "diff_summary": "QA cleanup tasks acknowledged",
        "diff_format": "markdown",
        "rag": {
            "faithfulness": 0.85,
            "context_precision": 0.82,
            "answer_relevancy": 0.84,
        },
    }
    commit_path.write_text(json.dumps(commit_payload), encoding="utf-8")
    return commit_path


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
        plan_guard=None,
        plan_paths=None,
        commit_paths=None,
        force: bool = False,
    ) -> int:
        if plan_guard is not None and not dry_run:
            for spec in specs:
                if getattr(spec, "requires_plan", False):
                    plan_guard.require(
                        f"qa.{spec.name.lower().replace(' ', '_')}",
                        plan_paths,
                        commit_paths=commit_paths,
                        force=force,
                    )
                    break
        self.capture["specs"] = specs
        self.capture["dry_run"] = dry_run
        self.capture["fail_fast"] = fail_fast
        self.capture["console"] = console
        self.capture["plan_guard"] = plan_guard
        self.capture["plan_paths"] = plan_paths
        self.capture["commit_paths"] = commit_paths
        self.capture["force"] = force
        return 0

    def describe(self) -> str:
        return "recording test runner"


def test_qa_all_dry_run_skips_dbt() -> None:
    captured: dict[str, Any] = {}

    with automation_cli.override_command_runner(_RecordingRunner(captured)):
        runner = CliRunner()
        result = runner.invoke(
            automation_cli.cli,
            ["qa", "all", "--dry-run", "--skip-dbt", "--no-auto-bootstrap"],
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
            [
                "qa",
                "security",
                "--dry-run",
                "--skip-secrets",
                "--no-auto-bootstrap",
            ],
        )
    assert result.exit_code == 0
    specs = cast(list[automation_cli.CommandSpec], captured["specs"])
    assert all("secrets" not in spec.tags for spec in specs)


def test_auto_bootstrap_invoked_for_dependencies(monkeypatch) -> None:
    invoked: dict[str, list[str]] = {}
    monkeypatch.setattr(automation_cli, "_python_meets_minimum", lambda: False)

    def _fake_main(argv: list[str]) -> int:
        invoked["argv"] = argv
        return 0

    monkeypatch.setattr(automation_cli.bootstrap_python, "main", _fake_main)
    captured: dict[str, Any] = {}
    with automation_cli.override_command_runner(_RecordingRunner(captured)):
        runner = CliRunner()
        result = runner.invoke(
            automation_cli.cli,
            ["qa", "dependencies", "--dry-run"],
        )
    assert result.exit_code == 0
    assert invoked["argv"] == [
        "--version",
        automation_cli.bootstrap_python.DEFAULT_VERSION,
        "--install-uv",
        "--poetry",
    ]


def test_auto_bootstrap_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setattr(automation_cli, "_python_meets_minimum", lambda: False)

    def _fail_main(_argv: list[str]) -> int:
        raise AssertionError("bootstrap_python.main should not be called")

    monkeypatch.setattr(automation_cli.bootstrap_python, "main", _fail_main)
    captured: dict[str, Any] = {}
    with automation_cli.override_command_runner(_RecordingRunner(captured)):
        runner = CliRunner()
        result = runner.invoke(
            automation_cli.cli,
            ["qa", "dependencies", "--dry-run", "--no-auto-bootstrap"],
        )
    assert result.exit_code == 0


def test_qa_all_requires_plan_for_cleanup(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}
    with automation_cli.override_command_runner(_RecordingRunner(captured)):
        runner = CliRunner()
        result = runner.invoke(
            automation_cli.cli,
            [
                "qa",
                "all",
                "--no-auto-bootstrap",
                "--skip-dbt",
            ],
        )
    assert result.exit_code != 0
    assert result.exception is not None
    assert "plan" in str(result.exception).lower()


def test_qa_all_accepts_plan(tmp_path: Path) -> None:
    plan_path = _write_plan(tmp_path)
    commit_path = _write_commit(tmp_path)
    captured: dict[str, Any] = {}
    with automation_cli.override_command_runner(_RecordingRunner(captured)):
        runner = CliRunner()
        result = runner.invoke(
            automation_cli.cli,
            [
                "qa",
                "all",
                "--no-auto-bootstrap",
                "--skip-dbt",
                "--plan",
                str(plan_path),
                "--commit",
                str(commit_path),
            ],
        )
    assert result.exit_code == 0
    plan_paths = captured.get("plan_paths")
    assert plan_paths is not None
    assert any(str(plan_path) in str(candidate) for candidate in plan_paths)
    commit_paths = captured.get("commit_paths")
    assert commit_paths is not None
    assert any(str(commit_path) in str(candidate) for candidate in commit_paths)
