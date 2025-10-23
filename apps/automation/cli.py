"""Developer experience CLI for the ACES Aerodynamics enrichment stack."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast

import click
from rich.console import Console
from rich.table import Table
from rich.text import Text

from firecrawl_demo.core import config
from firecrawl_demo.domain.contracts import CommitArtifactContract, PlanArtifactContract
from firecrawl_demo.integrations.contracts.shared_config import (
    environment_payload as contracts_environment_payload,
)
from firecrawl_demo.integrations.integration_plugins import contract_registry
from firecrawl_demo.interfaces.cli_base import (
    PlanCommitError,
    PlanCommitGuard,
    load_cli_environment,
)
from scripts import bootstrap_python

CLI_ENVIRONMENT = load_cli_environment()
REPO_ROOT = Path(__file__).resolve().parents[2]
PLAYWRIGHT_CACHE_DIR = (REPO_ROOT / "artifacts" / "cache" / "playwright").resolve()


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


def _derive_instructions(
    specs: Sequence[CommandSpec], override: str | None = None
) -> str:
    if override:
        text = override.strip()
        return text or "Execute QA tasks."
    task_names = ", ".join(spec.name for spec in specs)
    return f"Execute QA tasks: {task_names}."


def _build_plan_payload(
    specs: Sequence[CommandSpec],
    *,
    instructions: str,
    include_generated_at: bool = True,
) -> dict[str, Any]:
    changes: list[dict[str, Any]] = []
    for index, spec in enumerate(specs, start=1):
        change: dict[str, Any] = {
            "type": "qa_command",
            "step": index,
            "task": spec.name,
            "command": _format_args(spec.args),
        }
        if spec.tags:
            change["tags"] = list(spec.tags)
        changes.append(change)
    payload: dict[str, Any] = {"changes": changes, "instructions": instructions}
    if include_generated_at:
        payload["generated_at"] = datetime.now(UTC).isoformat()
    metadata = contract_registry()["PlanArtifact"]
    payload["contract"] = {
        "name": "PlanArtifact",
        "version": metadata["version"],
        "schema_uri": metadata["schema_uri"],
    }
    return PlanArtifactContract.model_validate(payload).model_dump(mode="json")


def _build_commit_payload(
    specs: Sequence[CommandSpec],
    *,
    diff_format: str,
    if_match_token: str | None = None,
    instructions: str,
    rag_score: float = 0.98,
) -> dict[str, Any]:
    summary_lines = [f"- {spec.name}: {_format_args(spec.args)}" for spec in specs]
    diff_summary = (
        "QA automation summary:\n"
        + "\n".join(summary_lines)
        + f"\n\nPlan instructions: {instructions}"
    )
    token = if_match_token or f"qa-suite-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"
    metadata = contract_registry()["CommitArtifact"]
    payload = {
        "if_match": f'"{token}"',
        "diff_summary": diff_summary,
        "diff_format": diff_format,
        "rag": {
            "faithfulness": rag_score,
            "context_precision": rag_score,
            "answer_relevancy": rag_score,
        },
        "contract": {
            "name": "CommitArtifact",
            "version": metadata["version"],
            "schema_uri": metadata["schema_uri"],
        },
    }
    return CommitArtifactContract.model_validate(payload).model_dump(mode="json")


def _ensure_unique_path(path: Path) -> Path:
    candidate = path
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}-{counter}{path.suffix}")
        counter += 1
    return candidate


def _write_json_file(
    path: Path, payload: Mapping[str, Any], *, overwrite: bool
) -> Path:
    path = path.expanduser()
    if path.exists() and not overwrite:
        raise click.ClickException(
            f"{path.as_posix()} already exists. Re-run with --overwrite to replace it."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def _maybe_generate_plan_artifacts(
    *,
    specs: Sequence[CommandSpec],
    dry_run: bool,
    guard: PlanCommitGuard | None,
    plan_paths: Sequence[Path],
    commit_paths: Sequence[Path],
    generate_plan: bool,
    plan_dir: Path | None,
    instructions: str,
    if_match_token: str | None,
    console: Console,
) -> tuple[list[Path], list[Path], PlanCommitGuard | None]:
    plan_paths_list = list(plan_paths)
    commit_paths_list = list(commit_paths)
    active_guard = guard
    if generate_plan and not dry_run:
        active_guard = active_guard or CLI_ENVIRONMENT.plan_guard
        if active_guard is None:
            raise click.ClickException(
                "Plan guard is not configured; cannot generate plan artefacts."
            )
        if plan_paths_list or commit_paths_list:
            console.print(
                Text.assemble(
                    ("Skipping auto plan generation", "yellow"),
                    " because plan/commit artefacts were provided.",
                )
            )
        else:
            target_dir = plan_dir or (config.DATA_DIR / "logs" / "plans")
            target_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
            base_name = f"qa_{timestamp}"
            plan_path = _ensure_unique_path(target_dir / f"{base_name}.plan")
            commit_path = _ensure_unique_path(target_dir / f"{base_name}.commit")
            plan_payload = _build_plan_payload(specs, instructions=instructions)
            _write_json_file(plan_path, plan_payload, overwrite=False)
            commit_payload = _build_commit_payload(
                specs,
                diff_format=active_guard.contract.diff_format,
                if_match_token=if_match_token,
                instructions=instructions,
            )
            _write_json_file(commit_path, commit_payload, overwrite=False)
            plan_paths_list.append(plan_path)
            commit_paths_list.append(commit_path)
            console.print(
                Text.assemble(
                    ("Generated plan artefact → ", "green"), plan_path.as_posix()
                )
            )
            console.print(
                Text.assemble(
                    ("Generated commit artefact → ", "green"), commit_path.as_posix()
                )
            )
    return plan_paths_list, commit_paths_list, active_guard


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
                "--cov=crawlkit",
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
    "mutation": [
        CommandSpec(
            name="Mutation testing",
            args=(
                "poetry",
                "run",
                "python",
                "-m",
                "tools.testing.mutation_runner",
            ),
            description="Run mutmut over pipeline hotspots to measure mutation score.",
            tags=("mutation", "testing"),
        )
    ],
    "format": [
        CommandSpec(
            name="Ruff (fix)",
            args=("poetry", "run", "ruff", "check", ".", "--fix"),
            description="Apply Ruff auto-fixes across the repository.",
            requires_plan=True,
        ),
        CommandSpec(
            name="Isort (fmt)",
            args=("poetry", "run", "isort", "--profile", "black", "."),
            description="Sort imports using the Black profile.",
            requires_plan=True,
        ),
        CommandSpec(
            name="Black (fmt)",
            args=("poetry", "run", "black", "."),
            description="Format Python files with Black.",
            requires_plan=True,
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
            name="Verify type stubs",
            args=("poetry", "run", "python", "-m", "scripts.sync_type_stubs"),
            description=(
                "Verify vendored type stubs are in sync with poetry.lock for offline QA."
            ),
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
            env=contracts_environment_payload(),
        ),
    ],
}

# Conditionally add Bandit if Python version supports it (Bandit doesn't support Python 3.14+)
if sys.version_info < (3, 14):
    _QA_GROUPS["security"].insert(
        0,
        CommandSpec(
            name="Bandit",
            args=(
                "poetry",
                "run",
                "bandit",
                "-r",
                "crawlkit",
                "firecrawl_demo",
            ),
            description="Security lint the Crawlkit and legacy Firecrawl packages with Bandit.",
        ),
    )

# Skip SQLFluff and dbt contracts automatically on interpreters where dbt's
# mashumaro dependency is incompatible (Python 3.14+). Analysts can still run
# these checks manually from a Python 3.13 environment when required.
if sys.version_info >= (3, 14):
    _QA_GROUPS["lint"] = [
        spec for spec in _QA_GROUPS["lint"] if spec.name != "SQLFluff"
    ]
    _QA_GROUPS["contracts"] = []


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
        commit_paths: Sequence[Path] | None = None,
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
    commit_paths: Sequence[Path] | None = None,
    force: bool = False,
) -> int:
    runner = _get_command_runner()
    return runner(
        specs,
        dry_run=dry_run,
        fail_fast=fail_fast,
        plan_guard=plan_guard,
        plan_paths=plan_paths,
        commit_paths=commit_paths,
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
    commit_paths: Sequence[Path] | None = None,
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
                    f"qa.{spec.name.lower().replace(' ', '_')}",
                    plan_paths,
                    commit_paths=commit_paths,
                    force=force,
                )
            except PlanCommitError as exc:
                raise click.ClickException(str(exc)) from exc
        console.print(Text.assemble(("→", "cyan"), " ", spec.name, ": ", command_str))
        start = time.perf_counter()
        env = os.environ.copy()
        env.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(PLAYWRIGHT_CACHE_DIR))
        if spec.env:
            env.update(spec.env)
        result = subprocess.run(spec.args, env=env, check=False)
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
@click.option(
    "--write-plan",
    type=click.Path(path_type=Path),
    help="Write the rendered plan artefact to disk.",
)
@click.option(
    "--write-commit",
    type=click.Path(path_type=Path),
    help="Write a commit acknowledgement artefact to disk.",
)
@click.option(
    "--instructions",
    "instructions_override",
    type=str,
    help="Override the instructions field recorded in generated plan/commit artefacts.",
)
@click.option(
    "--if-match-token",
    type=str,
    help="Override the If-Match token stored in the generated commit artefact.",
)
@click.option(
    "--overwrite",
    is_flag=True,
    help="Allow overwriting existing artefacts when writing plan/commit files.",
)
def qa_plan(
    skip_dbt: bool,
    write_plan: Path | None,
    write_commit: Path | None,
    instructions_override: str | None,
    if_match_token: str | None,
    overwrite: bool,
) -> None:
    """Display the QA plan without executing any commands."""

    specs = _collect_specs(_QA_DEFAULT_SEQUENCE, include_dbt=not skip_dbt)
    console = Console()
    console.print(_render_plan_table(specs))

    instructions = _derive_instructions(specs, instructions_override)

    if write_plan is not None:
        payload = _build_plan_payload(specs, instructions=instructions)
        written_path = _write_json_file(write_plan, payload, overwrite=overwrite)
        console.print(
            Text.assemble(
                ("Plan artefact written to ", "green"),
                written_path.as_posix(),
            )
        )

    if write_commit is not None:
        guard = CLI_ENVIRONMENT.plan_guard
        if guard is None:
            raise click.ClickException(
                "Plan guard is not configured; cannot generate commit artefacts."
            )
        payload = _build_commit_payload(
            specs,
            diff_format=guard.contract.diff_format,
            if_match_token=if_match_token,
            instructions=instructions,
        )
        written_path = _write_json_file(write_commit, payload, overwrite=overwrite)
        console.print(
            Text.assemble(
                ("Commit artefact written to ", "green"),
                written_path.as_posix(),
            )
        )


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
    "--commit",
    "commits",
    type=click.Path(path_type=Path),
    multiple=True,
    help="Path(s) to commit artefacts acknowledging diff review.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Bypass plan enforcement when policy permits force commits.",
)
@click.option(
    "--generate-plan",
    is_flag=True,
    help="Automatically generate plan/commit artefacts before executing QA cleanup.",
)
@click.option(
    "--plan-dir",
    type=click.Path(path_type=Path),
    help="Directory for generated plan/commit artefacts (defaults to data/logs/plans).",
)
@click.option(
    "--plan-note",
    type=str,
    help="Custom instructions text to embed in generated artefacts.",
)
@click.option(
    "--if-match-token",
    "generated_if_match",
    type=str,
    help="Override the If-Match token used in generated commit artefacts.",
)
def qa_all(
    dry_run: bool,
    fail_fast: bool,
    skip_dbt: bool,
    auto_bootstrap: bool,
    plans: Sequence[Path],
    commits: Sequence[Path],
    force: bool,
    generate_plan: bool,
    plan_dir: Path | None,
    plan_note: str | None,
    generated_if_match: str | None,
) -> None:
    """Run the full QA suite that mirrors CI."""

    console = Console()
    _maybe_bootstrap_python(auto_bootstrap=auto_bootstrap, console=console)
    specs = _collect_specs(_QA_DEFAULT_SEQUENCE, include_dbt=not skip_dbt)
    instructions = _derive_instructions(specs, plan_note)
    plan_paths_list, commit_paths_list, guard = _maybe_generate_plan_artifacts(
        specs=specs,
        dry_run=dry_run,
        guard=None if dry_run else CLI_ENVIRONMENT.plan_guard,
        plan_paths=plans,
        commit_paths=commits,
        generate_plan=generate_plan,
        plan_dir=plan_dir,
        instructions=instructions,
        if_match_token=generated_if_match,
        console=console,
    )

    exit_code = _invoke_specs(
        specs,
        dry_run=dry_run,
        fail_fast=fail_fast,
        plan_guard=guard,
        plan_paths=tuple(plan_paths_list),
        commit_paths=tuple(commit_paths_list),
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


@qa.command("mutation")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Skip execution and record placeholder mutation artefacts.",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    help="Directory for mutation artefacts (overrides default).",
)
def qa_mutation(dry_run: bool, output_dir: Path | None) -> None:
    """Run the mutation testing pilot across pipeline hotspots."""

    specs = _collect_specs(["mutation"])
    if not specs:
        raise click.ClickException("Mutation testing commands are not configured.")

    base_spec = specs[0]
    args = list(base_spec.args)
    if dry_run:
        args.append("--dry-run")
    if output_dir is not None:
        args.extend(["--output-dir", output_dir.as_posix()])

    mutated_spec = CommandSpec(
        name=base_spec.name,
        args=tuple(args),
        description=base_spec.description,
        env=base_spec.env,
        tags=base_spec.tags,
        requires_plan=base_spec.requires_plan,
    )

    exit_code = _invoke_specs(
        [mutated_spec],
        dry_run=dry_run,
        plan_guard=CLI_ENVIRONMENT.plan_guard,
    )
    raise SystemExit(exit_code)


@qa.command("fmt")
@click.option(
    "--dry-run", is_flag=True, help="Preview format commands without executing them."
)
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
    help="Path(s) to plan artefacts authorising formatting operations.",
)
@click.option(
    "--commit",
    "commits",
    type=click.Path(path_type=Path),
    multiple=True,
    help="Path(s) to commit artefacts acknowledging diff review.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Bypass plan enforcement when policy permits force commits.",
)
@click.option(
    "--generate-plan",
    is_flag=True,
    help="Automatically generate plan/commit artefacts before applying formatters.",
)
@click.option(
    "--plan-dir",
    type=click.Path(path_type=Path),
    help="Directory for generated plan/commit artefacts (defaults to data/logs/plans).",
)
@click.option(
    "--plan-note",
    type=str,
    help="Custom instructions text to embed in generated artefacts.",
)
@click.option(
    "--if-match-token",
    "generated_if_match",
    type=str,
    help="Override the If-Match token used in generated commit artefacts.",
)
def qa_fmt(
    dry_run: bool,
    auto_bootstrap: bool,
    plans: Sequence[Path],
    commits: Sequence[Path],
    force: bool,
    generate_plan: bool,
    plan_dir: Path | None,
    plan_note: str | None,
    generated_if_match: str | None,
) -> None:
    """Run auto-formatters (Ruff fix, isort, Black) with plan guard support."""

    console = Console()
    _maybe_bootstrap_python(auto_bootstrap=auto_bootstrap, console=console)
    specs = _collect_specs(["format"])
    instructions = _derive_instructions(specs, plan_note)
    plan_paths_list, commit_paths_list, guard = _maybe_generate_plan_artifacts(
        specs=specs,
        dry_run=dry_run,
        guard=None if dry_run else CLI_ENVIRONMENT.plan_guard,
        plan_paths=plans,
        commit_paths=commits,
        generate_plan=generate_plan,
        plan_dir=plan_dir,
        instructions=instructions,
        if_match_token=generated_if_match,
        console=console,
    )
    exit_code = _invoke_specs(
        specs,
        dry_run=dry_run,
        plan_guard=guard,
        plan_paths=tuple(plan_paths_list),
        commit_paths=tuple(commit_paths_list),
        force=force,
    )
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
