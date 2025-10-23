#!/usr/bin/env python3
"""Ensure vendored dependencies are installed into the active Python environment.

This script uses tools/hooks/bootstrap.ensure_python_package to install
packages from tools/vendor if available, otherwise falls back to pip install.

Usage:
  poetry run python scripts/ensure_deps.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Import the helper from the repo
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.hooks import bootstrap


def main() -> int:
    # Hard-coded minimal list for now — add packages as needed.
    deps = [
        ("marshmallow", "3.26.1"),
        ("pytest-cov", "7.0.0"),
    ]

    for name, ver in deps:
        print(f"Ensuring {name}=={ver}")
        # If marshmallow is already importable and provides the symbol we
        # expect, skip installing a vendored wheel to avoid downgrades that
        # break the runtime API used by the codebase.
        if name == "marshmallow":
            try:
                import importlib

                m = importlib.import_module("marshmallow")
                # Code imports ChangedInMarshmallow4Warning; if present we are good
                if hasattr(m, "warnings") and hasattr(
                    m.warnings, "ChangedInMarshmallow4Warning"
                ):
                    print(
                        "Existing marshmallow provides ChangedInMarshmallow4Warning; skipping install"
                    )
                    continue
            except Exception:
                # Not installed or incompatible; proceed with installation
                pass

        bootstrap.ensure_python_package(
            name, ver, python_executable=sys.executable, allow_network=True
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
