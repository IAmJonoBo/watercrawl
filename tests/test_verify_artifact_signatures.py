from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.verify_artifact_signatures import SignaturePolicyError, verify


def _write_bundle(path: Path, identity: str) -> None:
    bundle = {
        "mediaType": "application/vnd.dev.sigstore.bundle+json;version=0.1",
        "verificationMaterial": {
            "content": {
                "certificate": {
                    "subjectAlternativeName": {"uri": identity},
                }
            }
        },
    }
    path.write_text(json.dumps(bundle), encoding="utf-8")


def test_verify_happy_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dist_dir = tmp_path / "dist"
    bundle_dir = tmp_path / "bundles"
    dist_dir.mkdir()
    bundle_dir.mkdir()
    artifact = dist_dir / "package-1.0.0-py3-none-any.whl"
    artifact.write_text("wheel", encoding="utf-8")
    identity = "https://github.com/example/workflow@ref"
    _write_bundle(bundle_dir / f"{artifact.name}.sigstore", identity)
    monkeypatch.setenv("GITHUB_WORKFLOW_REF", "example/workflow@ref")

    verify(dist_dir, bundle_dir)


def test_verify_missing_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dist_dir = tmp_path / "dist"
    bundle_dir = tmp_path / "bundles"
    dist_dir.mkdir()
    bundle_dir.mkdir()
    artifact = dist_dir / "package-1.0.0-py3-none-any.whl"
    artifact.write_text("wheel", encoding="utf-8")
    monkeypatch.setenv("GITHUB_WORKFLOW_REF", "example/workflow@ref")

    with pytest.raises(SignaturePolicyError):
        verify(dist_dir, bundle_dir)


def test_verify_identity_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dist_dir = tmp_path / "dist"
    bundle_dir = tmp_path / "bundles"
    dist_dir.mkdir()
    bundle_dir.mkdir()
    artifact = dist_dir / "package-1.0.0-py3-none-any.whl"
    artifact.write_text("wheel", encoding="utf-8")
    monkeypatch.setenv("GITHUB_WORKFLOW_REF", "example/workflow@ref")
    _write_bundle(
        bundle_dir / f"{artifact.name}.sigstore",
        "https://github.com/other/workflow@ref",
    )

    with pytest.raises(SignaturePolicyError):
        verify(dist_dir, bundle_dir)
