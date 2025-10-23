#!/usr/bin/env python3
"""Download the latest wheelhouse artifact for this runner via the GitHub REST API.

This script expects the following environment variables set in CI:
- GITHUB_REPOSITORY (owner/repo)
- GITHUB_TOKEN
- RUNNER_OS (provided by Actions, e.g. Linux, macOS, Windows)
- PYTHON_VERSION (e.g. 3.13)

It looks for an artifact named `wheelhouse-<os>-py<python-version>` where `<os>` is one
of `ubuntu-latest`, `macos-latest`, or `windows-latest` (mapped from RUNNER_OS).
If found, downloads the artifact zip and extracts it into `./wheelhouse` safely.
Optionally pass `--seed-pip-cache` to copy the extracted contents into the offline pip
cache directory (defaults to `artifacts/cache/pip`).
If not found or on error, prints a message and exits 0 (best-effort).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from collections.abc import Sequence
from pathlib import Path


def _map_runner_os(runner_os: str) -> str:
    mapping = {
        "linux": "ubuntu-latest",
        "darwin": "macos-latest",
        "macos": "macos-latest",
        "windows": "windows-latest",
        "win32": "windows-latest",
    }
    key = runner_os.lower()
    return mapping.get(key, "ubuntu-latest")


def safe_extract_zip(zip_path: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as z:
        for info in z.infolist():
            target = dest / info.filename
            if not str(target.resolve()).startswith(str(dest.resolve())):
                raise RuntimeError(
                    "Zip archive contains path outside extraction directory"
                )
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, open(target, "wb") as dst:
                    dst.write(src.read())


def _stage_pip_cache(source: Path, destination: Path) -> None:
    """Copy extracted wheelhouse contents into the pip cache directory."""

    if not source.exists():
        raise RuntimeError(f"Wheelhouse directory {source} does not exist")

    destination.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        target = destination / entry.name
        if entry.is_dir():
            shutil.copytree(entry, target, dirs_exist_ok=True)
        else:
            shutil.copy2(entry, target)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wheelhouse-dir",
        type=Path,
        default=Path("wheelhouse"),
        help="Directory to extract the wheelhouse artifact (default: wheelhouse).",
    )
    parser.add_argument(
        "--seed-pip-cache",
        nargs="?",
        type=Path,
        const=Path("artifacts/cache/pip"),
        help=(
            "Copy the extracted wheelhouse into the pip cache directory. "
            "If no path is provided, defaults to artifacts/cache/pip."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    repo = os.getenv("GITHUB_REPOSITORY")
    token = os.getenv("GITHUB_TOKEN")
    runner_os = os.getenv("RUNNER_OS", os.getenv("RUNNERNAME", "linux"))
    py_ver = os.getenv("PYTHON_VERSION") or os.getenv("INPUT_PYTHON_VERSION")

    if not repo or not token or not py_ver:
        print(
            "GITHUB_REPOSITORY, GITHUB_TOKEN and PYTHON_VERSION must be set. Skipping artifact fetch."
        )
        return 0

    os_label = _map_runner_os(runner_os)
    artifact_name = f"wheelhouse-{os_label}-py{py_ver}"
    print(f"Looking for artifact: {artifact_name} in {repo}")

    api_url = f"https://api.github.com/repos/{repo}/actions/artifacts?per_page=100"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }
    req = urllib.request.Request(api_url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        print(f"Failed to list artifacts: {exc}")
        return 0

    artifacts = data.get("artifacts", [])
    matches = [a for a in artifacts if a.get("name") == artifact_name]
    if not matches:
        print("No matching artifact found. Skipping.")
        return 0

    # choose newest by created_at
    matches.sort(key=lambda a: a.get("created_at", ""), reverse=True)
    artifact = matches[0]
    artifact_id = artifact.get("id")
    if not artifact_id:
        print("Artifact did not contain an id. Skipping.")
        return 0

    download_url = (
        f"https://api.github.com/repos/{repo}/actions/artifacts/{artifact_id}/zip"
    )
    req = urllib.request.Request(download_url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            # save zip to temp
            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
                tmp_path = Path(tmp.name)
                tmp.write(resp.read())
    except urllib.error.HTTPError as exc:
        print(f"Failed to download artifact: {exc}")
        return 0

    try:
        out_dir = args.wheelhouse_dir
        print(f"Extracting artifact to {out_dir}")
        safe_extract_zip(tmp_path, out_dir)
    except Exception as exc:
        print(f"Failed to extract artifact: {exc}")
        return 0
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

    if args.seed_pip_cache is not None:
        try:
            seed_target = args.seed_pip_cache
            print(f"Seeding pip cache at {seed_target}")
            _stage_pip_cache(out_dir, seed_target)
        except Exception as exc:
            print(f"Failed to seed pip cache: {exc}")
            return 1

    print("Artifact downloaded and extracted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
