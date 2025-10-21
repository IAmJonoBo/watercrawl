"""Utility to run SQLFluff with an ensured DuckDB target for offline CI."""

from __future__ import annotations

import argparse
import os

# Bandit: subprocess usage is limited to the sqlfluff CLI with curated args.
import subprocess  # nosec B404
import sys
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path

import duckdb

DEFAULT_DBT_PROJECT = Path("data_contracts/analytics")
DEFAULT_DUCKDB = Path("target/contracts.duckdb")


def ensure_duckdb(project_dir: Path, relative_path: Path) -> Path:
    materialised_path = (project_dir / relative_path).resolve()
    materialised_path.parent.mkdir(parents=True, exist_ok=True)

    def _initialise(path: Path) -> None:
        with duckdb.connect(str(path)) as connection:
            connection.execute("PRAGMA database_list;")

    if not materialised_path.exists():
        _initialise(materialised_path)
        return materialised_path

    try:
        _initialise(materialised_path)
    except duckdb.Error:
        with suppress(FileNotFoundError):
            materialised_path.unlink()
        _initialise(materialised_path)

    return materialised_path


def run_sqlfluff(
    project_dir: Path, duckdb_path: Path, extra_args: Sequence[str]
) -> int:
    if sys.version_info >= (3, 14):
        print(
            "Skipping SQLFluff lint: dbt templater is incompatible with Python >= 3.14. "
            "Run this command from a Python 3.13 environment when SQL checks are required."
        )
        return 0

    materialised_path = ensure_duckdb(project_dir, duckdb_path)
    env = os.environ.copy()
    env.setdefault("DBT_DUCKDB_PATH", materialised_path.as_posix())
    # Seed CONTRACTS_CANONICAL_JSON if a canonical file is present to help
    # dbt macros compile during SQLFluff runs in offline CI.
    canonical_path = project_dir / "contracts_canonical.json"
    if canonical_path.exists():
        try:
            with canonical_path.open("r", encoding="utf-8") as fh:
                env["CONTRACTS_CANONICAL_JSON"] = fh.read()
        except OSError:
            # Best-effort; leave env unchanged if reading fails
            pass
    cmd = ["sqlfluff", "lint", str(project_dir), *extra_args]
    print("Executing:", " ".join(cmd))
    completed = subprocess.run(cmd, env=env, check=False)  # nosec B603
    return completed.returncode


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run SQLFluff with offline-friendly defaults."
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=DEFAULT_DBT_PROJECT,
        help="dbt project directory to lint (default: data_contracts/analytics)",
    )
    parser.add_argument(
        "--duckdb-path",
        type=Path,
        default=DEFAULT_DUCKDB,
        help="DuckDB target path to materialise if missing (default: data_contracts/analytics/target/contracts.duckdb)",
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


# Backwards compatibility for callers still importing the private helper.
_ensure_duckdb = ensure_duckdb


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
