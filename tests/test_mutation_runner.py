from __future__ import annotations

from pathlib import Path

from tools.testing import mutation_runner


def test_mutation_runner_dry_run(tmp_path: Path) -> None:
    output_dir = tmp_path / "mutation"
    exit_code = mutation_runner.run_mutation_tests(
        output_dir=output_dir,
        dry_run=True,
    )
    assert exit_code == 0
    summaries = list(output_dir.glob("mutation_summary_*.json"))
    assert summaries, "summary file should be created in dry-run mode"
