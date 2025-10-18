"""Developer experience CLI for the ACES Aerodynamics enrichment stack."""

from __future__ import annotations

import shlex
import subprocess
import time
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol

import click
from rich.console import Console
from rich.table import Table
from rich.text import Text


@dataclass(frozen=True)
class CommandSpec:
    """Describe a shell command that can be orchestrated by the DX CLI."""

    name: str
    args: Sequence[str]
    description: str
    env: Mapping[str, str] | None = None
    tags: tuple[str, ...] = ()


def _format_args(args: Sequence[str]) -> str:
    return shlex.join(args)


_QA_GROUPS: dict[str, list[CommandSpec]] = {
    "cleanup": [
        CommandSpec(
            name="Cleanup preview",
            args=("poetry", "run", "python", "-m", "scripts.cleanup", "--dry-run"),
            description="Show which cached artefacts will be removed before QA runs.",
        ),
        CommandSpec(
            name="Cleanup",
            args=("poetry", "run", "python", "-m", "scripts.cleanup"),
            description="Remove cached artefacts to avoid stale QA state.",
        ),
    ],
    "tests": [
        CommandSpec(
            name="Pytest",
            args=(
                "poetry",
                "run",
                "pytest",
                "--maxfail=1",
                "--disable-warnings",
                "--cov=firecrawl_demo",
                "--cov-report=term-missing",
            ),
            description="Execute the unit test suite with coverage reporting.",
        ),
    ],
    "lint": [
        CommandSpec(
            name="Ruff",
            args=("poetry", "run", "ruff", "check", "."),
            description="Static analysis and linting via Ruff.",
        ),
        CommandSpec(
            name="Isort",
            args=("poetry", "run", "isort", "--profile", "black", "--check-only", "."),
            description="Validate import ordering for reproducible diffs.",
        ),
        CommandSpec(
            name="Black",
            args=("poetry", "run", "black", "--check", "."),
            description="Ensure Black formatting rules remain satisfied.",
        ),
        CommandSpec(
            name="Yamllint",
            args=("poetry", "run", "yamllint", "--strict", "-c", ".yamllint.yaml", "."),
            description="Validate YAML manifests and dbt profiles.",
            tags=("yaml",),
        ),
        CommandSpec(
            name="SQLFluff",
            args=(
                "poetry",
                "run",
                "python",
                "-m",
                "tools.sql.sqlfluff_runner",
            ),
            description="Lint dbt models with SQLFluff (duckdb dialect) ensuring the DuckDB target exists.",
            tags=("sql", "dbt"),
        ),
        CommandSpec(
            name="Markdownlint",
            args=(
                "poetry",
                "run",
                "pre-commit",
                "run",
                "markdownlint-cli2",
                "--all-files",
            ),
            description="Enforce Markdown style for docs and README files.",
            tags=("docs",),
        ),
        CommandSpec(
            name="Hadolint",
            args=(
                "poetry",
                "run",
                "pre-commit",
                "run",
                "hadolint",
                "--all-files",
            ),
            description="Scan Dockerfiles for common container hygiene issues.",
            tags=("containers",),
        ),
        CommandSpec(
            name="Actionlint",
            args=(
                "poetry",
                "run",
                "pre-commit",
                "run",
                "actionlint",
                "--all-files",
            ),
            description="Lint GitHub workflow automation for logic and syntax errors.",
            tags=("ci",),
        ),
    ],
    "typecheck": [
        CommandSpec(
            name="Mypy",
            args=("poetry", "run", "mypy", "."),
            description="Run static type checks across the repository.",
        ),
    ],
    "security": [
        CommandSpec(
            name="Bandit",
            args=("poetry", "run", "bandit", "-r", "firecrawl_demo"),
            description="Security lint the core package with Bandit.",
        ),
        CommandSpec(
            name="Dotenv lint",
            args=("poetry", "run", "dotenv-linter", "lint", ".env", ".env.example"),
            description="Check environment files for malformed entries.",
            tags=("secrets",),
        ),
        CommandSpec(
            name="Safety",
            args=(
                "poetry",
                "run",
                "python",
                "-m",
                "tools.security.offline_safety",
                "--requirements",
                "requirements.txt",
                "--requirements",
                "requirements-dev.txt",
            ),
            description="Audit dependency manifests against the vendored Safety DB (offline-friendly).",
            tags=("supply-chain",),
        ),
    ],
    "precommit": [
        CommandSpec(
            name="Pre-commit",
            args=("poetry", "run", "pre-commit", "run", "--all-files"),
            description="Execute the configured pre-commit hooks locally.",
        ),
    ],
    "build": [
        CommandSpec(
            name="Poetry build",
            args=("poetry", "build"),
            description="Build wheel and sdist artefacts for release validation.",
        ),
    ],
    "contracts": [
        CommandSpec(
            name="dbt contracts",
            args=(
                "poetry",
                "run",
                "dbt",
                "build",
                "--project-dir",
                "analytics",
                "--profiles-dir",
                "analytics",
                "--target",
                "ci",
                "--select",
                "tag:contracts",
                "--vars",
                '{"curated_source_path": "data/sample.csv"}',
            ),
            description="Run dbt contracts aligned with CI expectations.",
            tags=("dbt",),
        ),
    ],
}

