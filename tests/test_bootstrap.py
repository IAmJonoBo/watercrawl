"""Tests for CLI bootstrap helpers used by pre-commit hooks."""

from __future__ import annotations

import io
import shutil
import tarfile
from pathlib import Path
from unittest import mock

import pytest

from tools.hooks import bootstrap


@pytest.fixture()
def fake_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point bootstrap helpers at a temporary cache directory."""

    monkeypatch.setattr(bootstrap, "CACHE_ROOT", tmp_path)
    return tmp_path


def make_tar_with_member(path: Path, *, member_name: str, content: bytes) -> None:
    """Create a gzipped tar archive containing a single member."""

    with tarfile.open(path, mode="w:gz") as archive:
        info = tarfile.TarInfo(member_name)
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))


def test_download_wraps_non_ssl_errors(fake_cache: Path) -> None:
    destination = fake_cache / "artifact.bin"
    error = Exception("network offline")

    with mock.patch("urllib.request.urlopen", side_effect=error):
        with pytest.raises(bootstrap.BootstrapError) as excinfo:
            bootstrap._download("https://example.invalid/tool", destination)

    assert "network offline" in str(excinfo.value)
    assert not destination.exists()


def test_actionlint_rejects_path_traversal(
    fake_cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path = fake_cache / "actionlint.tar.gz"
    make_tar_with_member(
        archive_path, member_name="../actionlint", content=b"echo nope"
    )

    def fake_download(url: str, destination: Path) -> None:
        shutil.copyfile(archive_path, destination)

    monkeypatch.setattr(bootstrap, "_download", fake_download)
    # Disable bundled binary lookup so we force download and extraction
    monkeypatch.setenv("WATERCRAWL_BOOTSTRAP_SKIP_BUNDLED", "1")

    with pytest.raises(bootstrap.BootstrapError) as excinfo:
        bootstrap.ensure_actionlint()

    assert "outside extraction directory" in str(excinfo.value)
    assert not any(fake_cache.rglob("actionlint"))
