from __future__ import annotations

import json
import subprocess
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
):
    return collect_problems.ToolSpec(
        name=name,
        command=_StubSpec(name, parser).command,
        parser=parser,
        optional=optional,
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

    outputs: dict[str, dict[str, Any]] = {
        "ruff": {"stdout": ruff_output},
        "mypy": {"stdout": mypy_output, "returncode": 1},
        "bandit": {"stdout": bandit_output, "stderr": "x" * 6000},
        "yamllint": {"stdout": yamllint_output},
        "sqlfluff": {"stdout": sqlfluff_output, "returncode": 65},
    }

    runner = _Runner(outputs)

    tools = [
        _make_spec("ruff", collect_problems.parse_ruff_output),
        _make_spec("mypy", collect_problems.parse_mypy_output),
        _make_spec("pylint", collect_problems.parse_pylint_output, optional=True),
        _make_spec("bandit", collect_problems.parse_bandit_output),
        _make_spec("yamllint", collect_problems.parse_yamllint_output),
        _make_spec("sqlfluff", collect_problems.parse_sqlfluff_output),
    ]

    results = collect_problems.collect(tools=tools, runner=runner.__call__)

    by_tool = {entry["tool"]: entry for entry in results}

    ruff_entry = by_tool["ruff"]
    assert ruff_entry["summary"]["issue_count"] == 1
    assert ruff_entry["issues"][0]["path"] == "firecrawl_demo/core/example.py"

    mypy_entry = by_tool["mypy"]
    assert mypy_entry["summary"] == {"issue_count": 1, "note_count": 1}
    assert mypy_entry["issues"][0]["code"] == "attr-defined"
    assert mypy_entry["notes"][0]["severity"] == "note"

    pylint_entry = by_tool["pylint"]
    assert pylint_entry["status"] == "not_installed"

    bandit_entry = by_tool["bandit"]
    assert bandit_entry["summary"]["severity_counts"]["HIGH"] == 1
    stderr_preview = bandit_entry["stderr_preview"]
    assert stderr_preview["chunks"][0] == "x" * 200
    assert stderr_preview["truncated"] is True
    assert stderr_preview["omitted_characters"] == 4000

    sqlfluff_entry = by_tool["sqlfluff"]
    assert sqlfluff_entry["issues"][0]["code"] == "L001"
    assert sqlfluff_entry["summary"]["issue_count"] == 1

    yamllint_entry = by_tool["yamllint"]
    assert yamllint_entry["issues"][0]["severity"] == "warning"


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
    if collect_problems.SQLFLUFF_TOOL is None:
        pytest.skip("sqlfluff support not available")

    expected = tmp_path / "contracts.duckdb"

    def fake_ensure(project_dir: Path, duckdb_path: Path) -> Path:
        assert project_dir == Path("data_contracts/analytics")
        assert duckdb_path == Path("target/contracts.duckdb")
        return expected

    monkeypatch.setattr(collect_problems, "ensure_duckdb", fake_ensure)

    cmd, env, cwd = collect_problems.SQLFLUFF_TOOL.command()

    assert cmd[:3] == ["sqlfluff", "lint", "data_contracts/analytics"]
    assert env is not None and env["DBT_DUCKDB_PATH"] == expected.as_posix()
    assert cwd is None
