#!/usr/bin/env python3
"""Test script to verify offline linter support."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tools.hooks.bootstrap import (  # noqa: E402
    BUNDLED_BIN_ROOT,
    ensure_actionlint,
    ensure_hadolint,
)


def test_bundled_binaries_exist():
    """Verify bundled binaries are present."""
    print("Testing bundled binary presence...")

    expected_binaries = [
        "hadolint-linux-x86_64",
        "hadolint-linux-arm64",
        "hadolint-macos-x86_64",
        "hadolint-macos-arm64",
        "actionlint-linux-x86_64",
        "actionlint-linux-arm64",
        "actionlint-macos-x86_64",
        "actionlint-macos-arm64",
    ]

    missing = []
    for binary_name in expected_binaries:
        binary_path = BUNDLED_BIN_ROOT / binary_name
        if not binary_path.exists():
            missing.append(binary_name)
        elif not os.access(binary_path, os.X_OK):
            print(f"  ✗ {binary_name} - not executable")
            missing.append(binary_name)
        else:
            print(f"  ✓ {binary_name} - present and executable")

    if missing:
        print(f"\n❌ Missing or non-executable binaries: {', '.join(missing)}")
        assert False, f"Missing binaries: {', '.join(missing)}"
    else:
        print("\n✅ All bundled binaries present and executable")


def test_bootstrap_functions():
    """Verify bootstrap functions use bundled binaries."""
    print("\nTesting bootstrap functions...")

    try:
        hadolint_path = ensure_hadolint()
        print(f"  hadolint path: {hadolint_path}")

        if (
            BUNDLED_BIN_ROOT in hadolint_path.parents
            or hadolint_path.parent == BUNDLED_BIN_ROOT
        ):
            print("  ✓ hadolint using bundled binary")
        else:
            print(f"  ✗ hadolint NOT using bundled binary (using {hadolint_path})")
            assert False, f"hadolint not using bundled binary: {hadolint_path}"

        actionlint_path = ensure_actionlint()
        print(f"  actionlint path: {actionlint_path}")

        if (
            BUNDLED_BIN_ROOT in actionlint_path.parents
            or actionlint_path.parent == BUNDLED_BIN_ROOT
        ):
            print("  ✓ actionlint using bundled binary")
        else:
            print(f"  ✗ actionlint NOT using bundled binary (using {actionlint_path})")
            assert False, f"actionlint not using bundled binary: {actionlint_path}"

        print("\n✅ Bootstrap functions correctly use bundled binaries")
    except Exception as exc:
        print(f"\n❌ Bootstrap functions failed: {exc}")
        raise


def test_binaries_work():
    """Verify binaries execute correctly."""
    print("\nTesting binary execution...")

    import subprocess

    try:
        hadolint_path = ensure_hadolint()
        result = subprocess.run(
            [str(hadolint_path), "--version"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"  ✓ hadolint works: {version}")
        else:
            print(f"  ✗ hadolint failed: {result.stderr}")
            assert False, f"hadolint execution failed: {result.stderr}"

        actionlint_path = ensure_actionlint()
        result = subprocess.run(
            [str(actionlint_path), "--version"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            version = result.stdout.strip().split("\n")[0]
            print(f"  ✓ actionlint works: {version}")
        else:
            print(f"  ✗ actionlint failed: {result.stderr}")
            assert False, f"actionlint execution failed: {result.stderr}"

        print("\n✅ All binaries execute correctly")
    except Exception as exc:
        print(f"\n❌ Binary execution failed: {exc}")
        raise


def main():
    """Run all tests."""
    print("=" * 60)
    print("Offline Linter Support Test Suite")
    print("=" * 60)

    failed = False
    try:
        test_bundled_binaries_exist()
        test_bootstrap_functions()
        test_binaries_work()
    except (AssertionError, Exception):
        failed = True

    print("\n" + "=" * 60)
    if not failed:
        print("✅ All tests passed!")
        print("=" * 60)
        return 0
    else:
        print("❌ Some tests failed")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
