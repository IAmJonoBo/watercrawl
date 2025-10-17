from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ci_summary import (
    CoverageMetrics,
    TestMetrics,
    build_summary,
    main,
    parse_coverage,
    parse_junit,
)


def test_parse_coverage(tmp_path: Path) -> None:
    report = tmp_path / "coverage.xml"
    report.write_text(
        '<coverage line-rate="0.88" lines-covered="88" lines-valid="100"/>',
        encoding="utf-8",
    )

    metrics = parse_coverage(report)
    assert metrics is not None
    assert pytest.approx(metrics.percent, rel=1e-3) == 88.0
    assert metrics.lines_covered == 88
    assert metrics.lines_valid == 100


def test_parse_junit(tmp_path: Path) -> None:
    report = tmp_path / "pytest.xml"
    report.write_text(
        '<testsuite tests="10" failures="1" errors="0" skipped="2" time="9.5"/>',
        encoding="utf-8",
    )

    metrics = parse_junit(report)
    assert metrics is not None
    assert metrics.tests == 10
    assert metrics.failures == 1
    assert pytest.approx(metrics.time_s, rel=1e-5) == 9.5


def test_summary_rendering() -> None:
    bundle = build_summary(
        CoverageMetrics(line_rate=0.9, lines_covered=90, lines_valid=100),
        TestMetrics(tests=10, failures=0, errors=0, skipped=2, time_s=3.2),
    )

    markdown = bundle.to_markdown()
    assert "CI Summary" in markdown
    assert "Coverage" in markdown

    payload = json.loads(bundle.to_json())
    assert payload["coverage"]["percent"] == pytest.approx(90.0)
    assert payload["tests"]["passed"] == 8


def test_cli_main_writes_outputs(tmp_path: Path) -> None:
    coverage_report = tmp_path / "coverage.xml"
    junit_report = tmp_path / "pytest.xml"
    coverage_report.write_text(
        '<coverage line-rate="0.75" lines-covered="75" lines-valid="100"/>',
        encoding="utf-8",
    )
    junit_report.write_text(
        '<testsuite tests="5" failures="0" errors="0" skipped="0" time="1.5"/>',
        encoding="utf-8",
    )

    markdown_out = tmp_path / "summary.md"
    json_out = tmp_path / "summary.json"

    exit_code = main(
        [
            "--coverage",
            str(coverage_report),
            "--junit",
            str(junit_report),
            "--output",
            str(markdown_out),
            "--json",
            str(json_out),
        ]
    )

    assert exit_code == 0
    assert markdown_out.read_text(encoding="utf-8").startswith("# CI Summary")
    data = json.loads(json_out.read_text(encoding="utf-8"))
    assert data["coverage"]["percent"] == pytest.approx(75.0)
    assert data["tests"]["total"] == 5
