#!/usr/bin/env python3
"""Create a wheelhouse (download wheels for locked requirements).

This script:
 - ensures the Poetry export plugin is available
 - exports requirements from the Poetry lockfile
 - downloads wheels into a wheelhouse directory using a trusted CA bundle

Usage:
  python scripts/provision_wheelhouse.py --output wheelhouse --python 3.13
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

import certifi

EXPORT_PLUGIN = "poetry-plugin-export"
REQUIREMENTS_FILE = Path("wheel-reqs.txt")


def _collect_ca_paths() -> list[Path]:
    """Collect CA bundle paths from the environment plus certifi."""
    candidates = [
        os.environ.get("PIP_CERT"),
        os.environ.get("REQUESTS_CA_BUNDLE"),
        os.environ.get("SSL_CERT_FILE"),
        certifi.where(),
    ]
    resolved: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        try:
            if not path.exists():
                continue
        except OSError:
            continue
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        resolved.append(path)
    return resolved


def _merge_ca_bundle(paths: list[Path]) -> tuple[str, str | None]:
    """Merge multiple CA bundles into a temporary file if needed."""
    if not paths:
        return certifi.where(), None
    if len(paths) == 1:
        return str(paths[0]), None

    handle = tempfile.NamedTemporaryFile(delete=False, suffix="-ca.pem")
    try:
        with handle as merged:
            for ca_path in paths:
                data = ca_path.read_bytes()
                merged.write(data)
                if not data.endswith(b"\n"):
                    merged.write(b"\n")
        return handle.name, handle.name
    except Exception:
        Path(handle.name).unlink(missing_ok=True)
        raise


def run(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
    """Run a subprocess and surface readable errors."""
    print(f"[wheelhouse] Running: {' '.join(cmd)}")
    completed = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if completed.returncode != 0:
        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        if stdout:
            print(stdout)
        if stderr:
            print(stderr, file=sys.stderr)
        raise subprocess.CalledProcessError(
            completed.returncode, cmd, output=completed.stdout, stderr=completed.stderr
        )


def ensure_export_plugin() -> None:
    """Ensure `poetry export` is available (Poetry 2.x requires a plugin)."""
    print("[wheelhouse] Ensuring poetry export plugin is installed")
    check_cmd = ["poetry", "self", "show", "plugins"]
    result = subprocess.run(check_cmd, capture_output=True, text=True)
    if result.returncode == 0 and EXPORT_PLUGIN in result.stdout:
        return

    print(f"[wheelhouse] Installing {EXPORT_PLUGIN}")
    run(["poetry", "self", "add", EXPORT_PLUGIN])


def _load_blocker_names(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    data = tomllib.loads(path.read_text())
    blockers = data.get("blockers", [])
    names: set[str] = set()
    for entry in blockers:
        if isinstance(entry, dict):
            name = entry.get("package")
            if isinstance(name, str):
                names.add(name.lower())
    return names


def _filter_blockers(blocker_names: set[str]) -> None:
    if not blocker_names or not REQUIREMENTS_FILE.exists():
        return

    lines = REQUIREMENTS_FILE.read_text().splitlines()
    filtered: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            filtered.append(line)
            continue
        pkg = stripped.split(";", 1)[0].split("==", 1)[0].split("[", 1)[0].strip()
        if pkg.lower() in blocker_names:
            print(f"[wheelhouse] Skipping known blocker dependency: {pkg}")
            continue
        filtered.append(line)
    REQUIREMENTS_FILE.write_text("\n".join(filtered) + "\n")


def export_requirements(include_dev: bool, blocker_names: set[str]) -> None:
    ensure_export_plugin()

    if REQUIREMENTS_FILE.exists():
        REQUIREMENTS_FILE.unlink()

    export_cmd = [
        "poetry",
        "export",
        "--format",
        "requirements.txt",
        "--output",
        str(REQUIREMENTS_FILE),
        "--without-hashes",
    ]
    if include_dev:
        export_cmd.extend(["--with", "dev"])
    run(export_cmd)
    _filter_blockers(blocker_names)


def download_wheels(output_dir: Path, python_version: str) -> None:
    ca_paths = _collect_ca_paths()
    ca_bundle, cleanup_path = _merge_ca_bundle(ca_paths)
    env = os.environ.copy()
    env.update(
        {
            "PIP_CERT": ca_bundle,
            "REQUESTS_CA_BUNDLE": ca_bundle,
            "SSL_CERT_FILE": ca_bundle,
        }
    )

    download_cmd = [
        sys.executable,
        "-m",
        "pip",
        "download",
        "-r",
        str(REQUIREMENTS_FILE),
        "-d",
        str(output_dir),
        "--only-binary",
        ":all:",
        "--no-deps",
        "--python-version",
        python_version,
    ]
    try:
        run(download_cmd, env=env)
    finally:
        if cleanup_path:
            Path(cleanup_path).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="wheelhouse")
    parser.add_argument("--python", default="3.13")
    parser.add_argument("--dev", action="store_true", help="Include dev dependencies")
    parser.add_argument(
        "--blockers",
        type=Path,
        default=Path("presets/dependency_blockers.toml"),
        help="Path to dependency blockers TOML used to skip known missing wheels",
    )
    parser.add_argument(
        "--no-skip-blockers",
        dest="skip_blockers",
        action="store_false",
        help="Do not skip packages listed in the blockers file.",
    )
    parser.set_defaults(skip_blockers=True)
    args = parser.parse_args()

    blocker_names = _load_blocker_names(args.blockers) if args.skip_blockers else set()

    output_path = Path(args.output)
    shutil.rmtree(output_path, ignore_errors=True)
    output_path.mkdir(parents=True, exist_ok=True)

    export_requirements(include_dev=args.dev, blocker_names=blocker_names)
    download_wheels(output_path, args.python)

    print("Wheelhouse created at:", output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