_QA_DEFAULT_SEQUENCE = (
    "cleanup",
    "tests",
    "lint",
    "typecheck",
    "security",
    "precommit",
    "build",
    "contracts",
)


class CommandRunner(Protocol):
    def __call__(
        self,
        specs: Sequence[CommandSpec],
        *,
        dry_run: bool,
        fail_fast: bool = False,
        console: Console | None = None,
    ) -> int: ...


_COMMAND_RUNNER_STACK: list[CommandRunner] = []


def _get_command_runner() -> CommandRunner:
    if _COMMAND_RUNNER_STACK:
        return _COMMAND_RUNNER_STACK[-1]
    return _run_command_specs


@contextmanager
def override_command_runner(runner: CommandRunner) -> Iterator[None]:
    """Temporarily override the QA command runner."""

    _COMMAND_RUNNER_STACK.append(runner)
    try:
        yield
    finally:
        _COMMAND_RUNNER_STACK.pop()


def _collect_specs(
    group_names: Iterable[str], *, include_dbt: bool = True
) -> list[CommandSpec]:
    specs: list[CommandSpec] = []
    for group_name in group_names:
        group = _QA_GROUPS.get(group_name, [])
        for spec in group:
            if not include_dbt and "dbt" in spec.tags:
                continue
            specs.append(spec)
    return specs


def _invoke_specs(
    specs: Sequence[CommandSpec], *, dry_run: bool, fail_fast: bool = False
) -> int:
    runner = _get_command_runner()
    return runner(specs, dry_run=dry_run, fail_fast=fail_fast)


def _render_plan_table(specs: Sequence[CommandSpec]) -> Table:
    table = Table(title="QA execution plan")
    table.add_column("Step", justify="right", style="cyan", no_wrap=True)
    table.add_column("Task", style="magenta")
    table.add_column("Command", style="white")
    table.add_column("Description", style="green")
    for index, spec in enumerate(specs, start=1):
        table.add_row(str(index), spec.name, _format_args(spec.args), spec.description)
    return table


def _run_command_specs(
    specs: Sequence[CommandSpec],
    *,
    dry_run: bool,
    fail_fast: bool = False,
    console: Console | None = None,
) -> int:
    console = console or Console()
    summary_table = Table(title="QA results" if not dry_run else "QA plan (dry-run)")
    summary_table.add_column("Task", style="magenta")
    summary_table.add_column("Command", style="white")
    summary_table.add_column("Status", style="cyan")
    summary_table.add_column("Duration", style="green", justify="right")

    exit_code = 0
    for spec in specs:
        command_str = _format_args(spec.args)
        if dry_run:
            console.print(
                Text.assemble(("DRY-RUN", "yellow"), " ", spec.name, ": ", command_str)
            )
            summary_table.add_row(
                spec.name, command_str, Text("skipped", style="yellow"), "-"
            )
            continue
        console.print(Text.assemble(("→", "cyan"), " ", spec.name, ": ", command_str))
        start = time.perf_counter()
        result = subprocess.run(spec.args, env=spec.env, check=False)
        duration = f"{time.perf_counter() - start:.1f}s"
        if result.returncode == 0:
            status = Text("passed", style="green")
        else:
            status = Text(f"failed ({result.returncode})", style="red")
            if exit_code == 0:
                exit_code = result.returncode
        summary_table.add_row(spec.name, command_str, status, duration)
        if result.returncode != 0 and fail_fast:
            break

    console.print()
    console.print(summary_table)
    return exit_code


