from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import sync_type_stubs


def _write_manifest(target: Path, entries: list[dict[str, object]]) -> None:
    manifest = {"packages": entries}
    (target / sync_type_stubs.MANIFEST_FILENAME).write_text(
        json.dumps(manifest), encoding="utf-8"
    )


def test_verify_stubs_accepts_matching_manifest(tmp_path: Path) -> None:
    cache = tmp_path / "stubs"
    cache.mkdir()
    package = sync_type_stubs.StubPackage(name="example-stubs", version="1.2.3")
    _write_manifest(
        cache,
        [{"name": package.name, "version": package.version, "extras": []}],
    )
    (cache / f"{package.normalized_name}-{package.version}.dist-info").mkdir()

    sync_type_stubs.verify_stubs(target=cache, packages=[package])


def test_verify_stubs_detects_mismatch(tmp_path: Path) -> None:
    cache = tmp_path / "stubs"
    cache.mkdir()
    package = sync_type_stubs.StubPackage(name="example-stubs", version="1.2.3")
    _write_manifest(
        cache,
        [{"name": package.name, "version": "9.9.9", "extras": []}],
    )
    (cache / f"{package.normalized_name}-9.9.9.dist-info").mkdir()

    with pytest.raises(sync_type_stubs.StubSyncError):
        sync_type_stubs.verify_stubs(target=cache, packages=[package])
