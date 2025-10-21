"""Policy gate ensuring built artifacts carry Sigstore bundles."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BUNDLE_SUFFIX = ".sigstore"


class SignaturePolicyError(RuntimeError):
    """Raised when artifact signature policy is violated."""


def _collect_artifacts(dist_dir: Path) -> list[Path]:
    candidates = sorted(
        path for path in dist_dir.glob("*") if path.suffix in {".whl", ".gz", ".zip"}
    )
    if not candidates:
        raise SignaturePolicyError(f"No build artifacts found in {dist_dir}")
    return candidates


def _bundle_path(bundle_dir: Path, artifact: Path) -> Path:
    return bundle_dir / f"{artifact.name}{BUNDLE_SUFFIX}"


def _load_bundle(bundle_path: Path) -> dict:
    try:
        return json.loads(bundle_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SignaturePolicyError(f"Missing bundle: {bundle_path}") from exc
    except json.JSONDecodeError as exc:
        raise SignaturePolicyError(f"Invalid JSON bundle: {bundle_path}") from exc


def _extract_identity(bundle: dict) -> str | None:
    material = bundle.get("verificationMaterial") or {}
    content = material.get("content") or {}
    certificate = content.get("certificate") or {}
    san = certificate.get("subjectAlternativeName") or {}
    # Depending on sigstore-cli version, the URI may live under different keys.
    if isinstance(san, dict):
        for key in ("uri", "uniformResourceIdentifier"):
            value = san.get(key)
            if value:
                return str(value)
    return None


def _expected_identity() -> str | None:
    workflow_ref = os.getenv("GITHUB_WORKFLOW_REF")
    if not workflow_ref:
        return None
    return f"https://github.com/{workflow_ref}"


def verify(dist_dir: Path, bundle_dir: Path) -> None:
    artifacts = _collect_artifacts(dist_dir)
    if not bundle_dir.exists():
        raise SignaturePolicyError(
            f"Bundle directory {bundle_dir} does not exist; expected bundles for {len(artifacts)} artifacts."
        )
    expected_identity = _expected_identity()
    for artifact in artifacts:
        bundle_path = _bundle_path(bundle_dir, artifact)
        bundle = _load_bundle(bundle_path)
        media_type = bundle.get("mediaType")
        if not media_type or "sigstore.bundle" not in media_type:
            raise SignaturePolicyError(
                f"Bundle {bundle_path} missing sigstore mediaType metadata."
            )
        if expected_identity:
            identity = _extract_identity(bundle)
            if identity != expected_identity:
                raise SignaturePolicyError(
                    f"Bundle {bundle_path} identity mismatch. "
                    f"Expected {expected_identity}, found {identity or 'unknown'}."
                )


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(
            "Usage: python -m scripts.verify_artifact_signatures <dist_dir> <bundle_dir>",
            file=sys.stderr,
        )
        return 2
    dist_dir = Path(argv[1])
    bundle_dir = Path(argv[2])
    try:
        verify(dist_dir, bundle_dir)
    except SignaturePolicyError as exc:
        print(f"[signature-policy] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main(sys.argv))