@click.group(help="Developer tooling for local QA and release preparation.")
def cli() -> None:
    """Expose DX helpers that mirror the CI quality gates."""


@cli.group(help="Run the quality-assurance commands used in CI.")
def qa() -> None:
    """Namespace for QA convenience commands."""


@qa.command("plan")
@click.option(
    "--skip-dbt", is_flag=True, help="Omit dbt contract execution from the plan."
)
def qa_plan(skip_dbt: bool) -> None:
    """Display the QA plan without executing any commands."""

    specs = _collect_specs(_QA_DEFAULT_SEQUENCE, include_dbt=not skip_dbt)
    console = Console()
    console.print(_render_plan_table(specs))


@qa.command("all")
@click.option(
    "--dry-run", is_flag=True, help="Preview the commands without executing them."
)
@click.option("--fail-fast", is_flag=True, help="Stop after the first failure.")
@click.option("--skip-dbt", is_flag=True, help="Skip dbt contract execution.")
def qa_all(dry_run: bool, fail_fast: bool, skip_dbt: bool) -> None:
    """Run the full QA suite that mirrors CI."""

    specs = _collect_specs(_QA_DEFAULT_SEQUENCE, include_dbt=not skip_dbt)
    exit_code = _invoke_specs(
        specs,
        dry_run=dry_run,
        fail_fast=fail_fast,
    )
    raise SystemExit(exit_code)


@qa.command("tests")
@click.option(
    "--dry-run", is_flag=True, help="Preview the pytest command without executing it."
)
def qa_tests(dry_run: bool) -> None:
    """Run the pytest suite with coverage enabled."""

    specs = _collect_specs(["tests"])
    exit_code = _invoke_specs(specs, dry_run=dry_run)
    raise SystemExit(exit_code)


@qa.command("lint")
@click.option(
    "--dry-run", is_flag=True, help="Preview lint commands without executing them."
)
def qa_lint(dry_run: bool) -> None:
    """Run Ruff, isort, and Black in check mode."""

    specs = _collect_specs(["lint"])
    exit_code = _invoke_specs(specs, dry_run=dry_run)
    raise SystemExit(exit_code)


@qa.command("typecheck")
@click.option(
    "--dry-run", is_flag=True, help="Preview the mypy command without executing it."
)
def qa_typecheck(dry_run: bool) -> None:
    """Execute the mypy static type checker."""

    specs = _collect_specs(["typecheck"])
    exit_code = _invoke_specs(specs, dry_run=dry_run)
    raise SystemExit(exit_code)


@qa.command("security")
@click.option(
    "--dry-run", is_flag=True, help="Preview security checks without executing them."
)
@click.option("--skip-secrets", is_flag=True, help="Skip the dotenv linter check.")
def qa_security(dry_run: bool, skip_secrets: bool) -> None:
    """Run security and secret-hygiene checks."""

    specs = _collect_specs(["security"])
    if skip_secrets:
        specs = [spec for spec in specs if "secrets" not in spec.tags]
    exit_code = _invoke_specs(specs, dry_run=dry_run)
    raise SystemExit(exit_code)


@qa.command("build")
@click.option(
    "--dry-run", is_flag=True, help="Preview the build command without executing it."
)
def qa_build(dry_run: bool) -> None:
    """Build wheel and sdist artefacts."""

    specs = _collect_specs(["build"])
    exit_code = _invoke_specs(specs, dry_run=dry_run)
    raise SystemExit(exit_code)


@qa.command("contracts")
@click.option(
    "--dry-run", is_flag=True, help="Preview dbt contract execution without running it."
)
def qa_contracts(dry_run: bool) -> None:
    """Execute dbt contracts for curated datasets."""

    specs = _collect_specs(["contracts"])
    exit_code = _invoke_specs(specs, dry_run=dry_run)
    raise SystemExit(exit_code)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    cli()
