from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import duckdb

from tools.sql import sqlfluff_runner


def _assert_valid_duckdb(path: Path) -> None:
    with duckdb.connect(str(path)) as conn:
        conn.execute("PRAGMA database_list;")


def test_ensure_duckdb_initialises_database(tmp_path: Path) -> None:
    project_dir = tmp_path
    relative_path = Path("target/contracts.duckdb")

    materialised = sqlfluff_runner.ensure_duckdb(project_dir, relative_path)

    assert materialised == (project_dir / relative_path).resolve()
    _assert_valid_duckdb(materialised)


def test_ensure_duckdb_rebuilds_invalid_databases(tmp_path: Path) -> None:
    project_dir = tmp_path
    relative_path = Path("target/contracts.duckdb")
    target = (project_dir / relative_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"")

    materialised = sqlfluff_runner.ensure_duckdb(project_dir, relative_path)

    assert materialised == target
    _assert_valid_duckdb(materialised)


def test_run_sqlfluff_uses_resolved_duckdb_path(monkeypatch, tmp_path: Path) -> None:
    project_dir = tmp_path
    relative_path = Path("target/contracts.duckdb")

    captured: dict[str, Any] = {}

    def fake_run(cmd, env, check):
        captured["cmd"] = cmd
        captured["env"] = env
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(sqlfluff_runner, "subprocess", SimpleNamespace(run=fake_run))

    exit_code = sqlfluff_runner.run_sqlfluff(project_dir, relative_path, ["--version"])

    assert exit_code == 0
    if sys.version_info >= (3, 14):
        # SQLFluff is skipped on Python 3.14+ due to dbt/mashumaro incompatibility.
        assert captured == {}
    else:
        expected_path = (project_dir / relative_path).resolve()
        assert captured["cmd"][:3] == ["sqlfluff", "lint", str(project_dir)]
        env = captured["env"]
        assert isinstance(env, dict)
        assert env["DBT_DUCKDB_PATH"] == expected_path.as_posix()
