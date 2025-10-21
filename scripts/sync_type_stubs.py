"""Sync vendored type stubs so QA can run without network access.

This helper installs the configured stub packages into a repository-local
directory (default: ``stubs/third_party``) so tools such as mypy, Ruff, and the
problems reporter have deterministic access to third-party typings.  When
invoked without ``--sync`` the script only verifies that the cached stubs match
the desired lockfile versions, making it safe to run in offline environments.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess  # nosec B404 - controlled CLI invocation
import sys
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_CONFIG = Path("presets/type_stub_sync.toml")
DEFAULT_LOCK = Path("poetry.lock")
MANIFEST_FILENAME = "manifest.json"


@dataclass(frozen=True)
class StubPackage:
    """Represent a vendored stub package specification."""

    name: str
    version: str
    extras: tuple[str, ...] = ()

    @property
    def normalized_name(self) -> str:
        return self.name.replace("-", "_")

    @property
    def identifier(self) -> str:
        if self.extras:
            extras = "[" + ",".join(self.extras) + "]"
        else:
            extras = ""
        return f"{self.name}{extras}=={self.version}"


class StubSyncError(RuntimeError):
    """Raised when stub synchronisation fails."""


def load_lock_versions(lock_path: Path) -> dict[str, str]:
    """Return a mapping of package name to locked version."""

    try:
        data = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - CLI guard
        raise StubSyncError(f"poetry.lock not found at {lock_path}") from exc
    packages = data.get("package", [])
    versions: dict[str, str] = {}
    for entry in packages:
        name = entry.get("name")
        version = entry.get("version")
        if isinstance(name, str) and isinstance(version, str):
            versions[name] = version
    return versions


def _parse_package_entry(
    entry: dict[str, object], lock_versions: dict[str, str]
) -> StubPackage:
    raw_name = entry.get("name")
    if not isinstance(raw_name, str):
        raise StubSyncError("Each package entry must include a 'name' string.")
    extras_field = entry.get("extras")
    extras: tuple[str, ...]
    if isinstance(extras_field, list):
        extras = tuple(str(item) for item in extras_field)
    elif extras_field is None:
        extras = ()
    else:
        raise StubSyncError(
            f"Unsupported extras type for package {raw_name!r}: {type(extras_field).__name__}"
        )
    version_field = entry.get("version")
    if version_field is None:
        version = lock_versions.get(raw_name)
        if version is None:
            raise StubSyncError(
                f"Package {raw_name!r} not found in poetry.lock; specify 'version' explicitly."
            )
    elif isinstance(version_field, str):
        version = version_field
    else:  # pragma: no cover - defensive
        raise StubSyncError(
            f"Unsupported version type for package {raw_name!r}: {type(version_field).__name__}"
        )
    return StubPackage(name=raw_name, extras=extras, version=version)


def load_configuration(
    config_path: Path, lock_path: Path
) -> tuple[Path, list[StubPackage]]:
    """Load sync configuration and resolve package versions."""

    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - CLI guard
        raise StubSyncError(f"Configuration not found at {config_path}") from exc
    target_str = config.get("target", "stubs/third_party")
    if not isinstance(target_str, str):
        raise StubSyncError("Configuration field 'target' must be a string path.")
    target = Path(target_str)

    packages_raw = config.get("package")
    if not isinstance(packages_raw, list) or not packages_raw:
        raise StubSyncError("Configuration must define at least one [[package]] entry.")
    lock_versions = load_lock_versions(lock_path)
    packages: list[StubPackage] = []
    for entry in packages_raw:
        if not isinstance(entry, dict):
            raise StubSyncError("Each [[package]] entry must be a table.")
        packages.append(_parse_package_entry(entry, lock_versions))
    return target, packages


def _run_command(command: Sequence[str], *, cwd: Path | None = None) -> None:
    result = subprocess.run(command, cwd=cwd, check=False)  # nosec B603
    if result.returncode != 0:
        raise StubSyncError(
            f"Command {' '.join(command)} failed with exit code {result.returncode}"
        )


def _resolve_installer(preferred: str | None = None) -> list[str]:
    if preferred == "uv":
        return ["uv", "pip", "install"]
    if preferred == "pip":
        return [sys.executable, "-m", "pip", "install"]
    if shutil.which("uv"):
        return ["uv", "pip", "install"]
    return [sys.executable, "-m", "pip", "install"]


def _clean_target(target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)


def _prune_auxiliary_artifacts(target: Path) -> None:
    bin_dir = target / "bin"
    if bin_dir.exists():
        shutil.rmtree(bin_dir, ignore_errors=True)
    build_dir = target / "build"
    if build_dir.exists():
        shutil.rmtree(build_dir, ignore_errors=True)
    for pycache in target.rglob("__pycache__"):
        shutil.rmtree(pycache, ignore_errors=True)


def sync_stubs(
    *,
    target: Path,
    packages: Sequence[StubPackage],
    installer: str | None,
    refresh: bool,
) -> None:
    """Install the configured stub packages into the target directory."""

    if refresh:
        _clean_target(target)
    else:
        target.mkdir(parents=True, exist_ok=True)

    install_cmd = _resolve_installer(installer)
    full_command: list[str] = [
        *install_cmd,
        "--target",
        str(target),
        "--no-deps",
        "--upgrade",
        "--no-compile",
    ]
    full_command.extend(pkg.identifier for pkg in packages)
    print("Installing type stubs →", " ".join(full_command))
    _run_command(full_command)

    _prune_auxiliary_artifacts(target)
    write_manifest(target, packages, install_cmd[0])


def write_manifest(
    target: Path, packages: Sequence[StubPackage], installer: str
) -> None:
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "installer": installer,
        "packages": [
            {
                "name": pkg.name,
                "version": pkg.version,
                "extras": list(pkg.extras),
            }
            for pkg in packages
        ],
    }
    manifest_path = target / MANIFEST_FILENAME
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote manifest → {manifest_path}")


def _load_manifest(target: Path) -> dict[str, object]:
    manifest_path = target / MANIFEST_FILENAME
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StubSyncError(
            f"Stub manifest not found at {manifest_path}; run with --sync to populate the cache."
        ) from exc


def _expected_manifest(
    packages: Iterable[StubPackage],
) -> dict[str, tuple[str, tuple[str, ...]]]:
    return {pkg.name: (pkg.version, pkg.extras) for pkg in packages}


def verify_stubs(*, target: Path, packages: Sequence[StubPackage]) -> None:
    """Ensure the cached stubs match the desired versions."""

    manifest = _load_manifest(target)
    recorded = manifest.get("packages")
    if not isinstance(recorded, list):
        raise StubSyncError("Stub manifest missing 'packages' list.")
    recorded_map: dict[str, tuple[str, tuple[str, ...]]] = {}
    for entry in recorded:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        version = entry.get("version")
        extras = entry.get("extras") or []
        if not isinstance(name, str) or not isinstance(version, str):
            continue
        if not isinstance(extras, list):
            raise StubSyncError(
                f"Stub manifest entry for {name!r} has invalid extras payload."
            )
        recorded_map[name] = (version, tuple(str(item) for item in extras))
    expected = _expected_manifest(packages)
    if recorded_map != expected:
        missing = expected.keys() - recorded_map.keys()
        extra = recorded_map.keys() - expected.keys()
        mismatched = {
            name
            for name in expected.keys() & recorded_map.keys()
            if expected[name] != recorded_map[name]
        }
        details: list[str] = []
        if missing:
            details.append(f"missing entries: {', '.join(sorted(missing))}")
        if extra:
            details.append(f"unexpected entries: {', '.join(sorted(extra))}")
        if mismatched:
            details.append(f"version mismatch: {', '.join(sorted(mismatched))}")
        raise StubSyncError(
            "Stub manifest out of date. "
            + "; ".join(details)
            + ". Run with --sync to refresh."
        )

    dist_errors: list[str] = []
    for pkg in packages:
        expected_dist = f"{pkg.normalized_name}-{pkg.version}.dist-info"
        dist_path = target / expected_dist
        if not dist_path.exists():
            dist_errors.append(expected_dist)
    if dist_errors:
        joined = ", ".join(dist_errors)
        raise StubSyncError(
            f"Missing dist-info directories: {joined}. Run with --sync to repopulate the cache."
        )
    print(
        f"Verified {len(packages)} vendored stubs under {target} "
        "(manifest and dist-info directories are in sync)."
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to the stub sync configuration file.",
    )
    parser.add_argument(
        "--lockfile",
        type=Path,
        default=DEFAULT_LOCK,
        help="Path to poetry.lock used for version resolution.",
    )
    parser.add_argument(
        "--target",
        type=Path,
        help="Override the destination directory for vendored stubs.",
    )
    parser.add_argument(
        "--installer",
        choices=("uv", "pip", "auto"),
        default="auto",
        help="Installer to use when syncing stubs. Defaults to auto-detect.",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Install or refresh the vendored stubs before verification.",
    )
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Do not clear the target directory before syncing (append/update).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        target, packages = load_configuration(args.config, args.lockfile)
        if args.target:
            target = args.target
        installer = None if args.installer == "auto" else args.installer
        if args.sync:
            sync_stubs(
                target=target,
                packages=packages,
                installer=installer,
                refresh=not args.no_refresh,
            )
        verify_stubs(target=target, packages=packages)
    except StubSyncError as exc:
        print(f"[stub-sync] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
