"""Regression tests covering the published wheel footprint."""

from __future__ import annotations

import sys

import pytest

from scripts import validate_wheel


@pytest.fixture(scope="module")
def wheel_members() -> tuple[str, ...]:
    """Build the project wheel once per test module."""

    if sys.version_info < (3, 14):
        pytest.skip("wheel validation requires Python >= 3.14")

    return validate_wheel.collect_wheel_members()


def test_wheel_excludes_workspace_directories(wheel_members: tuple[str, ...]) -> None:
    """Ensure Poetry's exclude list keeps non-package directories out of the wheel."""

    offending = validate_wheel.find_offending_entries(wheel_members)

    assert (
        offending == set()
    ), f"unexpected files leaked into wheel: {sorted(offending)}"


def test_wheel_contains_expected_payload(wheel_members: tuple[str, ...]) -> None:
    """Assert the built wheel ships the intended package contents."""

    roots = {name.split("/", 1)[0] for name in wheel_members if "/" in name}
    allowed_roots = set(validate_wheel.ALLOWED_ROOT_NAMES)

    assert roots == allowed_roots, f"unexpected root entries detected: {sorted(roots)}"
    for package_dir in validate_wheel.PROJECT_METADATA.package_dirs:
        assert (
            f"{package_dir}/__init__.py" in wheel_members
        ), f"{package_dir} payload missing from wheel"
