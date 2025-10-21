from __future__ import annotations

import json

# Subprocess interactions are stubbed to exercise the collector pipeline.
import subprocess  # nosec B404
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from scripts import collect_problems


@dataclass
class _StubSpec:
    name: str
    parser: Callable[[subprocess.CompletedProcess[str]], dict[str, Any]]

    def command(self) -> tuple[list[str], dict[str, str] | None, Path | None]:
        return [self.name], None, None


class _Runner:
    def __init__(self, outputs: dict[str, dict[str, Any]]):
        self._outputs = outputs
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        spec: collect_problems.ToolSpec,
        cmd: Sequence[str],
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if spec.name == "pylint":  # simulate optional tool missing from PATH
            raise FileNotFoundError("pylint")
        payload = self._outputs[spec.name]
        self.calls.append({"tool": spec.name, "cmd": list(cmd), "env": env, "cwd": cwd})
        return subprocess.CompletedProcess(
            cmd,
            payload.get("returncode", 0),
            stdout=payload.get("stdout", ""),
            stderr=payload.get("stderr", ""),
        )


def _make_spec(
    name: str,
    parser: Callable[[subprocess.CompletedProcess[str]], dict[str, Any]],
    *,
    optional: bool = False,
    autofix: tuple[tuple[str, ...], ...] | None = None,
):
    return collect_problems.ToolSpec(
        name=name,
        command=_StubSpec(name, parser).command,
        parser=parser,
        optional=optional,
        autofix=autofix or (),
    )


