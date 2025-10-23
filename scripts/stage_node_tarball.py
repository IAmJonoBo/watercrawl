#!/usr/bin/env python3
"""Download and stage signed Node.js tarballs for offline environments.

This script downloads official Node.js release tarballs and their checksums,
verifies integrity, and stages them under artifacts/cache/node/ for offline
bootstrap workflows.
"""

from __future__ import annotations

import argparse
import hashlib
import platform
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import NamedTuple


class NodeRelease(NamedTuple):
    """Represents a Node.js release with platform-specific download info."""

    version: str
    platform: str
    arch: str
    tarball_name: str
    tarball_url: str
    checksum_url: str


DEFAULT_NODE_VERSION = "v20.19.5"
CACHE_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "cache" / "node"


def get_platform_arch() -> tuple[str, str]:
    """Return the current platform and architecture in Node.js naming convention."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    platform_map = {
        "linux": "linux",
        "darwin": "darwin",
        "windows": "win",
    }
    node_platform = platform_map.get(system, system)

    arch_map = {
        "x86_64": "x64",
        "amd64": "x64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }
    node_arch = arch_map.get(machine, machine)

    return node_platform, node_arch


def build_release_info(version: str) -> NodeRelease:
    """Build download information for a specific Node.js version."""
    plat, arch = get_platform_arch()

    # Remove 'v' prefix if present
    clean_version = version.lstrip("v")
    version_with_v = f"v{clean_version}"

    tarball_name = f"node-{version_with_v}-{plat}-{arch}.tar.gz"
    base_url = f"https://nodejs.org/dist/{version_with_v}"
    tarball_url = f"{base_url}/{tarball_name}"
    checksum_url = f"{base_url}/SHASUMS256.txt"

    return NodeRelease(
        version=version_with_v,
        platform=plat,
        arch=arch,
        tarball_name=tarball_name,
        tarball_url=tarball_url,
        checksum_url=checksum_url,
    )


def download_file(url: str, destination: Path) -> None:
    """Download a file from URL to destination path."""
    print(f"Downloading {url} → {destination}")
    try:
        with urllib.request.urlopen(url) as response:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(response.read())
    except Exception as exc:
        raise RuntimeError(f"Failed to download {url}: {exc}") from exc


def verify_checksum(tarball_path: Path, checksum_file: Path) -> bool:
    """Verify the SHA256 checksum of a tarball against SHASUMS256.txt."""
    checksum_text = checksum_file.read_text(encoding="utf-8")
    tarball_name = tarball_path.name

    # Find the line with our tarball's checksum
    expected_checksum = None
    for line in checksum_text.splitlines():
        if tarball_name in line:
            parts = line.strip().split()
            if len(parts) >= 2:
                expected_checksum = parts[0]
                break

    if not expected_checksum:
        print(f"Warning: Could not find checksum for {tarball_name} in SHASUMS256.txt")
        return False

    # Calculate actual checksum
    sha256 = hashlib.sha256()
    with tarball_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            sha256.update(chunk)
    actual_checksum = sha256.hexdigest()

    if actual_checksum == expected_checksum:
        print(f"✓ Checksum verified: {actual_checksum}")
        return True

    print("✗ Checksum mismatch!")
    print(f"  Expected: {expected_checksum}")
    print(f"  Actual:   {actual_checksum}")
    return False


def verify_gpg_signature(checksum_file: Path) -> bool:
    """Verify GPG signature of SHASUMS256.txt (optional, requires gpg)."""
    sig_url = f"{checksum_file.parent / 'SHASUMS256.txt.sig'}"
    sig_file = checksum_file.with_suffix(".txt.sig")

    try:
        # Download signature file
        download_file(str(sig_url).replace(str(checksum_file.parent), checksum_file.parent.as_uri()), sig_file)

        # Verify with gpg
        result = subprocess.run(
            ["gpg", "--verify", str(sig_file), str(checksum_file)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            print("✓ GPG signature verified")
            return True
        print(f"✗ GPG signature verification failed: {result.stderr}")
        return False
    except FileNotFoundError:
        print("ℹ GPG not available; skipping signature verification")
        return False
    except Exception as exc:
        print(f"Warning: GPG verification failed: {exc}")
        return False


def stage_node_tarball(
    version: str = DEFAULT_NODE_VERSION,
    cache_dir: Path = CACHE_DIR,
    verify_sig: bool = False,
) -> Path:
    """Download, verify, and stage a Node.js tarball for offline use.

    Args:
        version: Node.js version to download (e.g., 'v20.19.5')
        cache_dir: Directory to store the cached tarball
        verify_sig: Whether to verify GPG signature (requires gpg)

    Returns:
        Path to the staged tarball

    Raises:
        RuntimeError: If download or verification fails
    """
    release = build_release_info(version)
    tarball_path = cache_dir / release.tarball_name
    checksum_path = cache_dir / "SHASUMS256.txt"

    # Check if tarball already exists
    if tarball_path.exists():
        print(f"Tarball already cached: {tarball_path}")
        if checksum_path.exists():
            if verify_checksum(tarball_path, checksum_path):
                print("✓ Using cached tarball (checksum valid)")
                return tarball_path
            print("Warning: Cached tarball checksum invalid; re-downloading")
        else:
            print("Warning: No checksum file found; re-downloading for verification")

    # Download tarball and checksum
    download_file(release.tarball_url, tarball_path)
    download_file(release.checksum_url, checksum_path)

    # Verify checksum
    if not verify_checksum(tarball_path, checksum_path):
        tarball_path.unlink(missing_ok=True)
        raise RuntimeError("Checksum verification failed")

    # Optionally verify GPG signature
    if verify_sig:
        verify_gpg_signature(checksum_path)

    print(f"✓ Node.js tarball staged: {tarball_path}")
    return tarball_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Download and stage Node.js tarballs for offline environments",
    )
    parser.add_argument(
        "--version",
        default=DEFAULT_NODE_VERSION,
        help=f"Node.js version to download (default: {DEFAULT_NODE_VERSION})",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=CACHE_DIR,
        help=f"Cache directory (default: {CACHE_DIR})",
    )
    parser.add_argument(
        "--verify-signature",
        action="store_true",
        help="Verify GPG signature (requires gpg in PATH)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    args = parse_args(argv)
    try:
        stage_node_tarball(
            version=args.version,
            cache_dir=args.cache_dir,
            verify_sig=args.verify_signature,
        )
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
