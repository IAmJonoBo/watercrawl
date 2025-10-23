#!/usr/bin/env python3
"""Mirror Python wheels for offline uv pip sync caches.

This helper orchestrates two passes of ``scripts/provision_wheelhouse.py`` so
that the cp314/cp315 wheel inventories live under
``artifacts/cache/pip/<python-tag>/`` and are also promoted to the cache root for
``uv pip sync``. Each run records metadata so CI and release gates can verify the
mirror remains fresh when the lockfile changes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import provision_wheelhouse

DEFAULT_PYTHON_VERSIONS = ("3.14", "3.15")
DEFAULT_CACHE_ROOT = Path("artifacts/cache/pip")
DEFAULT_METADATA_NAME = "mirror_state.json"


class MirrorError(RuntimeError):
    """Raised when the cache validation fails."""


def _python_tag(version: str) -> str:
    major, dot, minor = version.partition(".")
    if not dot or not minor.isdigit():  # pragma: no cover - defensive guard
        raise ValueError(f"Unsupported Python version format: {version}")
    return f"cp{major}{minor}"


def _lockfile_hash(lockfile: Path) -> str:
    digest = hashlib.sha256()
    digest.update(lockfile.read_bytes())
    return digest.hexdigest()


def _metadata_path(cache_root: Path, metadata_name: str) -> Path:
    return cache_root / metadata_name


def _write_metadata(
    *,
    cache_root: Path,
    metadata_name: str,
    python_versions: Iterable[str],
    wheel_counts: dict[str, int],
    blockers: set[str],
    lockfile_hash: str,
    requirements_hash: str,
    include_dev: bool,
) -> None:
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "python_versions": list(python_versions),
        "python_tags": {version: _python_tag(version) for version in python_versions},
        "wheel_counts": wheel_counts,
        "blockers_skipped": sorted(blockers),
        "poetry_lock_sha256": lockfile_hash,
        "requirements_txt_sha256": requirements_hash,
        "include_dev": include_dev,
    }
    metadata_path = _metadata_path(cache_root, metadata_name)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _validate_cache(
    *,
    cache_root: Path,
    metadata_name: str,
    python_versions: Iterable[str],
    lockfile: Path,
    blockers_path: Path | None,
    include_dev: bool,
) -> None:
    metadata_path = _metadata_path(cache_root, metadata_name)
    if not metadata_path.exists():
        raise MirrorError(
            f"Mirror metadata not found at {metadata_path.as_posix()}. "
            "Run scripts/mirror_wheels.py without --dry-run to seed the cache."
        )

    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    recorded_versions = set(data.get("python_versions", ()))
    expected_versions = set(python_versions)
    missing_versions = expected_versions - recorded_versions
    if missing_versions:
        raise MirrorError(
            "Mirror metadata missing required Python versions: "
            + ", ".join(sorted(missing_versions))
        )

    recorded_hash = data.get("poetry_lock_sha256")
    current_hash = _lockfile_hash(lockfile)
    if recorded_hash != current_hash:
        raise MirrorError(
            "Cached wheels are stale: poetry.lock hash mismatch. "
            "Re-run scripts/mirror_wheels.py to refresh the mirror."
        )

    requirements_hash = data.get("requirements_txt_sha256")
    req_file = provision_wheelhouse.REQUIREMENTS_FILE
    if req_file.exists():
        req_file.unlink()

    blocker_names = (
        provision_wheelhouse._load_blocker_names(blockers_path)
        if blockers_path is not None
        else set()
    )
    provision_wheelhouse.export_requirements(
        include_dev=include_dev, blocker_names=blocker_names
    )
    current_req_hash = _hash_file(req_file)
    req_file.unlink(missing_ok=True)

    recorded_include_dev = bool(data.get("include_dev", False))
    if recorded_include_dev != include_dev:
        raise MirrorError(
            "Mirror metadata was generated with a different dependency scope. "
            "Re-run scripts/mirror_wheels.py using the same flags."
        )
    if requirements_hash and requirements_hash != current_req_hash:
        raise MirrorError(
            "Cached wheels no longer match exported requirements. "
            "Re-run scripts/mirror_wheels.py to refresh."
        )

    wheel_counts = data.get("wheel_counts", {})
    for version in expected_versions:
        tag = _python_tag(version)
        wheel_dir = cache_root / tag
        if not wheel_dir.exists():
            raise MirrorError(
                f"Wheel directory missing for {tag}: {wheel_dir.as_posix()}"
            )
        wheels = list(wheel_dir.glob("*.whl"))
        if not wheels:
            raise MirrorError(
                f"No wheels mirrored for {tag} under {wheel_dir.as_posix()}"
            )
        recorded = (
            int(wheel_counts.get(tag, 0)) if isinstance(wheel_counts, dict) else 0
        )
        if recorded and recorded != len(wheels):
            raise MirrorError(
                f"Wheel count mismatch for {tag}: metadata={recorded}, found={len(wheels)}"
            )


def _mirror_wheels(
    *,
    python_versions: Iterable[str],
    cache_root: Path,
    blockers_path: Path | None,
    include_dev: bool,
    metadata_name: str,
) -> None:
    cache_root.mkdir(parents=True, exist_ok=True)
    blockers = (
        provision_wheelhouse._load_blocker_names(blockers_path)
        if blockers_path is not None
        else set()
    )
    provision_wheelhouse.export_requirements(
        include_dev=include_dev, blocker_names=blockers
    )
    requirements_hash = _hash_file(provision_wheelhouse.REQUIREMENTS_FILE)

    wheel_counts: dict[str, int] = {}
    for version in python_versions:
        tag = _python_tag(version)
        destination = cache_root / tag
        print(f"[mirror] Refreshing cache for Python {version} ({tag}) → {destination}")
        shutil.rmtree(destination, ignore_errors=True)
        destination.mkdir(parents=True, exist_ok=True)
        provision_wheelhouse.download_wheels(destination, version)
        wheel_count = 0
        for wheel_path in destination.glob("*.whl"):
            target = cache_root / wheel_path.name
            shutil.copy2(wheel_path, target)
            wheel_count += 1
        wheel_counts[tag] = wheel_count
        print(f"[mirror] {wheel_count} wheels mirrored for {tag}")

    lockfile = Path("poetry.lock")
    lock_hash = _lockfile_hash(lockfile)
    _write_metadata(
        cache_root=cache_root,
        metadata_name=metadata_name,
        python_versions=python_versions,
        wheel_counts=wheel_counts,
        blockers=blockers,
        lockfile_hash=lock_hash,
        requirements_hash=requirements_hash,
        include_dev=include_dev,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mirror Python wheels for offline uv pip sync consumption."
    )
    parser.add_argument(
        "--python",
        dest="python_versions",
        action="append",
        help="Python version(s) to mirror (defaults to 3.14 and 3.15).",
    )
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=DEFAULT_CACHE_ROOT,
        help="Wheel cache root directory (default: artifacts/cache/pip).",
    )
    parser.add_argument(
        "--metadata-name",
        default=DEFAULT_METADATA_NAME,
        help="Filename for the mirror metadata JSON (default: mirror_state.json).",
    )
    parser.add_argument(
        "--blockers",
        type=Path,
        default=Path("presets/dependency_blockers.toml"),
        help="Blocker configuration to reuse when exporting requirements.",
    )
    parser.add_argument(
        "--no-skip-blockers",
        dest="skip_blockers",
        action="store_false",
        help="Include packages listed in the blockers file.",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Include development dependencies when exporting requirements.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate cached wheels against the current lockfile without downloading.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    python_versions = tuple(args.python_versions or DEFAULT_PYTHON_VERSIONS)
    cache_root: Path = args.cache_root
    metadata_name: str = args.metadata_name
    blockers_path: Path | None = args.blockers if args.skip_blockers else None

    include_dev = bool(args.dev)

    try:
        if args.dry_run:
            _validate_cache(
                cache_root=cache_root,
                metadata_name=metadata_name,
                python_versions=python_versions,
                lockfile=Path("poetry.lock"),
                blockers_path=blockers_path,
                include_dev=include_dev,
            )
            print("[mirror] Cache validation successful; mirrored wheels are fresh.")
            return 0

        _mirror_wheels(
            python_versions=python_versions,
            cache_root=cache_root,
            blockers_path=blockers_path,
            include_dev=include_dev,
            metadata_name=metadata_name,
        )
        print("[mirror] Wheel mirror refreshed successfully.")
        return 0
    except MirrorError as exc:
        print(f"[mirror] Validation failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - surfaced to caller
        print(f"[mirror] Unexpected error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