def test_collect_aggregates_and_truncates_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ruff_output = json.dumps(
        [
            {
                "filename": "firecrawl_demo/core/example.py",
                "code": "F401",
                "message": "module imported but unused",
                "location": {"row": 12, "column": 5},
            }
        ]
    )
    mypy_output = (
        "firecrawl_demo/core/example.py:12: note: By default the bodies of untyped functions are not\n"
        "firecrawl_demo/core/example.py:40: error: Example failure [attr-defined]\n"
        "Success: no issues found in 1 source file"
    )
    bandit_output = json.dumps(
        {
            "results": [
                {
                    "filename": "firecrawl_demo/core/example.py",
                    "issue_text": "Use of exec detected",
                    "issue_severity": "HIGH",
                    "issue_confidence": "HIGH",
                    "line_number": 33,
                    "test_id": "B102",
                }
            ],
            "metrics": {"_totals": {"loc": 10}},
        }
    )
    yamllint_output = (
        "docs/example.yaml:2:1: [warning] trailing spaces  (trailing-spaces)"
    )
    sqlfluff_output = json.dumps(
        [
            {
                "filepath": "data_contracts/analytics/models/example.sql",
                "violations": [
                    {
                        "start_line_no": 4,
                        "start_line_pos": 7,
                        "code": "L001",
                        "description": "Indentation not consistent",
                        "name": "",
                        "warning": False,
                    }
                ],
            }
        ]
    )
    trunk_output = json.dumps(
        {
            "results": [
                {
                    "check_id": "Ruff/F401",
                    "severity": "ERROR",
                    "linter": "ruff",
                    "message": "module imported but unused",
                    "location": {
                        "path": "firecrawl_demo/core/example.py",
                        "line": 3,
                        "column": 1,
                    },
                },
                {
                    "check_id": "YAML/L001",
                    "severity": "WARNING",
                    "linter": "yamllint",
                    "message": "Trailing spaces",
                    "location": {
                        "path": "docs/example.yaml",
                        "line": 5,
                        "column": 1,
                    },
                },
            ]
        }
    )

    biome_output = '{"path":"app/main.ts","diagnostics":[{"code":"noUnusedVariables","message":"unused variable foo","severity":"error","span":{"start":{"line":4,"column":5}},"fixable":true}]}'

    outputs: dict[str, dict[str, Any]] = {
        "ruff": {"stdout": ruff_output},
        "mypy": {
            "stdout": mypy_output,
            "stderr": "firecrawl_demo/core/example.py:1: DeprecationWarning: yaml.load is deprecated",
            "returncode": 1,
        },
        "bandit": {
            "stdout": bandit_output,
            "stderr": "x" * 6000
            + "\n[manager]\tWARNING\tTest in comment: controlled is not a test name or id, ignoring",
        },
        "yamllint": {"stdout": yamllint_output},
        "sqlfluff": {
            "stdout": sqlfluff_output,
            "stderr": "WARNING    Skipped file data_contracts/analytics/macros/contracts_shared.sql because it is a macro ",
            "returncode": 65,
        },
        "trunk": {"stdout": trunk_output},
        "biome": {"stdout": biome_output},
    }

    runner = _Runner(outputs)

    tools = [
        _make_spec(
            "ruff",
            collect_problems.parse_ruff_output,
            autofix=(("ruff", "check", ".", "--fix"),),
        ),
        _make_spec("mypy", collect_problems.parse_mypy_output),
        _make_spec("pylint", collect_problems.parse_pylint_output, optional=True),
        _make_spec("bandit", collect_problems.parse_bandit_output),
        _make_spec("yamllint", collect_problems.parse_yamllint_output),
        _make_spec("sqlfluff", collect_problems.parse_sqlfluff_output),
        _make_spec("trunk", collect_problems.parse_trunk_output, optional=True),
        _make_spec("biome", collect_problems.parse_biome_output, optional=True),
    ]

    results = collect_problems.collect(tools=tools, runner=runner.__call__)

    by_tool = {entry["tool"]: entry for entry in results}

    ruff_entry = by_tool["ruff"]
    assert ruff_entry["summary"]["issue_count"] == 1
    assert ruff_entry["issues"][0]["path"] == "firecrawl_demo/core/example.py"

    mypy_entry = by_tool["mypy"]
    assert mypy_entry["summary"]["issue_count"] == 1
    assert mypy_entry["summary"]["note_count"] == 1
    assert mypy_entry["issues"][0]["code"] == "attr-defined"
    assert mypy_entry["notes"][0]["severity"] == "note"
    assert mypy_entry["summary"]["warning_count"] == 1
    assert mypy_entry["warnings"][0]["category"] == "DeprecationWarning"

    pylint_entry = by_tool["pylint"]
    assert pylint_entry["status"] == "not_installed"

    bandit_entry = by_tool["bandit"]
    assert bandit_entry["summary"]["severity_counts"]["HIGH"] == 1
    stderr_preview = bandit_entry["stderr_preview"]
    assert stderr_preview["chunks"][0] == "x" * 200
    assert stderr_preview["truncated"] is True
    assert stderr_preview["omitted_characters"] >= 4000
    assert bandit_entry["summary"]["warning_count"] == 1
    assert bandit_entry["warnings"][0]["source"] == "manager"

    sqlfluff_entry = by_tool["sqlfluff"]
    assert sqlfluff_entry["issues"][0]["code"] == "L001"
    assert sqlfluff_entry["summary"]["issue_count"] == 1
    assert sqlfluff_entry["summary"].get("warning_count", 0) == 0
    assert not sqlfluff_entry.get("warnings")

    yamllint_entry = by_tool["yamllint"]
    assert yamllint_entry["issues"][0]["severity"] == "warning"

    trunk_ruff_entry = by_tool["trunk:ruff"]
    assert trunk_ruff_entry["summary"]["issue_count"] == 1
    assert trunk_ruff_entry["issues"][0]["path"] == "firecrawl_demo/core/example.py"
    assert trunk_ruff_entry["issues"][0]["insight"].startswith("Unused symbol")
    assert trunk_ruff_entry["issues"][0]["severity"] == "error"

    trunk_yaml_entry = by_tool["trunk:yamllint"]
    assert trunk_yaml_entry["summary"]["issue_count"] == 1
    assert trunk_yaml_entry["issues"][0]["path"] == "docs/example.yaml"
    assert trunk_yaml_entry["issues"][0]["severity"] == "warning"

    biome_entry = by_tool["biome"]
    assert biome_entry["summary"]["issue_count"] == 1
    assert biome_entry["issues"][0]["path"] == "app/main.ts"
    assert biome_entry["issues"][0]["insight"].startswith(
        "Biome detected unused symbols"
    )

    overall = collect_problems.build_overall_summary(results)
    assert overall["issue_count"] == 8
    assert overall["fixable_count"] == 1
    assert overall["potential_dead_code"] >= 2
    assert "ruff" in overall["tools_run"]
    assert "trunk:ruff" in overall["tools_run"]
    assert overall["warning_count"] == 2
    assert any(
        insight.get("kind") == "deprecation" for insight in overall["warning_insights"]
    )
    configured = overall.get("configured_tools")
    if configured:
        assert "trunk_enabled" in configured
    actions = overall.get("actions") or []
    assert any(
        action.get("type") == "autofix" and action.get("tool") == "ruff"
        for action in actions
    )
    assert any(action.get("type") == "warnings" for action in actions)


