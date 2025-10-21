#!/usr/bin/env python3
"""Download and optionally bundle Node.js for the current host.

This script calls `tools.hooks.bootstrap.ensure_nodejs` to download and extract
the Node.js runtime into the user's cache and, when `--bundle` is passed,
copies the extracted tree into `tools/bin/` so it becomes available as a
bundled runtime for offline CI and local ephemeral runs.

Note: To create bundles for multiple platforms you must run this script on
each target platform/arch (or arrange cross-architecture tooling/VMs).
"""

from __future__ import annotations

import argparse
import shutil
import sys

from tools.hooks import bootstrap

# pathlib.Path not required here


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--version",
        "-v",
        default="v20.10.0",
        help="Node.js version to fetch (e.g. v20.10.0)",
    )
    parser.add_argument(
        "--bundle",
        action="store_true",
        help="Copy extracted Node into tools/bin as a bundled runtime",
    )
    args = parser.parse_args()

    try:
        node_path = bootstrap.ensure_nodejs(args.version)
    except bootstrap.BootstrapError as exc:
        print(f"Failed to ensure Node.js: {exc}", file=sys.stderr)
        return 2

    print(f"Node binary ready at: {node_path}")

    if args.bundle:
        # The extracted tree is usually <cache>/node-v<ver>-<platform>-<arch>/bin/node
        extracted_root = node_path.parent.parent
        if not extracted_root.exists():
            print(
                f"Expected extracted directory not found: {extracted_root}",
                file=sys.stderr,
            )
            return 3

        dest = bootstrap.BUNDLED_BIN_ROOT / extracted_root.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(extracted_root, dest)
        print(f"Bundled node runtime copied to: {dest}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
