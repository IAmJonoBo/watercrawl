"""Aggregate QA findings into a compact ``problems_report.json`` artefact."""

from __future__ import annotations

import json
import os
import re
import subprocess  # nosec B404 - subprocess usage is for controlled QA tool execution
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SQLFLUFF_AVAILABLE = sys.version_info < (3, 14)
if SQLFLUFF_AVAILABLE:
    try:  # pragma: no branch - import guard for script execution
        from tools.sql.sqlfluff_runner import (
            DEFAULT_DBT_PROJECT,
            DEFAULT_DUCKDB,
            ensure_duckdb,
        )
    except ModuleNotFoundError as exc:  # pragma: no cover - defensive path fix
        if exc.name == "duckdb":
            SQLFLUFF_AVAILABLE = False
        else:
            PROJECT_ROOT = Path(__file__).resolve().parents[1]
            if str(PROJECT_ROOT) not in sys.path:
                sys.path.insert(0, str(PROJECT_ROOT))
            try:
                from tools.sql.sqlfluff_runner import (
                    DEFAULT_DBT_PROJECT,
                    DEFAULT_DUCKDB,
                    ensure_duckdb,
                )
            except ModuleNotFoundError as inner_exc:  # pragma: no cover - fallback
                if inner_exc.name == "duckdb":
                    SQLFLUFF_AVAILABLE = False
                else:
                    raise
else:  # pragma: no cover - placeholders for type checking when disabled
    DEFAULT_DBT_PROJECT = Path("data_contracts/analytics")
    DEFAULT_DUCKDB = Path("target/contracts.duckdb")

    def ensure_duckdb(project_dir: Path, relative_path: Path) -> Path:
        raise RuntimeError(
            f"sqlfluff unavailable on Python {sys.version_info.major}.{sys.version_info.minor}"
        )


# Bandit doesn't support Python 3.14 yet (ast.Num removed)
BANDIT_AVAILABLE = sys.version_info < (3, 14)

REPORT_PATH = Path("problems_report.json")
MAX_TEXT = 2000
MAX_ISSUES = 100
PREVIEW_CHUNK = 200
MAX_PREVIEW_CHUNKS = 40

CompletedProcess = subprocess.CompletedProcess[str]


def _truncate(value: str, *, limit: int = MAX_TEXT) -> str:
    if len(value) <= limit:
        return value
    remaining = len(value) - limit
    return f"{value[:limit]}… (truncated {remaining} characters)"


def _normalise_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def build_preview(
    value: str,
    *,
    limit: int = MAX_TEXT,
    chunk_size: int = PREVIEW_CHUNK,
    max_chunks: int = MAX_PREVIEW_CHUNKS,
) -> dict[str, Any]:
    normalised = _normalise_newlines(value)
    truncated_chars = max(len(normalised) - limit, 0)
    limited = normalised[:limit]
    chunks: list[str] = []
    for raw_line in limited.split("\n"):
        if not raw_line:
            if chunks:
                chunks.append("")
            continue
        for start in range(0, len(raw_line), chunk_size):
            chunks.append(raw_line[start : start + chunk_size])
    omitted_chunks = 0
    truncated = truncated_chars > 0
    if len(chunks) > max_chunks:
        omitted_chunks = len(chunks) - max_chunks
        chunks = chunks[:max_chunks]
        truncated = True
    if truncated:
        if chunks:
            chunks[-1] = f"{chunks[-1]}…"
        else:
            chunks.append("…")
    payload: dict[str, Any] = {"chunks": chunks}
    if truncated:
        payload["truncated"] = True
    if truncated_chars:
        payload["omitted_characters"] = truncated_chars
    if omitted_chunks:
        payload["omitted_chunks"] = omitted_chunks
    return payload


def _attach_preview(entry: dict[str, Any], key: str, value: str | None) -> None:
    if not value:
        return
    entry[key] = build_preview(value)


def _truncate_message(entry: dict[str, Any]) -> None:
    message = entry.get("message")
    if isinstance(message, str):
        entry["message"] = _truncate(message)


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass
class ToolSpec:
    """Describe how to execute and parse a QA tool."""

    name: str
    command: Callable[[], tuple[list[str], Mapping[str, str] | None, Path | None]]
    parser: Callable[[CompletedProcess], dict[str, Any]]
    optional: bool = False


