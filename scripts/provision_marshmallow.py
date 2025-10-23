#!/usr/bin/env python3
"""Download Marshmallow wheel into repo vendor cache for offline runners.

Usage:
  python scripts/provision_marshmallow.py --version 3.26.1

The script invokes `python -m pip download marshmallow==<version> --no-deps -d <dest>`
so it works with whatever Python executable is used to run the script (use the
project virtualenv via `poetry run python` if you want downloads into the venv
cache).
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--version",
        required=False,
        default="3.26.1",
        help="Marshmallow version to download",
    )
    parser.add_argument(
        "--dest",
        required=False,
        default=str(Path(__file__).parent.parent / "tools" / "vendor" / "marshmallow"),
        help="Destination directory for downloaded wheels",
    )
    args = parser.parse_args()

    version = args.version
    dest = Path(args.dest) / version
    dest.mkdir(parents=True, exist_ok=True)

    print(f"Downloading marshmallow=={version} into {dest}")

    # Use the running Python interpreter's pip to download the wheel.
    cmd = [
        shutil.which("python") or "python",
        "-m",
        "pip",
        "download",
        f"marshmallow=={version}",
        "--no-deps",
        "-d",
        str(dest),
    ]
    print("Running:", " ".join(cmd))
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError as exc:
        print(f"pip download failed: {exc}")
        return 2

    print("Done. Wheels available in:")
    for p in sorted(dest.iterdir()):
        print(" -", p.name)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
