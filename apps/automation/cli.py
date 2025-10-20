"""Developer experience CLI for the ACES Aerodynamics enrichment stack."""

from __future__ import annotations

import shlex
import subprocess
import sys
import time
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

import click
from rich.console import Console
from rich.table import Table
from rich.text import Text

from firecrawl_demo.interfaces.cli_base import (
    PlanCommitError,
    PlanCommitGuard,
    load_cli_environment,
)
from scripts import bootstrap_python

CLI_ENVIRONMENT = load_cli_environment()


@dataclass(frozen=True)
class CommandSpec:
    """Describe a shell command that can be orchestrated by the DX CLI."""

    name: str
    args: Sequence[str]
    description: str
    env: Mapping[str, str] | None = None
    tags: tuple[str, ...] = ()
    requires_plan: bool = False


def _format_args(args: Sequence[str]) -> str:
    return shlex.join(args)


_MINIMUM_PYTHON_VERSION = (3, 14)


def _python_meets_minimum() -> bool:
    version = sys.version_info
    return (version.major, version.minor) >= _MINIMUM_PYTHON_VERSION


def _maybe_bootstrap_python(
    *, auto_bootstrap: bool, console: Console | None = None
) -> None:
    """Provision the minimum Python interpreter when required."""

    if not auto_bootstrap or _python_meets_minimum():
        return
    bootstrap_args = [
        "--version",
        bootstrap_python.DEFAULT_VERSION,
        "--install-uv",
        "--poetry",
    ]
    console = console or Console()
    console.print(
        Text.assemble(
            ("Provisioning", "cyan"),
            " Python ",
            bootstrap_python.DEFAULT_VERSION,
            " with uv for QA tasks…",
        )
    )
    result = bootstrap_python.main(bootstrap_args)
    if result != 0:
        raise click.ClickException(
            "Failed to provision Python " f"{bootstrap_python.DEFAULT_VERSION} via uv."
        )
    console.print(
        Text.assemble(
            ("Pinned", "green"),
            " Poetry to the uv-provisioned interpreter.",
        )
    )


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
            requires_plan=True,
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
    "dependencies": [
        CommandSpec(
            name="Sync dependencies",
            args=("poetry", "install", "--no-root"),
            description="Install all Poetry-managed dependencies for QA runs.",
            tags=("python", "poetry"),
        ),
        CommandSpec(
            name="Dependency survey",
            args=(
                "python",
                "-m",
                "scripts.dependency_matrix",
                "survey",
                "--config",
                "presets/dependency_targets.toml",
                "--output",
                "tools/dependency_matrix/report.json",
            ),
            description=(
                "Assess Python target compatibility for pinned dependencies and regenerate the wheel gap report."
            ),
            tags=("supply-chain", "python"),
        ),
        CommandSpec(
            name="Dependency guard",
            args=(
                "python",
                "-m",
                "scripts.dependency_matrix",
                "guard",
                "--config",
                "presets/dependency_targets.toml",
                "--blockers",
                "presets/dependency_blockers.toml",
                "--status-output",
                "tools/dependency_matrix/status.json",
            ),
            description=(
                "Fail fast when new wheel blockers appear and emit status metadata for Renovate and CI dashboards."
            ),
            tags=("supply-chain", "python"),
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
                "data_contracts/analytics",
                "--profiles-dir",
                "data_contracts/analytics",
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

# Conditionally add Bandit if Python version supports it (Bandit doesn't support Python 3.14+)
if sys.version_info < (3, 14):
    _QA_GROUPS["security"].insert(
        0,
        CommandSpec(
            name="Bandit",
            args=("poetry", "run", "bandit", "-r", "firecrawl_demo"),
            description="Security lint the core package with Bandit.",
        ),
    )


_QA_DEFAULT_SEQUENCE = (
    "cleanup",
    "dependencies",
    "tests",
    "lint",
    "typecheck",
    "security",
    "precommit",
    "build",
    "contracts",
)


class CommandRunner(Protocol):
    """Protocol for running a sequence of CommandSpec objects with QA orchestration."""

    def __call__(
        self,
        specs: Sequence[CommandSpec],
        *,
        dry_run: bool,
        fail_fast: bool = False,
        console: Console | None = None,
        plan_guard: PlanCommitGuard | None = None,
        plan_paths: Sequence[Path] | None = None,
        force: bool = False,
    ) -> int: ...

    def describe(self) -> str:
        """Return a description of the command runner implementation."""
        return "CommandRunner protocol"


_COMMAND_RUNNER_STACK: list[CommandRunner] = []


def _default_runner_description() -> str:
    return "subprocess command runner"


def _get_command_runner() -> CommandRunner:
    if _COMMAND_RUNNER_STACK:
        return _COMMAND_RUNNER_STACK[-1]
    return _DEFAULT_COMMAND_RUNNER


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
    specs: Sequence[CommandSpec],
    *,
    dry_run: bool,
    fail_fast: bool = False,
    plan_guard: PlanCommitGuard | None = None,
    plan_paths: Sequence[Path] | None = None,
    force: bool = False,
) -> int:
    runner = _get_command_runner()
    return runner(
        specs,
        dry_run=dry_run,
        fail_fast=fail_fast,
        plan_guard=plan_guard,
        plan_paths=plan_paths,
        force=force,
    )


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
    plan_guard: PlanCommitGuard | None = None,
    plan_paths: Sequence[Path] | None = None,
    force: bool = False,
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
        if spec.requires_plan and plan_guard is not None:
            try:
                plan_guard.require(
                    f"qa.{spec.name.lower().replace(' ', '_')}", plan_paths, force=force
                )
            except PlanCommitError as exc:
                raise click.ClickException(str(exc)) from exc
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


_run_command_specs.describe = _default_runner_description  # type: ignore[attr-defined]
_DEFAULT_COMMAND_RUNNER: CommandRunner = cast(CommandRunner, _run_command_specs)


@click.group(help="Developer tooling for local QA and release preparation.")
def cli() -> None:
    """Expose DX helpers that mirror the CI quality gates."""


@cli.group(help="Provision and manage developer toolchains.")
def toolchain() -> None:
    """Namespace for provisioning helper commands."""


@toolchain.command("python")
@click.option(
    "--version",
    default=bootstrap_python.DEFAULT_VERSION,
    show_default=True,
    help="Python version to install via the uv toolchain manager.",
)
@click.option(
    "--install-uv/--no-install-uv",
    default=False,
    help="Automatically install the uv CLI before provisioning the interpreter.",
)
@click.option(
    "--poetry/--no-poetry",
    default=True,
    help="Pin the Poetry virtualenv to the provisioned interpreter.",
)
def toolchain_python(version: str, install_uv: bool, poetry: bool) -> None:
    """Install a Python interpreter and optionally pin Poetry to it."""

    argv: list[str] = ["--version", version]
    if install_uv:
        argv.append("--install-uv")
    if poetry:
        argv.append("--poetry")
    raise SystemExit(bootstrap_python.main(argv))


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
@click.option(
    "--auto-bootstrap/--no-auto-bootstrap",
    default=True,
    help="Automatically provision Python 3.14 with uv when required.",
    show_default=True,
)
@click.option(
    "--plan",
    "plans",
    type=click.Path(path_type=Path),
    multiple=True,
    help="Path(s) to plan artefacts authorising cleanup operations.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Bypass plan enforcement when policy permits force commits.",
)
def qa_all(
    dry_run: bool,
    fail_fast: bool,
    skip_dbt: bool,
    auto_bootstrap: bool,
    plans: Sequence[Path],
    force: bool,
) -> None:
    """Run the full QA suite that mirrors CI."""

    console = Console()
    _maybe_bootstrap_python(auto_bootstrap=auto_bootstrap, console=console)
    specs = _collect_specs(_QA_DEFAULT_SEQUENCE, include_dbt=not skip_dbt)
    exit_code = _invoke_specs(
        specs,
        dry_run=dry_run,
        fail_fast=fail_fast,
        plan_guard=None if dry_run else CLI_ENVIRONMENT.plan_guard,
        plan_paths=plans,
        force=force,
    )
    raise SystemExit(exit_code)


@qa.command("dependencies")
@click.option(
    "--dry-run", is_flag=True, help="Preview dependency checks without executing them."
)
@click.option(
    "--auto-bootstrap/--no-auto-bootstrap",
    default=True,
    help="Automatically provision Python 3.14 with uv when required.",
    show_default=True,
)
def qa_dependencies(dry_run: bool, auto_bootstrap: bool) -> None:
    """Run dependency survey and guard checks."""

    _maybe_bootstrap_python(auto_bootstrap=auto_bootstrap)
    specs = _collect_specs(["dependencies"])
    exit_code = _invoke_specs(specs, dry_run=dry_run)
    raise SystemExit(exit_code)


@qa.command("tests")
@click.option(
    "--dry-run", is_flag=True, help="Preview the pytest command without executing it."
)
@click.option(
    "--auto-bootstrap/--no-auto-bootstrap",
    default=True,
    help="Automatically provision Python 3.14 with uv when required.",
    show_default=True,
)
def qa_tests(dry_run: bool, auto_bootstrap: bool) -> None:
    """Run the pytest suite with coverage enabled."""

    _maybe_bootstrap_python(auto_bootstrap=auto_bootstrap)
    specs = _collect_specs(["tests"])
    exit_code = _invoke_specs(specs, dry_run=dry_run)
    raise SystemExit(exit_code)


@qa.command("lint")
@click.option(
    "--dry-run", is_flag=True, help="Preview lint commands without executing them."
)
@click.option(
    "--auto-bootstrap/--no-auto-bootstrap",
    default=True,
    help="Automatically provision Python 3.14 with uv when required.",
    show_default=True,
)
def qa_lint(dry_run: bool, auto_bootstrap: bool) -> None:
    """Run Ruff, isort, and Black in check mode."""

    _maybe_bootstrap_python(auto_bootstrap=auto_bootstrap)
    specs = _collect_specs(["lint"])
    exit_code = _invoke_specs(specs, dry_run=dry_run)
    raise SystemExit(exit_code)


@qa.command("typecheck")
@click.option(
    "--dry-run", is_flag=True, help="Preview the mypy command without executing it."
)
@click.option(
    "--auto-bootstrap/--no-auto-bootstrap",
    default=True,
    help="Automatically provision Python 3.14 with uv when required.",
    show_default=True,
)
def qa_typecheck(dry_run: bool, auto_bootstrap: bool) -> None:
    """Execute the mypy static type checker."""

    _maybe_bootstrap_python(auto_bootstrap=auto_bootstrap)
    specs = _collect_specs(["typecheck"])
    exit_code = _invoke_specs(specs, dry_run=dry_run)
    raise SystemExit(exit_code)


@qa.command("security")
@click.option(
    "--dry-run", is_flag=True, help="Preview security checks without executing them."
)
@click.option("--skip-secrets", is_flag=True, help="Skip the dotenv linter check.")
@click.option(
    "--auto-bootstrap/--no-auto-bootstrap",
    default=True,
    help="Automatically provision Python 3.14 with uv when required.",
    show_default=True,
)
def qa_security(dry_run: bool, skip_secrets: bool, auto_bootstrap: bool) -> None:
    """Run security and secret-hygiene checks."""

    _maybe_bootstrap_python(auto_bootstrap=auto_bootstrap)
    specs = _collect_specs(["security"])
    if skip_secrets:
        specs = [spec for spec in specs if "secrets" not in spec.tags]
    exit_code = _invoke_specs(specs, dry_run=dry_run)
    raise SystemExit(exit_code)


@qa.command("build")
@click.option(
    "--dry-run", is_flag=True, help="Preview the build command without executing it."
)
@click.option(
    "--auto-bootstrap/--no-auto-bootstrap",
    default=True,
    help="Automatically provision Python 3.14 with uv when required.",
    show_default=True,
)
def qa_build(dry_run: bool, auto_bootstrap: bool) -> None:
    """Build wheel and sdist artefacts."""

    _maybe_bootstrap_python(auto_bootstrap=auto_bootstrap)
    specs = _collect_specs(["build"])
    exit_code = _invoke_specs(specs, dry_run=dry_run)
    raise SystemExit(exit_code)


@qa.command("contracts")
@click.option(
    "--dry-run", is_flag=True, help="Preview dbt contract execution without running it."
)
@click.option(
    "--auto-bootstrap/--no-auto-bootstrap",
    default=True,
    help="Automatically provision Python 3.14 with uv when required.",
    show_default=True,
)
def qa_contracts(dry_run: bool, auto_bootstrap: bool) -> None:
    """Execute dbt contracts for curated datasets."""

    _maybe_bootstrap_python(auto_bootstrap=auto_bootstrap)
    specs = _collect_specs(["contracts"])
    exit_code = _invoke_specs(specs, dry_run=dry_run)
    raise SystemExit(exit_code)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    cli()