def _static_command(*args: str) -> Callable[[], tuple[list[str], None, None]]:
    def _factory() -> tuple[list[str], None, None]:
        return list(args), None, None

    return _factory


def _sqlfluff_command() -> tuple[list[str], Mapping[str, str], None]:
    duckdb_path = ensure_duckdb(DEFAULT_DBT_PROJECT, DEFAULT_DUCKDB)
    env = os.environ.copy()
    env.setdefault("DBT_DUCKDB_PATH", duckdb_path.as_posix())
    cmd = [
        "sqlfluff",
        "lint",
        str(DEFAULT_DBT_PROJECT),
        "--format",
        "json",
    ]
    return cmd, env, None


def _run_subprocess(
    spec: ToolSpec,
    cmd: Sequence[str],
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> CompletedProcess:
    # nosec B603 - cmd is constructed from trusted tool specs (ruff, mypy, etc.)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        env=dict(env) if env is not None else None,
        cwd=cwd,
    )


def parse_ruff_output(result: CompletedProcess) -> dict[str, Any]:
    try:
        findings = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        payload = {"issues": [], "summary": {"issue_count": 0}}
        _attach_preview(payload, "raw_preview", result.stdout or "")
        return payload

    issues: list[dict[str, Any]] = []
    fixable = sum(1 for item in findings if item.get("fix"))
    for item in findings[:MAX_ISSUES]:
        location = item.get("location") or {}
        entry = {
            "path": item.get("filename"),
            "line": location.get("row"),
            "column": location.get("column"),
            "code": item.get("code"),
            "message": item.get("message"),
        }
        _truncate_message(entry)
        issues.append(entry)
    omitted = max(len(findings) - MAX_ISSUES, 0)
    return {
        "issues": issues,
        "summary": {
            "issue_count": len(findings),
            "fixable": fixable,
            **({"omitted_issues": omitted} if omitted else {}),
        },
    }


_MYPY_PATTERN = re.compile(
    r"^(?P<path>[^:]+):(?P<line>\d+): (?:(?P<column>\d+): )?(?P<severity>\w+): "
    r"(?P<message>.*?)(?: \[(?P<code>[\w\-\.]+)\])?$"
)


