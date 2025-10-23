#!/usr/bin/env python3
"""Run autofix commands for linting and formatting tools."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence

# Available autofix tools and their commands
AUTOFIX_TOOLS = {
    "ruff": {
        "command": ["ruff", "check", ".", "--fix"],
        "with_poetry": ["poetry", "run", "ruff", "check", ".", "--fix"],
        "description": "Fix auto-fixable linting issues with ruff",
    },
    "black": {
        "command": ["black", "."],
        "with_poetry": ["poetry", "run", "black", "."],
        "description": "Format code with black",
    },
    "isort": {
        "command": ["isort", "."],
        "with_poetry": ["poetry", "run", "isort", "."],
        "description": "Sort imports with isort",
    },
    "biome": {
        "command": ["npx", "biome", "check", "--apply"],
        "with_poetry": None,
        "description": "Fix JavaScript/TypeScript issues with biome",
    },
    "trunk": {
        "command": ["trunk", "fmt"],
        "with_poetry": None,
        "description": "Format code with trunk",
    },
    "all": {
        "command": None,  # Special case, runs all tools
        "with_poetry": None,
        "description": "Run all available autofix tools",
    },
}


def check_tool_available(tool_name: str) -> bool:
    """Check if a tool is available in PATH."""
    try:
        result = subprocess.run(
            [tool_name, "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def run_autofix(tool: str, use_poetry: bool = False, dry_run: bool = False) -> int:
    """Run autofix command for a specific tool."""
    if tool not in AUTOFIX_TOOLS:
        print(f"Error: Unknown tool '{tool}'", file=sys.stderr)
        return 1

    config = AUTOFIX_TOOLS[tool]

    # Determine which command to use
    if use_poetry and config["with_poetry"]:
        cmd = config["with_poetry"]
    else:
        cmd = config["command"]

    if cmd is None:
        print(f"Error: No command configured for '{tool}'", file=sys.stderr)
        return 1

    # Check if the primary tool is available
    primary_tool = cmd[0] if not use_poetry else cmd[2]
    if not check_tool_available(primary_tool):
        print(f"Warning: Tool '{primary_tool}' not found in PATH", file=sys.stderr)
        if use_poetry:
            print(
                f"Hint: Run 'poetry install --no-root --with dev' first",
                file=sys.stderr,
            )
        return 1

    print(f"Running: {' '.join(cmd)}")

    if dry_run:
        print(f"[DRY RUN] Would execute: {' '.join(cmd)}")
        return 0

    try:
        result = subprocess.run(cmd, check=False)
        return result.returncode
    except Exception as exc:
        print(f"Error running {tool}: {exc}", file=sys.stderr)
        return 1


def run_all_autofixes(use_poetry: bool = False, dry_run: bool = False) -> int:
    """Run all available autofix tools in sequence."""
    tools_to_run = ["ruff", "black", "isort", "biome"]
    exit_code = 0

    for tool in tools_to_run:
        print(f"\n{'='*70}")
        print(f"Running autofix: {tool}")
        print(f"{'='*70}")
        code = run_autofix(tool, use_poetry=use_poetry, dry_run=dry_run)
        if code != 0:
            print(f"Warning: {tool} exited with code {code}")
            exit_code = code

    return exit_code


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run autofix commands for linting and formatting tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Available tools:
"""
        + "\n".join(
            f"  {name:10} - {config['description']}"
            for name, config in AUTOFIX_TOOLS.items()
        ),
    )
    parser.add_argument(
        "tool",
        nargs="?",
        default="all",
        choices=list(AUTOFIX_TOOLS.keys()),
        help="Tool to run autofix for (default: all)",
    )
    parser.add_argument(
        "--poetry",
        action="store_true",
        help="Use poetry run prefix for Python tools",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing them",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Main entry point."""
    args = parse_args(argv)

    if args.tool == "all":
        return run_all_autofixes(use_poetry=args.poetry, dry_run=args.dry_run)
    else:
        return run_autofix(args.tool, use_poetry=args.poetry, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
