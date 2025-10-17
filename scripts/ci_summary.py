"""Generate CI summary artefacts for dashboards and job summaries."""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CoverageMetrics:
    """Lightweight representation of coverage results."""

    line_rate: float
    lines_covered: int
    lines_valid: int

    @property
    def percent(self) -> float:
        """Return the coverage percentage as a 0-100 float."""

        return self.line_rate * 100


@dataclass
class TestMetrics:
    """Aggregate metrics extracted from a JUnit XML report."""

    tests: int
    failures: int
    errors: int
    skipped: int
    time_s: float

    @property
    def passed(self) -> int:
        """Return the count of tests that passed."""

        return self.tests - self.failures - self.errors - self.skipped


@dataclass
class SummaryBundle:
    """Combined CI metrics for Markdown and JSON generation."""

    coverage: CoverageMetrics | None = None
    tests: TestMetrics | None = None

    def to_markdown(self) -> str:
        """Render the metrics as a Markdown table."""

        lines = ["# CI Summary", ""]
        rows: list[tuple[str, str]] = []
        if self.tests:
            rows.extend(
                [
                    ("Tests", str(self.tests.tests)),
                    ("Passed", str(self.tests.passed)),
                    ("Failures", str(self.tests.failures)),
                    ("Errors", str(self.tests.errors)),
                    ("Skipped", str(self.tests.skipped)),
                    ("Duration (s)", f"{self.tests.time_s:.2f}"),
                ]
            )
        if self.coverage:
            rows.append(("Coverage", f"{self.coverage.percent:.2f}%"))
            rows.append(
                (
                    "Lines",
                    f"{self.coverage.lines_covered}/{self.coverage.lines_valid}",
                )
            )
        if not rows:
            lines.append("> No metrics available.")
            return "\n".join(lines) + "\n"

        header = "| Metric | Value |"
        separator = "| --- | --- |"
        table_lines = [header, separator]
        table_lines.extend(f"| {metric} | {value} |" for metric, value in rows)
        lines.extend(table_lines)
        lines.append("")
        return "\n".join(lines)

    def to_json(self) -> str:
        """Return a JSON representation of the metrics."""

        payload: dict[str, Any] = {}
        if self.tests:
            payload["tests"] = {
                "total": self.tests.tests,
                "passed": self.tests.passed,
                "failures": self.tests.failures,
                "errors": self.tests.errors,
                "skipped": self.tests.skipped,
                "duration_seconds": self.tests.time_s,
            }
        if self.coverage:
            payload["coverage"] = {
                "percent": round(self.coverage.percent, 4),
                "line_rate": self.coverage.line_rate,
                "lines_covered": self.coverage.lines_covered,
                "lines_valid": self.coverage.lines_valid,
            }
        return json.dumps(payload, indent=2, sort_keys=True)


def parse_coverage(path: Path) -> CoverageMetrics | None:
    """Parse a coverage.py XML report if present."""

    if not path.exists():
        return None

    tree = ET.parse(path)
    root = tree.getroot()

    try:
        line_rate = float(root.attrib.get("line-rate", "0"))
        lines_covered = int(root.attrib.get("lines-covered", "0"))
        lines_valid = int(root.attrib.get("lines-valid", "0"))
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise ValueError(f"Invalid coverage metrics in {path}") from exc

    if lines_valid == 0:
        return None

    return CoverageMetrics(
        line_rate=line_rate,
        lines_covered=lines_covered,
        lines_valid=lines_valid,
    )


def _merge_testsuites(root: ET.Element) -> Iterable[ET.Element]:
    """Yield all test suites contained within the root element."""

    if root.tag == "testsuite":
        yield root
    elif root.tag == "testsuites":
        yield from root.findall("testsuite")
    else:  # pragma: no cover - schema variations
        yield from root.findall("testsuite")


def parse_junit(path: Path) -> TestMetrics | None:
    """Parse a JUnit XML report and return aggregate metrics."""

    if not path.exists():
        return None

    tree = ET.parse(path)
    root = tree.getroot()

    total_tests = 0
    total_failures = 0
    total_errors = 0
    total_skipped = 0
    total_time = 0.0

    for suite in _merge_testsuites(root):
        total_tests += int(suite.attrib.get("tests", "0"))
        total_failures += int(suite.attrib.get("failures", "0"))
        total_errors += int(suite.attrib.get("errors", "0"))
        total_skipped += int(suite.attrib.get("skipped", "0"))
        total_time += float(suite.attrib.get("time", "0"))

    if total_tests == 0:
        return None

    return TestMetrics(
        tests=total_tests,
        failures=total_failures,
        errors=total_errors,
        skipped=total_skipped,
        time_s=total_time,
    )


def build_summary(
    coverage: CoverageMetrics | None, tests: TestMetrics | None
) -> SummaryBundle:
    """Create a combined summary payload from coverage and test metrics."""

    return SummaryBundle(coverage=coverage, tests=tests)


def write_outputs(
    bundle: SummaryBundle, markdown_path: Path, json_path: Path | None
) -> None:
    """Write Markdown and optional JSON summaries to disk."""

    markdown_path.write_text(bundle.to_markdown(), encoding="utf-8")
    if json_path:
        json_path.write_text(bundle.to_json(), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for generating CI dashboard artefacts."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage", type=Path, help="Path to coverage XML report")
    parser.add_argument("--junit", type=Path, help="Path to JUnit XML report")
    parser.add_argument(
        "--output", type=Path, required=True, help="Markdown output path"
    )
    parser.add_argument("--json", type=Path, help="Optional JSON output path")
    args = parser.parse_args(argv)

    coverage_metrics = parse_coverage(args.coverage) if args.coverage else None
    test_metrics = parse_junit(args.junit) if args.junit else None
    bundle = build_summary(coverage_metrics, test_metrics)
    write_outputs(bundle, args.output, args.json)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
