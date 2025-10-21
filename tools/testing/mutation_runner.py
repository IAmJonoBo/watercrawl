"""Run mutation testing using mutmut with curated defaults."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

DEFAULT_TARGETS = (
    "firecrawl_demo/application/pipeline.py",
    "firecrawl_demo/integrations/research/core.py",
)
DEFAULT_TESTS = (
    "tests/test_pipeline.py",
    "tests/test_research_logic.py",
)
DEFAULT_ARTIFACTS_DIR = Path("artifacts/testing/mutation")


def _build_mutmut_command(
    *,
    targets: Sequence[str],
    tests: Sequence[str],
) -> list[str]:
    runner = "python -m pytest " + " ".join(tests)
    return [
        "mutmut",
        "run",
        "--paths-to-mutate",
        ",".join(targets),
        "--runner",
        runner,
    ]


def run_mutation_tests(
    *,
    output_dir: Path,
    targets: Sequence[str] = DEFAULT_TARGETS,
    tests: Sequence[str] = DEFAULT_TESTS,
    dry_run: bool = False,
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    summary_path = output_dir / f"mutation_summary_{timestamp}.json"
    results_path = output_dir / f"mutmut_results_{timestamp}.txt"

    if dry_run:
        summary = {
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "skipped",
            "message": "Dry-run mode; mutation tests not executed.",
            "targets": list(targets),
            "tests": list(tests),
        }
        summary_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
        )
        return 0

    command = _build_mutmut_command(targets=targets, tests=tests)
    run_proc = subprocess.run(command, check=False)  # nosec B603

    results_proc = subprocess.run(
        ["mutmut", "results"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        text=True,
    )  # nosec B603
    results_path.write_text(results_proc.stdout, encoding="utf-8")

    summary = {
        "timestamp": datetime.now(UTC).isoformat(),
        "command": command,
        "exit_code": run_proc.returncode,
        "results_file": str(results_path),
        "targets": list(targets),
        "tests": list(tests),
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )

    latest_symlink = output_dir / "latest.txt"
    try:
        if latest_symlink.exists() or latest_symlink.is_symlink():
            latest_symlink.unlink()
        latest_symlink.symlink_to(results_path.name)
    except OSError:
        # Symlinks might be unavailable on some filesystems; ignore.
        pass

    return run_proc.returncode


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run mutation testing pilot over pipeline hotspots."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_ARTIFACTS_DIR,
        help="Directory to store mutation artefacts (default: artifacts/testing/mutation)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip execution and record a placeholder summary.",
    )
    args = parser.parse_args(argv)

    return run_mutation_tests(
        output_dir=args.output_dir,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