def parse_mypy_output(result: CompletedProcess) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    notes: list[dict[str, Any]] = []
    for raw_line in (result.stdout or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("Success:"):
            continue
        match = _MYPY_PATTERN.match(line)
        if not match:
            continue
        data = match.groupdict()
        entry: dict[str, Any] = {
            "path": data.get("path"),
            "line": _coerce_int(data.get("line")),
            "message": data.get("message"),
            "severity": (data.get("severity") or "").lower(),
        }
        column = _coerce_int(data.get("column"))
        if column is not None:
            entry["column"] = column
        code = data.get("code")
        if code:
            entry["code"] = code
        _truncate_message(entry)
        target = notes if entry["severity"] == "note" else issues
        target.append(entry)
    trimmed_issues = issues[:MAX_ISSUES]
    trimmed_notes = notes[:MAX_ISSUES]
    summary: dict[str, Any] = {
        "issue_count": len(issues),
        "note_count": len(notes),
    }
    if len(issues) > MAX_ISSUES:
        summary["omitted_issues"] = len(issues) - MAX_ISSUES
    if len(notes) > MAX_ISSUES:
        summary["omitted_notes"] = len(notes) - MAX_ISSUES
    return {
        "issues": trimmed_issues,
        "notes": trimmed_notes,
        "summary": summary,
    }


def parse_pylint_output(result: CompletedProcess) -> dict[str, Any]:
    payload = result.stdout or ""
    if not payload.strip():
        return {"issues": [], "summary": {"issue_count": 0}}
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        fallback_result: dict[str, Any] = {"issues": [], "summary": {"issue_count": 0}}
        _attach_preview(fallback_result, "raw_preview", payload)
        return fallback_result
    messages: Iterable[dict[str, Any]]
    score: Any = None
    if isinstance(parsed, dict):
        messages = parsed.get("messages", [])
        score = parsed.get("score")
    else:
        messages = parsed
    items = list(messages)
    issues = []
    for message in items[:MAX_ISSUES]:
        entry = {
            "path": message.get("path") or message.get("module"),
            "line": message.get("line"),
            "column": message.get("column"),
            "code": message.get("symbol") or message.get("message-id"),
            "message": message.get("message"),
            "severity": message.get("type"),
        }
        _truncate_message(entry)
        issues.append(entry)
    summary: dict[str, Any] = {"issue_count": len(items)}
    if len(items) > MAX_ISSUES:
        summary["omitted_issues"] = len(items) - MAX_ISSUES
    if score is not None:
        summary["score"] = score
    return {"issues": issues, "summary": summary}


def parse_bandit_output(result: CompletedProcess) -> dict[str, Any]:
    payload = result.stdout or ""
    try:
        parsed = json.loads(payload) if payload else {}
    except json.JSONDecodeError:
        fallback_result: dict[str, Any] = {"issues": [], "summary": {"issue_count": 0}}
        _attach_preview(fallback_result, "raw_preview", payload)
        return fallback_result
    results = parsed.get("results", []) or []
    issues: list[dict[str, Any]] = []
    severity_counts: Counter[str] = Counter()
    confidence_counts: Counter[str] = Counter()
    for finding in results[:MAX_ISSUES]:
        severity = finding.get("issue_severity") or "UNKNOWN"
        confidence = finding.get("issue_confidence") or "UNKNOWN"
        severity_counts[severity] += 1
        confidence_counts[confidence] += 1
        entry = {
            "path": finding.get("filename"),
            "line": finding.get("line_number"),
            "code": finding.get("test_id"),
            "message": finding.get("issue_text"),
            "severity": severity,
            "confidence": confidence,
        }
        _truncate_message(entry)
        issues.append(entry)
    summary: dict[str, Any] = {
        "issue_count": len(results),
        "severity_counts": dict(severity_counts),
        "confidence_counts": dict(confidence_counts),
    }
    if len(results) > MAX_ISSUES:
        summary["omitted_issues"] = len(results) - MAX_ISSUES
    totals = parsed.get("metrics", {}).get("_totals")
    if isinstance(totals, dict):
        summary["metrics"] = {
            key: totals.get(key) for key in ("loc", "nosec", "skipped_tests")
        }
    return {"issues": issues, "summary": summary}


_YAMLLINT_PATTERN = re.compile(
    r"^(?P<path>[^:]+):(?P<line>\d+):(?P<column>\d+): \[(?P<level>[^]]+)\] "
    r"(?P<message>.*?)(?:  \((?P<rule>[^)]+)\))?$"
)


def parse_yamllint_output(result: CompletedProcess) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    for raw_line in (result.stdout or "").splitlines():
        match = _YAMLLINT_PATTERN.match(raw_line.strip())
        if not match:
            continue
        data = match.groupdict()
        entry: dict[str, Any] = {
            "path": data.get("path"),
            "line": _coerce_int(data.get("line")),
            "column": _coerce_int(data.get("column")),
            "severity": (data.get("level") or "").lower(),
            "message": data.get("message"),
        }
        if data.get("rule"):
            entry["rule"] = data["rule"]
        _truncate_message(entry)
        issues.append(entry)
    trimmed = issues[:MAX_ISSUES]
    summary: dict[str, Any] = {"issue_count": len(issues)}
    if len(issues) > MAX_ISSUES:
        summary["omitted_issues"] = len(issues) - MAX_ISSUES
    return {"issues": trimmed, "summary": summary}


def parse_sqlfluff_output(result: CompletedProcess) -> dict[str, Any]:
    payload = result.stdout or ""
    try:
        parsed = json.loads(payload) if payload else []
    except json.JSONDecodeError:
        fallback_result: dict[str, Any] = {"issues": [], "summary": {"issue_count": 0}}
        _attach_preview(fallback_result, "raw_preview", payload)
        return fallback_result
    issues: list[dict[str, Any]] = []
    files_with_issues = 0
    for entry in parsed:
        violations = entry.get("violations") or []
        if violations:
            files_with_issues += 1
        for violation in violations:
            item = {
                "path": entry.get("filepath"),
                "line": violation.get("start_line_no"),
                "column": violation.get("start_line_pos"),
                "code": violation.get("code"),
                "message": violation.get("description"),
                "warning": bool(violation.get("warning")),
            }
            _truncate_message(item)
            issues.append(item)
            if len(issues) >= MAX_ISSUES:
                break
        if len(issues) >= MAX_ISSUES:
            break
    omitted = max(len(issues) - MAX_ISSUES, 0)
    return {
        "issues": issues,
        "summary": {
            "issue_count": len(issues),
            "files_with_issues": files_with_issues,
            **({"omitted_issues": omitted} if omitted else {}),
        },
    }


TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="ruff",
        command=_static_command("ruff", "check", ".", "--output-format", "json"),
        parser=parse_ruff_output,
    ),
    ToolSpec(
        name="mypy",
        command=_static_command(
            "mypy",
            ".",
            "--no-pretty",
            "--show-error-codes",
            "--hide-error-context",
            "--no-error-summary",
        ),
        parser=parse_mypy_output,
    ),
    ToolSpec(
        name="yamllint",
        command=_static_command("yamllint", "--format", "parsable", "."),
        parser=parse_yamllint_output,
    ),
]

