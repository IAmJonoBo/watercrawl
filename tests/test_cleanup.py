"""Tests for scripts.cleanup automation helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import cleanup


def _make_file(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("placeholder", encoding="utf-8")
    return path


def test_cleanup_removes_default_targets(tmp_path: Path) -> None:
    (tmp_path / ".pytest_cache" / "dummy").mkdir(parents=True)
    (tmp_path / ".mypy_cache" / "dir").mkdir(parents=True)
    (tmp_path / ".ruff_cache").mkdir()
    (tmp_path / "artifacts" / "lineage").mkdir(parents=True)
    (tmp_path / "data" / "contracts" / "snapshot").mkdir(parents=True)
    (tmp_path / "data" / "versioning" / "meta").mkdir(parents=True)
    (tmp_path / "dist").mkdir()
    _make_file(tmp_path / "coverage.xml")

    result = cleanup.cleanup(
        project_root=tmp_path,
        include=("coverage.xml",),
    )

    assert not (tmp_path / ".pytest_cache").exists()
    assert not (tmp_path / ".mypy_cache").exists()
    assert not (tmp_path / ".ruff_cache").exists()
    assert not (tmp_path / "artifacts").exists()
    assert not (tmp_path / "data" / "contracts").exists()
    assert not (tmp_path / "data" / "versioning").exists()
    assert not (tmp_path / "dist").exists()
    assert not (tmp_path / "coverage.xml").exists()
    assert result.removed  # ensure at least one removal occurred


def test_cleanup_dry_run_does_not_modify_files(tmp_path: Path) -> None:
    (tmp_path / "artifacts" / "lineage").mkdir(parents=True)
    target = _make_file(tmp_path / "custom.log")

    result = cleanup.cleanup(
        project_root=tmp_path,
        include=("custom.log",),
        dry_run=True,
    )

    assert target.exists()
    assert (tmp_path / "artifacts").exists()
    assert result.dry_run is True
    assert target in result.removed


def test_cleanup_rejects_paths_outside_project_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside"
    outside.mkdir()

    with pytest.raises(ValueError):
        cleanup.cleanup(
            project_root=tmp_path,
            include=("../outside",),
        )