def test_collect_surfaces_non_zero_exit_without_findings() -> None:
    outputs = {
        "failing": {
            "stdout": "",
            "stderr": "",
            "returncode": 2,
        }
    }
    runner = _Runner(outputs)

    def parser(_: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        return {"issues": [], "summary": {"issue_count": 0}}

    tools = [_make_spec("failing", parser)]

    results = collect_problems.collect(tools=tools, runner=runner.__call__)
    assert len(results) == 1
    entry = results[0]
    assert entry["status"] == "completed_with_exit_code"
    assert entry["issues"]
    issue = entry["issues"][0]
    assert issue["code"] == "tool_exit_non_zero"
    assert issue["severity"] == "error"
    summary = entry["summary"]
    assert summary["issue_count"] == 1
    assert summary["severity_counts"]["error"] == 1


def test_collect_default_registry_includes_autofix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_runner(
        spec: collect_problems.ToolSpec,
        cmd: Sequence[str],
        env: Mapping[str, str] | None,
        cwd: Path | None,
    ) -> subprocess.CompletedProcess[str]:
        if spec.name == "bandit":
            stdout = json.dumps({"results": [], "metrics": {}})
        elif spec.name == "mypy":
            stdout = "Success: no issues found\n"
        elif spec.name == "ruff":
            stdout = "[]"
        elif spec.name == "yamllint":
            stdout = ""
        else:
            stdout = ""
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(collect_problems, "_run_subprocess", fake_runner)
    results = collect_problems.collect()
    ruff_entry = next(entry for entry in results if entry["tool"] == "ruff")
    assert "autofix_commands" in ruff_entry
    assert any("ruff" in cmd for cmd in ruff_entry["autofix_commands"])


def test_vscode_fallback_parses_markers(tmp_path: Path) -> None:
    payload = {
        "problems": [
            {
                "message": "Example lint error",
                "severity": 1,
                "source": "pylint",
                "code": {"value": "E0001"},
                "location": {
                    "uri": "file:///repo/module.py",
                    "range": {"start": {"line": 10, "character": 4}},
                },
            },
            {
                "message": "Trailing whitespace",
                "severity": "warning",
                "source": "markdownlint",
                "location": {
                    "path": "/repo/docs/example.md",
                    "lineNumber": 5,
                    "column": 1,
                },
            },
        ]
    }
    export_path = tmp_path / "vscode_problems.json"
    export_path.write_text(json.dumps(payload), encoding="utf-8")
    entries = collect_problems._collect_vscode_problems_fallback(
        {collect_problems.VSCODE_PROBLEMS_ENV: str(export_path)}
    )
    by_tool = {entry["tool"]: entry for entry in entries}
    pylint_entry = by_tool["vscode:pylint"]
    assert pylint_entry["summary"]["issue_count"] == 1
    pylint_issue = pylint_entry["issues"][0]
    assert pylint_issue["path"].endswith("module.py")
    assert pylint_issue["line"] == 10
    assert pylint_issue["severity"] == "error"
    markdown_entry = by_tool["vscode:markdownlint"]
    assert markdown_entry["issues"][0]["severity"] == "warning"


def test_preview_handles_multiline_chunks() -> None:
    payload = "line-" + "a" * 210 + "\nsecond-line"
    preview = collect_problems.build_preview(
        payload, limit=170, chunk_size=50, max_chunks=10
    )

    assert preview["chunks"][0] == "line-" + "a" * 45
    assert preview["chunks"][1] == "a" * 50
    assert preview["chunks"][2] == "a" * 50
    assert preview["chunks"][3].startswith("a" * 20)
    assert preview["chunks"][3].endswith("…")
    assert preview["truncated"] is True
    assert preview["omitted_characters"] == 57


def test_sqlfluff_command_sets_duckdb_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry = collect_problems.build_tool_registry()
    sqlfluff_specs = [spec for spec in registry.values() if spec.name == "sqlfluff"]
    if not sqlfluff_specs:
        pytest.skip("sqlfluff support not available")

    tool = sqlfluff_specs[0]

    expected = tmp_path / "contracts.duckdb"

    def fake_ensure(project_dir: Path, duckdb_path: Path) -> Path:
        assert project_dir == Path("data_contracts/analytics")
        assert duckdb_path == Path("target/contracts.duckdb")
        return expected

    monkeypatch.setattr(collect_problems, "ensure_duckdb", fake_ensure)

    cmd, env, cwd = tool.command()

    assert cmd[:3] == ["sqlfluff", "lint", "data_contracts/analytics"]
    assert env is not None and env["DBT_DUCKDB_PATH"] == expected.as_posix()
    assert cwd is None


def test_run_autofixes_executes_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_runner(cmd: Sequence[str]):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    results = collect_problems.run_autofixes(["ruff", "unknown"], runner=fake_runner)
    assert calls[0][:3] == ["poetry", "run", "ruff"]
    status_by_tool = {entry["tool"]: entry["status"] for entry in results}
    assert status_by_tool["ruff"] == "succeeded"
    assert status_by_tool["unknown"] == "unsupported"
    ruff_autofix = next(entry for entry in results if entry["tool"] == "ruff")
    assert ruff_autofix["commands"][0]["command"][:3] == ["poetry", "run", "ruff"]


def test_write_report_includes_autofixes(tmp_path: Path) -> None:
    results = [
        {
            "tool": "ruff",
            "status": "completed",
            "summary": {"issue_count": 0},
            "issues": [],
        }
    ]
    autofixes = [{"tool": "ruff", "status": "succeeded"}]
    output = tmp_path / "report.json"
    collect_problems.write_report(results, autofixes=autofixes, output_path=output)
    payload = json.loads(output.read_text())
    assert payload["autofixes"][0]["tool"] == "ruff"
    assert payload["summary"]["autofix"]["succeeded"] == 1


def test_mypy_command_includes_stubs_in_mypypath() -> None:
    """Test that mypy command builder includes stubs in MYPYPATH for ephemeral runners."""
    cmd, env, cwd = collect_problems._mypy_command()

    assert cmd[0] == "mypy"
    assert "." in cmd
    assert "--show-error-codes" in cmd

    # Verify MYPYPATH is set when stubs directory exists
    repo_root = Path(__file__).resolve().parents[1]
    stubs_path = repo_root / "stubs"

    if stubs_path.exists():
        assert env is not None
        assert "MYPYPATH" in env
        mypypath = env["MYPYPATH"]
        # Should include both third_party and base stubs directories
        assert str(stubs_path) in mypypath
        third_party = stubs_path / "third_party"
        if third_party.exists():
            assert str(third_party) in mypypath


def test_ephemeral_runner_summary_includes_stubs_info() -> None:
    """Test that summary includes information about stubs availability."""
    results = [
        {
            "tool": "mypy",
            "status": "completed",
            "summary": {"issue_count": 0, "note_count": 0},
            "issues": [],
            "notes": [],
        }
    ]
    summary = collect_problems.build_overall_summary(results)

    # Should include stubs_available flag
    assert "stubs_available" in summary

    # If stubs are available, should have ephemeral runner notes
    if summary["stubs_available"]:
        assert "ephemeral_runner_notes" in summary
        notes = summary["ephemeral_runner_notes"]
        assert any("stubs" in note.lower() for note in notes)


def test_contracts_environment_fallback_graceful() -> None:
    """Test that contracts_environment_payload has a graceful fallback."""
    # This should not raise an error even if firecrawl_demo is not available
    result = collect_problems.contracts_environment_payload()
    assert isinstance(result, dict)


def test_collect_tracks_tool_execution_duration() -> None:
    """Test that the collector tracks and reports tool execution times."""
    outputs = {
        "ruff": {"stdout": "[]", "returncode": 0},
        "mypy": {"stdout": "Success: no issues found\n", "returncode": 0},
    }
    runner = _Runner(outputs)

    tools = [
        _make_spec("ruff", collect_problems.parse_ruff_output),
        _make_spec("mypy", collect_problems.parse_mypy_output),
    ]

    results = collect_problems.collect(tools=tools, runner=runner.__call__)

    # All tools should have duration tracking
    for entry in results:
        assert "duration_seconds" in entry
        assert isinstance(entry["duration_seconds"], (int, float))
        assert entry["duration_seconds"] >= 0

    # Summary should include performance metrics
    summary = collect_problems.build_overall_summary(results)
    assert "performance" in summary
    assert "total_duration_seconds" in summary["performance"]
    assert "slowest_tools" in summary["performance"]
    assert isinstance(summary["performance"]["slowest_tools"], list)
