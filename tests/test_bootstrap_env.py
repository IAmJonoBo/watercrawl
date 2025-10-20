from __future__ import annotations

from pathlib import Path

import pytest

from scripts import bootstrap_env


def test_discover_node_projects(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    docs_dir = tmp_path / "docs-starlight"
    docs_dir.mkdir()
    (docs_dir / "package.json").write_text("{}\n", encoding="utf-8")
    (docs_dir / "package-lock.json").write_text("{}\n", encoding="utf-8")

    projects = bootstrap_env.discover_node_projects(tmp_path)

    assert [p.relative_to(tmp_path) for p in projects] == [
        Path("package.json").parent,
        Path("docs-starlight"),
    ]


def test_build_node_command_prefers_ci_with_lock(tmp_path: Path) -> None:
    project = tmp_path / "docs"
    project.mkdir()
    (project / "package.json").write_text("{}\n", encoding="utf-8")
    (project / "package-lock.json").write_text("{}\n", encoding="utf-8")

    command = bootstrap_env.build_node_install_command(project)

    assert command == ("npm", "ci")


@pytest.mark.parametrize(
    "lock_file,expected",
    [
        ("pnpm-lock.yaml", ("pnpm", "install", "--frozen-lockfile")),
        ("yarn.lock", ("yarn", "install", "--frozen-lockfile")),
        (None, ("npm", "install")),
    ],
)
def test_build_node_command_variants(
    tmp_path: Path, lock_file: str | None, expected: tuple[str, ...]
) -> None:
    project = tmp_path / "web"
    project.mkdir()
    (project / "package.json").write_text("{}\n", encoding="utf-8")
    if lock_file:
        (project / lock_file).write_text("lock\n", encoding="utf-8")

    command = bootstrap_env.build_node_install_command(project)

    assert command == expected


def test_plan_includes_python_and_node(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    docs_dir = tmp_path / "docs-starlight"
    docs_dir.mkdir()
    (docs_dir / "package.json").write_text("{}\n", encoding="utf-8")

    plan = bootstrap_env.build_bootstrap_plan(
        repo_root=tmp_path,
        enable_python=True,
        enable_node=True,
        enable_docs=True,
    )

    step_descriptions = [step.description for step in plan]

    assert "Install Poetry environment" in step_descriptions
    assert any("docs-starlight" in step.description for step in plan)

