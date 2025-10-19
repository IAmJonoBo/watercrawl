from __future__ import annotations

from pathlib import Path

import pytest

from scripts.dependency_matrix import (
    Issue,
    PackageFile,
    PackageInfo,
    Target,
    evaluate_package,
    has_compatible_wheel,
    load_targets,
    parse_package_files,
    python_tag_supports,
)


def test_parse_package_files_extracts_python_tags() -> None:
    raw_files = [
        {"file": "pkg-1.0.0-py3-none-any.whl"},
        {"file": "pkg-1.0.0-cp311-cp311-manylinux.whl"},
        {"file": "pkg-1.0.0.tar.gz"},
    ]
    files = parse_package_files(raw_files)
    assert files[0].python_tag == "py3"
    assert files[1].python_tag == "cp311"
    assert files[2].python_tag is None


def test_python_tag_supports_major_minor() -> None:
    target = Target(python_version="3.14", label="candidate")
    assert python_tag_supports("py3", target)
    assert python_tag_supports("py314", target)
    assert python_tag_supports("cp314", target)
    assert not python_tag_supports("cp311", target)


def test_has_compatible_wheel_detects_match() -> None:
    target = Target(python_version="3.14", label="candidate")
    package = PackageInfo(
        name="example",
        version="1.0.0",
        groups=("main",),
        python_spec=">=3.9",
        files=(
            PackageFile(filename="example-1.0.0-cp314-cp314-manylinux.whl", is_wheel=True, python_tag="cp314"),
        ),
    )
    assert has_compatible_wheel(package, target)


def test_evaluate_package_flags_spec_incompatibility() -> None:
    target = Target(python_version="3.14", label="candidate")
    package = PackageInfo(
        name="blocked",
        version="0.1.0",
        groups=("main",),
        python_spec=">=3.9,<3.14",
        files=(),
    )
    issue = evaluate_package(package, target)
    assert isinstance(issue, Issue)
    assert issue.reason == "python-spec"


def test_evaluate_package_flags_missing_wheel(tmp_path: Path) -> None:
    target = Target(python_version="3.14", label="candidate")
    package = PackageInfo(
        name="native-only",
        version="2.0.0",
        groups=("dev",),
        python_spec=">=3.13",
        files=(
            PackageFile(filename="native-only-2.0.0-cp313-cp313-manylinux.whl", is_wheel=True, python_tag="cp313"),
        ),
    )
    issue = evaluate_package(package, target)
    assert isinstance(issue, Issue)
    assert issue.reason == "missing-wheel"


def test_load_targets_parses_default_config(tmp_path: Path) -> None:
    config = tmp_path / "targets.toml"
    config.write_text(
        """
[[targets]]
python = "3.13"
label = "stable"
[[targets]]
python = "3.14"
label = "candidate"
require_wheels = false
"""
    )
    targets = load_targets(config)
    assert targets[0].python_version == "3.13"
    assert not targets[1].require_wheels


@pytest.mark.parametrize(
    "wheel_tag,expected",
    [
        ("py3", True),
        ("py314", True),
        ("cp314", True),
        ("cp311", False),
        (None, False),
    ],
)
def test_python_tag_support_matrix(wheel_tag: str | None, expected: bool) -> None:
    target = Target(python_version="3.14", label="candidate")
    assert python_tag_supports(wheel_tag, target) is expected
