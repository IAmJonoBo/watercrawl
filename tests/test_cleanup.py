"""Tests for scripts.cleanup automation helpers."""

from __future__ import annotations

# Tests intentionally exercise git workflows to ensure CLI parity.
import subprocess  # nosec B404
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
    assert result.tracked == ()


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
    assert result.tracked == ()


def test_cleanup_rejects_paths_outside_project_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside"
    outside.mkdir()

    with pytest.raises(ValueError):
        cleanup.cleanup(
            project_root=tmp_path,
            include=("../outside",),
        )


def test_cleanup_skips_tracked_targets(tmp_path: Path) -> None:
    subprocess.run(("git", "init"), check=True, cwd=tmp_path)  # nosec B603
    subprocess.run(
        ("git", "-C", str(tmp_path), "config", "user.email", "test@example.com"),
        check=True,
    )  # nosec B603
    subprocess.run(
        ("git", "-C", str(tmp_path), "config", "user.name", "Test User"),
        check=True,
    )  # nosec B603
    tracked = tmp_path / "dist" / "keep.txt"
    tracked.parent.mkdir(parents=True)
    tracked.write_text("keep", encoding="utf-8")
    subprocess.run(
        ("git", "-C", str(tmp_path), "add", "dist/keep.txt"), check=True
    )  # nosec B603

    result = cleanup.cleanup(project_root=tmp_path)

    assert tracked.exists()
    assert tracked in result.tracked
    assert (tmp_path / "dist") in result.skipped
    assert (tmp_path / "dist") not in result.removed
