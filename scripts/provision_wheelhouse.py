#!/usr/bin/env python3
"""Create a wheelhouse (download wheels for locked requirements) for CI consumption.

This script:
 - exports requirements from poetry lockfile
 - downloads wheels into a wheelhouse directory
 - optionally archives the wheelhouse for upload

Usage:
  python scripts/provision_wheelhouse.py --output wheelhouse --python 3.13
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="wheelhouse")
    p.add_argument("--python", default="3.13")
    p.add_argument("--dev", action="store_true", help="Include dev dependencies")
    args = p.parse_args()

    out = Path(args.output)
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)

    # Export requirements from poetry
    export_cmd = [
        "poetry",
        "export",
        "--format",
        "requirements.txt",
        "-o",
        "wheel-reqs.txt",
    ]
    if args.dev:
        export_cmd.insert(-1, "--dev")
    subprocess.check_call(export_cmd)

    # Download wheels
    dl_cmd = ["python", "-m", "pip", "download", "-r", "wheel-reqs.txt", "-d", str(out)]
    subprocess.check_call(dl_cmd)

    print("Wheelhouse created at:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
