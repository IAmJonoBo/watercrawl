"""Discover and report the current development environment for ephemeral agents.

This script helps agents in ephemeral runners quickly understand what tools and
environments are available, and how to bootstrap the project.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def check_tool(tool_name: str) -> dict[str, Any]:
    """Check if a tool is available and get its version."""
    path = shutil.which(tool_name)
    result = {"name": tool_name, "available": path is not None, "path": path}

    if path:
        try:
            # Try common version flags
            for flag in ["--version", "-V", "version"]:
                proc = subprocess.run(
                    [tool_name, flag],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if proc.returncode == 0:
                    result["version"] = proc.stdout.strip()
                    break
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    return result


def discover_python_environment() -> dict[str, Any]:
    """Discover Python interpreter and virtual environment details."""
    in_venv = hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    )

    return {
        "version": sys.version,
        "executable": sys.executable,
        "prefix": sys.prefix,
        "in_venv": in_venv,
        "venv_path": os.environ.get("VIRTUAL_ENV"),
    }


def discover_project_structure(repo_root: Path) -> dict[str, Any]:
    """Discover project files and configuration."""
    return {
        "pyproject_toml": (repo_root / "pyproject.toml").exists(),
        "poetry_toml": (repo_root / "poetry.toml").exists(),
        "poetry_lock": (repo_root / "poetry.lock").exists(),
        "requirements_txt": (repo_root / "requirements.txt").exists(),
        "requirements_dev_txt": (repo_root / "requirements-dev.txt").exists(),
        "venv_dir": (repo_root / ".venv").exists(),
        "package_json": (repo_root / "package.json").exists(),
        "pnpm_lock": (repo_root / "pnpm-lock.yaml").exists(),
    }


def discover_bootstrap_tools(repo_root: Path) -> dict[str, Any]:
    """Discover bootstrap scripts and helpers."""
    scripts_dir = repo_root / "scripts"
    return {
        "bootstrap_env": (scripts_dir / "bootstrap_env.py").exists(),
        "bootstrap_python": (scripts_dir / "bootstrap_python.py").exists(),
        "bootstrap_node": (scripts_dir / "bootstrap_node.py").exists(),
        "collect_problems": (scripts_dir / "collect_problems.py").exists(),
    }


def get_bootstrap_recommendations(
    tools: dict[str, dict[str, Any]], project: dict[str, Any]
) -> list[str]:
    """Provide recommendations for bootstrapping the environment."""
    recommendations = []

    if not tools["poetry"]["available"]:
        recommendations.append(
            "Poetry is not installed. Install it with: pip install poetry"
        )
    elif not project["venv_dir"]:
        recommendations.append(
            "Poetry virtual environment not set up. Run: poetry install --no-root"
        )

    if not tools["uv"]["available"]:
        recommendations.append(
            "UV is not installed. Install it with: pip install uv "
            "or run: python -m scripts.bootstrap_python --install-uv"
        )

    if not tools["pnpm"]["available"] and project["package_json"]:
        recommendations.append(
            "pnpm is not installed. Enable with: corepack enable && "
            "corepack prepare pnpm@latest --activate"
        )

    if not recommendations:
        recommendations.append(
            "Environment appears ready. Run 'poetry install --no-root' "
            "to ensure all dependencies are installed."
        )

    return recommendations


def main() -> int:
    """Main entry point for environment discovery."""
    repo_root = Path.cwd()

    print("=" * 70)
    print("WATERCRAWL ENVIRONMENT DISCOVERY")
    print("=" * 70)
    print()

    # Python environment
    print("Python Environment:")
    print("-" * 70)
    python_env = discover_python_environment()
    print(f"  Version: {python_env['version'].split()[0]}")
    print(f"  Executable: {python_env['executable']}")
    print(f"  In virtualenv: {python_env['in_venv']}")
    if python_env["venv_path"]:
        print(f"  VIRTUAL_ENV: {python_env['venv_path']}")
    print()

    # Package managers
    print("Package Managers:")
    print("-" * 70)
    tools = {}
    for tool_name in ["pip", "poetry", "uv", "pipx", "pnpm", "npm", "node"]:
        tool_info = check_tool(tool_name)
        tools[tool_name] = tool_info
        status = "✓" if tool_info["available"] else "✗"
        version = tool_info.get("version", "").split("\n")[0]
        print(f"  {status} {tool_name:12s} {version}")
    print()

    # Project structure
    print("Project Structure:")
    print("-" * 70)
    project = discover_project_structure(repo_root)
    for key, exists in project.items():
        status = "✓" if exists else "✗"
        print(f"  {status} {key}")
    print()

    # Bootstrap tools
    print("Bootstrap Scripts:")
    print("-" * 70)
    bootstrap = discover_bootstrap_tools(repo_root)
    for key, exists in bootstrap.items():
        status = "✓" if exists else "✗"
        print(f"  {status} {key}")
    print()

    # Recommendations
    print("Recommendations:")
    print("-" * 70)
    recommendations = get_bootstrap_recommendations(tools, project)
    for idx, rec in enumerate(recommendations, 1):
        print(f"  {idx}. {rec}")
    print()

    # Quick start
    print("Quick Start:")
    print("-" * 70)
    print("  For a fresh environment, run:")
    print("    1. python -m scripts.bootstrap_env")
    print("    2. poetry install --no-root --with dev")
    print("    3. poetry run pytest -q  # Verify tests pass")
    print()
    print("  For agents, ensure access to:")
    print("    - poetry run <command>  # Run commands in Poetry venv")
    print("    - scripts/collect_problems.py  # Check quality gates")
    print("    - .venv/bin/python  # Direct venv access (after setup)")
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
