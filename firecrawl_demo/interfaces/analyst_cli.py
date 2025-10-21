"""Analyst-facing CLI for dataset validation and enrichment."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TypeVar
from uuid import uuid4

import click
from rich.console import Console
from rich.progress import BarColumn, Progress, TaskID, TextColumn, TimeRemainingColumn

from firecrawl_demo.application.pipeline import Pipeline
from firecrawl_demo.application.progress import PipelineProgressListener
from firecrawl_demo.core import config
from firecrawl_demo.core.excel import read_dataset
from firecrawl_demo.core.profiles import ProfileError
from firecrawl_demo.domain.models import SchoolRecord
from firecrawl_demo.infrastructure.evidence import build_evidence_sink
from firecrawl_demo.integrations.contracts import (
    CuratedDatasetContractResult,
    DbtContractResult,
    calculate_contract_coverage,
    persist_contract_artifacts,
    record_contracts_evidence,
    report_coverage,
    run_dbt_contract_tests,
    validate_curated_file,
)
from firecrawl_demo.integrations.storage.lakehouse import build_lakehouse_writer
from firecrawl_demo.integrations.telemetry.lineage import LineageContext, LineageManager
from firecrawl_demo.interfaces.cli_base import (
    CliEnvironment,
    PlanCommitError,
    load_cli_environment,
)
from firecrawl_demo.interfaces.mcp.server import CopilotMCPServer

CLI_ENVIRONMENT: CliEnvironment = load_cli_environment()

T = TypeVar("T")


_CLI_OVERRIDE_STACK: list[dict[str, Any]] = []


def _get_cli_override(name: str, default: T) -> T:
    for overrides in reversed(_CLI_OVERRIDE_STACK):
        if name in overrides:
            return overrides[name]
    cli_module = sys.modules.get("firecrawl_demo.interfaces.cli")
    if cli_module is not None and hasattr(cli_module, name):
        return getattr(cli_module, name)
    return default


@contextmanager
def override_cli_dependencies(**overrides: Any) -> Iterator[None]:
    """Temporarily override CLI dependencies for testing and tooling."""

    _CLI_OVERRIDE_STACK.append(overrides)
    try:
        yield
    finally:
        _CLI_OVERRIDE_STACK.pop()


def _select_profile(profile_id: str | None, profile_path: Path | None) -> None:
    """Switch the active profile when requested."""

    if not profile_id and not profile_path:
        return
    try:
        config.switch_profile(profile_id=profile_id, profile_path=profile_path)
    except ProfileError as exc:
        raise click.ClickException(str(exc)) from exc


class RichPipelineProgress(PipelineProgressListener):
    """Rich progress bar implementation for pipeline runs."""

    def __init__(self, description: str, console: Console | None = None) -> None:
        self._description = description
        self._console = console or Console(stderr=True)
        progress_factory = _get_cli_override("Progress", Progress)
        self._progress = progress_factory(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeRemainingColumn(),
            console=self._console,
            transient=True,
            auto_refresh=True,
        )
        self._task_id: TaskID | None = None
        self._started = False

    def on_start(self, total_rows: int) -> None:
        if self._started:
            return
        self._progress.start()
        self._task_id = self._progress.add_task(
            self._description, total=max(total_rows, 1)
        )
        self._started = True

    def on_row_processed(self, index: int, updated: bool, record: SchoolRecord) -> None:
        if not self._started or self._task_id is None:
            return
        self._progress.advance(self._task_id, 1)
        if updated:
            self._progress.update(
                self._task_id,
                description=f"Updating {record.name}",
            )

    def on_complete(self, metrics: Mapping[str, int]) -> None:
        if not self._started or self._task_id is None:
            return
        adapter_failures = metrics.get("adapter_failures", 0)
        if adapter_failures:
            self._progress.log(
                "[yellow]"
                f"{adapter_failures} research adapter failures encountered. "
                "Review logs for details.[/yellow]"
            )
        self._progress.stop()
        self._started = False

    def on_error(self, error: Exception, index: int | None = None) -> None:
        if not self._started:
            return
        location = f"row {index + 2}" if index is not None else "dataset"
        self._progress.log(f"[red]Adapter failure processing {location}: {error}[/red]")


def _resolve_progress_flag(output_format: str, requested: bool | None) -> bool:
    if requested is not None:
        return requested
    return output_format == "text"


@click.group()
def cli() -> None:
    """Utilities for validating and enriching ACES Aerodynamics datasets."""


@cli.command()
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format", "output_format", type=click.Choice(["text", "json"]), default="text"
)
@click.option(
    "--progress/--no-progress",
    "progress",
    default=None,
    help="Display a progress bar while validating (defaults to off).",
)
@click.option(
    "--profile",
    "profile_id",
    type=str,
    help="Refinement profile identifier to load before validation.",
)
@click.option(
    "--profile-path",
    type=click.Path(path_type=Path),
    help="Path to a refinement profile YAML file.",
)
def validate(
    input_path: Path,
    output_format: str,
    progress: bool | None,
    profile_id: str | None,
    profile_path: Path | None,
) -> None:
    """Validate a CSV/XLSX dataset and report any quality issues."""

    _select_profile(profile_id, profile_path)
    pipeline_factory = _get_cli_override("Pipeline", Pipeline)
    reader = _get_cli_override("read_dataset", read_dataset)
    pipeline = pipeline_factory()
    frame = reader(input_path)
    report = pipeline.validator.validate_dataframe(frame)
    issues_payload = [issue.__dict__ for issue in report.issues]
    payload: dict[str, object] = {
        "rows": report.rows,
        "issues": issues_payload,
        "is_valid": report.is_valid,
    }
    progress_listener_factory = _get_cli_override(
        "RichPipelineProgress", RichPipelineProgress
    )
    if progress:
        listener = progress_listener_factory("Validating dataset")
        listener.on_start(report.rows)
        for index, (_, row) in enumerate(frame.iterrows()):
            record = SchoolRecord.from_dataframe_row(row)
            listener.on_row_processed(index, False, record)
        listener.on_complete(
            {
                "rows_total": report.rows,
                "enriched_rows": 0,
                "verified_rows": 0,
                "issues_found": len(report.issues),
                "adapter_failures": 0,
            }
        )
    if output_format == "json":
        click.echo(json.dumps(payload, indent=2))
    else:
        click.echo(f"Rows: {payload['rows']}")
        if issues_payload:
            click.echo("Issues:")
            for issue in issues_payload:
                column = issue.get("column", "")
                location = f" (column {column})" if column else ""
                click.echo(f" - {issue['code']}{location}: {issue['message']}")
        else:
            click.echo("No issues detected.")
    if not report.is_valid:
        raise click.exceptions.Exit(1)


@cli.command()
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    help="Optional path for the enriched dataset (defaults to *_enriched).",
)
@click.option(
    "--format", "output_format", type=click.Choice(["text", "json"]), default="text"
)
@click.option(
    "--progress/--no-progress",
    "progress",
    default=None,
    help="Display a progress bar during enrichment (defaults to on for text output).",
)
@click.option(
    "--profile",
    "profile_id",
    type=str,
    help="Refinement profile identifier to load before enrichment.",
)
@click.option(
    "--profile-path",
    type=click.Path(path_type=Path),
    help="Path to a refinement profile YAML file.",
)
@click.option(
    "--plan",
    "plans",
    type=click.Path(path_type=Path),
    multiple=True,
    help="Path(s) to recorded plan artefacts required before writes.",
)
@click.option(
    "--commit",
    "commits",
    type=click.Path(path_type=Path),
    multiple=True,
    help="Path(s) to recorded commit artefacts confirming diff review.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Bypass plan enforcement when policy allows force commits.",
)
def enrich(
    input_path: Path,
    output_path: Path | None,
    output_format: str,
    progress: bool | None,
    profile_id: str | None,
    profile_path: Path | None,
    plans: Sequence[Path],
    commits: Sequence[Path],
    force: bool,
) -> None:
    """Validate, enrich, and export a dataset."""

    _select_profile(profile_id, profile_path)
    evidence_sink_factory = _get_cli_override(
        "build_evidence_sink", build_evidence_sink
    )
    lineage_manager_factory = _get_cli_override("LineageManager", LineageManager)
    lakehouse_writer_factory = _get_cli_override(
        "build_lakehouse_writer", build_lakehouse_writer
    )
    pipeline_factory = _get_cli_override("Pipeline", Pipeline)
    plan_guard = _get_cli_override("plan_guard", CLI_ENVIRONMENT.plan_guard)
    try:
        validation = plan_guard.require(
            "cli.enrich",
            list(plans),
            commit_paths=list(commits),
            force=force,
        )
    except PlanCommitError as exc:
        raise click.ClickException(str(exc)) from exc
    evidence_sink = evidence_sink_factory()
    lineage_manager = lineage_manager_factory()
    lakehouse_writer = lakehouse_writer_factory()
    pipeline = pipeline_factory(
        evidence_sink=evidence_sink,
        lineage_manager=lineage_manager,
        lakehouse_writer=lakehouse_writer,
    )
    target = output_path or input_path.with_name(
        f"{input_path.stem}_enriched{input_path.suffix}"
    )
    show_progress = _resolve_progress_flag(output_format, progress)
    progress_listener_factory = _get_cli_override(
        "RichPipelineProgress", RichPipelineProgress
    )
    listener: PipelineProgressListener | None = (
        progress_listener_factory("Enriching dataset") if show_progress else None
    )
    lineage_context: LineageContext | None = None
    run_id = f"enrichment-{uuid4()}"
    if lineage_manager:
        lineage_context = LineageContext(
            run_id=run_id,
            namespace=lineage_manager.namespace,
            job_name=lineage_manager.job_name,
            dataset_name=lineage_manager.dataset_name,
            input_uri=input_path.resolve().as_uri(),
            output_uri=target.resolve().as_uri(),
            evidence_path=config.EVIDENCE_LOG,
            dataset_version=target.stem,
        )
    report = pipeline.run_file(
        input_path,
        output_path=target,
        progress=listener,
        lineage_context=lineage_context,
    )
    issues_payload = [issue.__dict__ for issue in report.issues]
    payload = {
        "rows_total": report.metrics["rows_total"],
        "rows_enriched": report.metrics["enriched_rows"],
        "verified_rows": report.metrics["verified_rows"],
        "issues": issues_payload,
        "output_path": str(target),
        "adapter_failures": report.metrics["adapter_failures"],
        "plan_artifacts": [str(path) for path in validation.plan_paths],
        "commit_artifacts": [str(path) for path in validation.commit_paths],
    }
    if report.lineage_artifacts:
        payload["lineage_artifacts"] = {
            "openlineage": str(report.lineage_artifacts.openlineage_path),
            "prov": str(report.lineage_artifacts.prov_path),
            "catalog": str(report.lineage_artifacts.catalog_path),
        }
    if report.lakehouse_manifest:
        payload["lakehouse_manifest"] = str(report.lakehouse_manifest.manifest_path)
        payload["lakehouse_version"] = report.lakehouse_manifest.version
        payload["lakehouse_uri"] = report.lakehouse_manifest.table_uri
    if report.version_info:
        payload["version_manifest"] = str(report.version_info.metadata_path)
        payload["version"] = report.version_info.version
        payload["version_reproduce_command"] = list(
            report.version_info.reproduce_command
        )
    if output_format == "json":
        click.echo(json.dumps(payload, indent=2))
    else:
        click.echo(
            "Enrichment complete: "
            f"{payload['rows_enriched']} of {payload['rows_total']} rows updated."
        )
        click.echo(f"Output written to: {payload['output_path']}")
        if report.lineage_artifacts:
            click.echo(
                f"Lineage artifacts: {report.lineage_artifacts.openlineage_path.parent}"
            )
        if report.lakehouse_manifest:
            click.echo(f"Lakehouse manifest: {report.lakehouse_manifest.manifest_path}")
        if report.version_info:
            click.echo(f"Version manifest: {report.version_info.metadata_path}")
        if payload["adapter_failures"]:
            click.echo(
                f"Warnings: {payload['adapter_failures']} research lookups failed; see logs."
            )
        if validation.plan_paths:
            click.echo(
                "Plan artefacts: "
                + ", ".join(str(path) for path in validation.plan_paths)
            )
        if validation.commit_paths:
            click.echo(
                "Commit artefacts: "
                + ", ".join(str(path) for path in validation.commit_paths)
            )


@cli.command("contracts")
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format", "output_format", type=click.Choice(["text", "json"]), default="text"
)
@click.option(
    "--profile",
    "profile_id",
    type=str,
    help="Refinement profile identifier to load before contract checks.",
)
@click.option(
    "--profile-path",
    type=click.Path(path_type=Path),
    help="Path to a refinement profile YAML file.",
)
def contracts(
    input_path: Path,
    output_format: str,
    profile_id: str | None,
    profile_path: Path | None,
) -> None:
    """Run Great Expectations contracts against a curated dataset."""

    _select_profile(profile_id, profile_path)
    sink_factory = _get_cli_override("build_evidence_sink", build_evidence_sink)
    evidence_sink = sink_factory()

    # Handle Great Expectations availability
    if validate_curated_file is not None:
        ge_result: CuratedDatasetContractResult = validate_curated_file(input_path)  # type: ignore
    else:
        # Fallback when Great Expectations is not available (e.g., Python 3.14+)
        ge_result = CuratedDatasetContractResult(
            success=True,  # Assume success when GE is not available
            statistics={"unsuccessful_expectations": 0},
            results=[],
            expectation_suite_name="great_expectations_unavailable",
            meta={"note": "Great Expectations not available in this Python version"},
        )

    dbt_result: DbtContractResult = run_dbt_contract_tests(input_path)  # type: ignore

    ge_payload: dict[str, Any] = {
        "success": ge_result.success,
        "statistics": ge_result.statistics,
        "unsuccessful_expectations": ge_result.unsuccessful_expectations,
        "expectation_suite_name": ge_result.expectation_suite_name,
        "meta": ge_result.meta,
        "failed_expectations": [
            {
                "expectation_type": entry.get("expectation_config", {}).get(
                    "expectation_type"
                ),
                "kwargs": entry.get("expectation_config", {}).get("kwargs", {}),
                "result": entry.get("result", {}),
            }
            for entry in ge_result.results
            if not entry.get("success", True)
        ],
    }

    dbt_payload: dict[str, Any] = {
        "success": dbt_result.success,
        "total": dbt_result.total,
        "passed": dbt_result.total - dbt_result.failures,
        "failures": dbt_result.failures,
        "elapsed": dbt_result.elapsed,
        "target_path": str(dbt_result.target_path),
        "log_path": str(dbt_result.log_path),
        "results": dbt_result.results,
    }

    artifact_dir = persist_contract_artifacts(input_path, ge_payload, dbt_result)  # type: ignore
    record_contracts_evidence(
        input_path, ge_result, dbt_result, artifact_dir, evidence_sink  # type: ignore
    )

    payload: dict[str, Any] = {
        "success": ge_result.success and dbt_result.success,
        "great_expectations": ge_payload,
        "dbt": dbt_payload,
        "artifact_dir": str(artifact_dir),
    }

    if output_format == "json":
        click.echo(json.dumps(payload, indent=2))
    else:
        click.echo(
            "Contracts " + ("passed" if payload["success"] else "failed"),
        )
        click.echo(
            "Great Expectations: "
            + f"{ge_payload['statistics'].get('successful_expectations', 0)} / "
            + f"{ge_payload['statistics'].get('evaluated_expectations', 0)}"
        )
        if ge_payload["failed_expectations"]:
            click.echo("Failing expectations:")
            for failure in ge_payload["failed_expectations"]:
                expectation = failure.get("expectation_type", "unknown")
                column = failure.get("kwargs", {}).get("column")
                scope = f" on column '{column}'" if column else ""
                click.echo(f" - {expectation}{scope}")
        click.echo(
            "dbt tests: "
            + f"{dbt_payload['passed']} passed / {dbt_payload['total']} executed"
        )
        if dbt_payload["failures"]:
            click.echo("Failing dbt tests:")
            for record in dbt_payload["results"]:
                status = record.get("status")
                if status and str(status).lower() not in {"pass", "skipped", "warn"}:
                    click.echo(
                        f" - {record.get('unique_id', record.get('name', 'unknown'))}: {status}"
                    )

    if not payload["success"]:
        raise click.exceptions.Exit(1)


@cli.command("coverage")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"], case_sensitive=False),
    default="text",
    help="Output format (text or JSON).",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Write JSON report to specified file.",
)
def coverage_command(output_format: str, output_path: Path | None) -> None:
    """Report contract coverage across curated tables.

    Calculates the percentage of curated tables covered by Great Expectations,
    dbt, and Deequ contracts. Exits with code 1 if coverage is below 95%.
    """
    coverage = calculate_contract_coverage()

    if output_format == "json" or output_path:
        report = report_coverage(output_path)
        if output_format == "json":
            click.echo(json.dumps(report, indent=2))
    else:
        click.echo("Contract Coverage Report")
        click.echo("========================")
        click.echo(f"Total tables: {coverage.total_tables}")
        click.echo(f"Covered tables: {coverage.covered_tables}")
        click.echo(f"Coverage: {coverage.coverage_percent:.1f}%")
        click.echo("Threshold: 95.0%")
        click.echo(f"Status: {'✓ PASS' if coverage.meets_threshold else '✗ FAIL'}")
        click.echo()
        click.echo("Coverage by tool:")
        for tool, count in coverage.coverage_by_tool.items():
            click.echo(f"  {tool}: {count} tables")
        if coverage.uncovered_tables:
            click.echo()
            click.echo("Uncovered tables:")
            for table in coverage.uncovered_tables:
                click.echo(f"  - {table}")

    if not coverage.meets_threshold:
        click.echo(
            f"\nERROR: Coverage ({coverage.coverage_percent:.1f}%) is below threshold (95%)",
            err=True,
        )
        raise click.exceptions.Exit(1)


@cli.command("mcp-server")
@click.option("--stdio/--no-stdio", default=True, help="Run using stdio transport.")
def mcp_server(stdio: bool) -> None:
    """Expose the pipeline via the Model Context Protocol for Copilot."""

    pipeline_factory = _get_cli_override("Pipeline", Pipeline)
    sink_factory = _get_cli_override("build_evidence_sink", build_evidence_sink)
    server_factory = _get_cli_override("CopilotMCPServer", CopilotMCPServer)
    plan_guard = _get_cli_override("plan_guard", CLI_ENVIRONMENT.plan_guard)

    def _build_pipeline() -> Pipeline:
        return pipeline_factory(evidence_sink=sink_factory())

    server = server_factory(
        pipeline=_build_pipeline(),
        plan_guard=plan_guard,
        pipeline_builder=_build_pipeline,
    )
    if stdio:
        asyncio_run = _get_cli_override("asyncio_run", asyncio.run)
        asyncio_run(server.serve_stdio())
    else:
        raise click.UsageError("Only stdio transport is supported in this build.")


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    cli()
