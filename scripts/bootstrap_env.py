from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path


class BootstrapError(RuntimeError):
    """Raised when one of the bootstrap steps fails."""


@dataclass(frozen=True)
class BootstrapStep:
    """Represents an executable step in the environment bootstrap plan."""

    description: str
    command: tuple[str, ...]
    cwd: Path | None = None

    def render(self) -> str:
        location = f" (cwd: {self.cwd})" if self.cwd else ""
        cmd = " ".join(self.command)
        return f"{self.description}{location}: $ {cmd}"


def discover_node_projects(repo_root: Path) -> list[Path]:
    """Return known Node.js project directories within the repository."""

    candidates = [repo_root, repo_root / "docs-starlight"]
    projects: list[Path] = []
    for candidate in candidates:
        if (candidate / "package.json").exists():
            projects.append(candidate)
    projects.sort(key=lambda path: path.relative_to(repo_root).as_posix())
    return projects


def build_node_install_command(project_dir: Path) -> tuple[str, ...]:
    """Build the install command for a Node.js project based on its lock file."""

    if (project_dir / "package-lock.json").exists():
        return ("npm", "ci")
    if (project_dir / "pnpm-lock.yaml").exists():
        return ("pnpm", "install", "--frozen-lockfile")
    if (project_dir / "yarn.lock").exists():
        return ("yarn", "install", "--frozen-lockfile")
    return ("npm", "install")


def build_bootstrap_plan(
    *,
    repo_root: Path,
    enable_python: bool,
    enable_node: bool,
    enable_docs: bool,
) -> list[BootstrapStep]:
    """Assemble the ordered bootstrap steps for the repository."""

    steps: list[BootstrapStep] = []

    if enable_python:
        steps.append(
            BootstrapStep(
                description="Provision Python toolchain with uv",
                command=(
                    sys.executable,
                    "-m",
                    "scripts.bootstrap_python",
                    "--install-uv",
                    "--poetry",
                ),
            )
        )
        steps.append(
            BootstrapStep(
                description="Install Poetry environment",
                command=("poetry", "install", "--no-root", "--sync"),
            )
        )
        steps.append(
            BootstrapStep(
                description="Verify Poetry dependency graph",
                command=("poetry", "check"),
            )
        )
        steps.append(
            BootstrapStep(
                description="Install pre-commit hooks",
                command=("poetry", "run", "pre-commit", "install"),
            )
        )

    if enable_node:
        root_package = repo_root / "package.json"
        if root_package.exists():
            steps.append(
                BootstrapStep(
                    description="Install Node.js tooling for repository root",
                    command=build_node_install_command(repo_root),
                    cwd=repo_root,
                )
            )

    if enable_docs:
        docs_project = repo_root / "docs-starlight"
        if (docs_project / "package.json").exists():
            steps.append(
                BootstrapStep(
                    description="Install docs-starlight dependencies",
                    command=build_node_install_command(docs_project),
                    cwd=docs_project,
                )
            )

    return steps


def execute_plan(steps: Iterable[BootstrapStep], *, dry_run: bool) -> None:
    """Execute each bootstrap step sequentially."""

    for step in steps:
        print(step.render())
        if dry_run:
            continue
        result = subprocess.run(step.command, cwd=step.cwd, check=False)
        if result.returncode != 0:
            raise BootstrapError(
                f"Step '{step.description}' failed with exit code {result.returncode}."
            )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap the Python and Node.js tooling for the repository.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (defaults to the current working directory).",
    )
    parser.add_argument(
        "--no-python",
        action="store_false",
        dest="enable_python",
        help="Skip Python environment provisioning.",
    )
    parser.add_argument(
        "--no-node",
        action="store_false",
        dest="enable_node",
        help="Skip root Node.js tooling installation.",
    )
    parser.add_argument(
        "--no-docs",
        action="store_false",
        dest="enable_docs",
        help="Skip docs-starlight Node.js dependency installation.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the plan without executing commands.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    plan = build_bootstrap_plan(
        repo_root=args.repo_root,
        enable_python=args.enable_python,
        enable_node=args.enable_node,
        enable_docs=args.enable_docs,
    )
    try:
        execute_plan(plan, dry_run=args.dry_run)
    except BootstrapError as exc:  # pragma: no cover - CLI error handling
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