if os.getenv("ENABLE_PYLINT", "0") == "1":
    TOOL_SPECS.append(
        ToolSpec(
            name="pylint",
            command=_static_command(
                "pylint",
                "firecrawl_demo",
                "app",
                "scripts",
                "tests",
                "--output-format=json",
                "--score=n",
            ),
            parser=parse_pylint_output,
            optional=True,
        )
    )

BANDIT_TOOL: ToolSpec | None = None
if BANDIT_AVAILABLE:
    BANDIT_TOOL = ToolSpec(
        name="bandit",
        command=_static_command("bandit", "-r", "firecrawl_demo", "-f", "json"),
        parser=parse_bandit_output,
    )
    TOOL_SPECS.append(BANDIT_TOOL)

SQLFLUFF_TOOL: ToolSpec | None = None
if SQLFLUFF_AVAILABLE:
    SQLFLUFF_TOOL = ToolSpec(
        name="sqlfluff",
        command=_sqlfluff_command,
        parser=parse_sqlfluff_output,
    )
    TOOL_SPECS.append(SQLFLUFF_TOOL)


def collect(
    *,
    tools: Sequence[ToolSpec] | None = None,
    runner: (
        Callable[
            [ToolSpec, Sequence[str], Mapping[str, str] | None, Path | None],
            CompletedProcess,
        ]
        | None
    ) = None,
) -> list[dict[str, Any]]:
    specs = list(tools or TOOL_SPECS)
    run = runner or _run_subprocess
    aggregated: list[dict[str, Any]] = []
    for spec in specs:
        try:
            cmd, env, cwd = spec.command()
        except Exception as exc:  # pragma: no cover - defensive guard
            aggregated.append(
                {
                    "tool": spec.name,
                    "status": "failed_to_prepare",
                    "error": _truncate(str(exc)),
                }
            )
            continue
        try:
            completed = run(spec, cmd, env, cwd)
        except FileNotFoundError as exc:
            aggregated.append(
                {
                    "tool": spec.name,
                    "status": "not_installed" if spec.optional else "failed",
                    "error": str(exc),
                }
            )
            continue
        except Exception as exc:  # pragma: no cover - defensive guard
            aggregated.append(
                {
                    "tool": spec.name,
                    "status": "failed",
                    "error": _truncate(str(exc)),
                }
            )
            continue
        parsed = spec.parser(completed)
        entry: dict[str, Any] = {
            "tool": spec.name,
            "status": (
                "completed" if completed.returncode == 0 else "completed_with_exit_code"
            ),
            "returncode": completed.returncode,
        }
        entry.update(parsed)
        entry.setdefault("issues", [])
        if completed.stderr:
            _attach_preview(entry, "stderr_preview", completed.stderr)
        aggregated.append(entry)
    return aggregated


def write_report(results: Sequence[dict[str, Any]]) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tools": list(results),
    }
    REPORT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    results = collect()
    write_report(results)
    print(f"Problems report written to {REPORT_PATH}")


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    main()
