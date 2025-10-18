"""Utility to run SQLFluff with an ensured DuckDB target for offline CI."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

DEFAULT_DBT_PROJECT = Path("analytics")
DEFAULT_DUCKDB = Path("target/contracts.duckdb")


def _ensure_duckdb(project_dir: Path, relative_path: Path) -> None:
    materialised_path = project_dir / relative_path
    materialised_path.parent.mkdir(parents=True, exist_ok=True)
    if not materialised_path.exists():
        materialised_path.touch()


def run_sqlfluff(
    project_dir: Path, duckdb_path: Path, extra_args: Sequence[str]
) -> int:
    _ensure_duckdb(project_dir, duckdb_path)
    env = os.environ.copy()
    env.setdefault("DBT_DUCKDB_PATH", duckdb_path.as_posix())
    cmd = ["sqlfluff", "lint", str(project_dir), *extra_args]
    print("Executing:", " ".join(cmd))
    completed = subprocess.run(cmd, env=env, check=False)
    return completed.returncode


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run SQLFluff with offline-friendly defaults."
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=DEFAULT_DBT_PROJECT,
        help="dbt project directory to lint (default: analytics)",
    )
    parser.add_argument(
        "--duckdb-path",
        type=Path,
        default=DEFAULT_DUCKDB,
        help="DuckDB target path to materialise if missing (default: analytics/target/contracts.duckdb)",
    )
    parser.add_argument(
        "extra_args",
        nargs=argparse.REMAINDER,
        help="Additional arguments to forward to sqlfluff (prefix with --).",
    )
    args = parser.parse_args(argv)
    extra = list(args.extra_args or [])
    if extra and extra[0] == "--":
        extra = extra[1:]
    return run_sqlfluff(args.project_dir, args.duckdb_path, extra)


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
