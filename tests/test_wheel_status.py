from __future__ import annotations

from pathlib import Path

from scripts.wheel_status import Blocker, evaluate_package, generate_status

PYPI_TEMPLATE = {
    "info": {
        "version": "1.0.0",
        "requires_python": None,
    },
    "releases": {
        "1.0.0": [
            {"packagetype": "bdist_wheel", "python_version": "cp313"},
            {"packagetype": "bdist_wheel", "python_version": "py3"},
        ]
    },
}


def test_evaluate_package_detects_missing_wheels() -> None:
    blocker = Blocker(
        package="example", targets=("3.14",), owner=None, issue=None, notes=None
    )
    metadata = {
        "info": {"version": "1.0.0", "requires_python": ">=3.9"},
        "releases": {"1.0.0": [{"packagetype": "sdist", "python_version": "source"}]},
    }
    result = evaluate_package(blocker, metadata)
    assert result["targets"]["3.14"]["status"] == "missing-wheel"
    assert result["resolved"] is False


def test_generate_status_counts_unresolved(tmp_path: Path) -> None:
    blocker = Blocker(
        package="pkg", targets=("3.13", "3.14"), owner=None, issue=None, notes=None
    )

    def fetcher(_: str):
        return PYPI_TEMPLATE

    status = generate_status([blocker], fetcher)
    assert status["unresolved_count"] == 0
    package = status["packages"][0]
    assert package["targets"]["3.13"]["status"] == "ok"
    assert package["targets"]["3.14"]["status"] == "ok"
