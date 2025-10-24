from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "watercrawl"


def _import_targets(module_path: Path) -> set[str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            targets.add(node.module)
    return targets


@pytest.mark.parametrize(
    "module_path",
    sorted((PACKAGE_ROOT / "core").rglob("*.py"))
    + sorted((PACKAGE_ROOT / "integrations").rglob("*.py")),
)
def test_core_and_integrations_do_not_import_interfaces(module_path: Path) -> None:
    imports = _import_targets(module_path)
    forbidden = {
        target for target in imports if target.startswith("watercrawl.interfaces")
    }
    assert (
        not forbidden
    ), f"{module_path} imports interface modules: {sorted(forbidden)}"
