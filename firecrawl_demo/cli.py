from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.progress import BarColumn, Progress, TaskID, TextColumn, TimeRemainingColumn

from .audit import build_evidence_sink
from .contracts import validate_curated_file
from .excel import read_dataset
from .mcp.server import CopilotMCPServer
from .models import SchoolRecord
from .pipeline import Pipeline
from .progress import PipelineProgressListener


class RichPipelineProgress(PipelineProgressListener):
    """Rich progress bar implementation for pipeline runs."""

    def __init__(self, description: str, console: Console | None = None) -> None:
        self._description = description
        self._console = console or Console(stderr=True)
        self._progress = Progress(
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
def validate(input_path: Path, output_format: str, progress: bool | None) -> None:
    """Validate a CSV/XLSX dataset and report any quality issues."""

    pipeline = Pipeline()
    frame = read_dataset(input_path)
    report = pipeline.validator.validate_dataframe(frame)
    issues_payload = [issue.__dict__ for issue in report.issues]
    payload: dict[str, object] = {
        "rows": report.rows,
        "issues": issues_payload,
        "is_valid": report.is_valid,
    }
    if progress:
        listener = RichPipelineProgress("Validating dataset")
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
def enrich(
    input_path: Path,
    output_path: Path | None,
    output_format: str,
    progress: bool | None,
) -> None:
    """Validate, enrich, and export a dataset."""

    pipeline = Pipeline(evidence_sink=build_evidence_sink())
    target = output_path or input_path.with_name(
        f"{input_path.stem}_enriched{input_path.suffix}"
    )
    show_progress = _resolve_progress_flag(output_format, progress)
    listener: PipelineProgressListener | None = (
        RichPipelineProgress("Enriching dataset") if show_progress else None
    )
    report = pipeline.run_file(
        input_path,
        output_path=target,
        progress=listener,
    )
    issues_payload = [issue.__dict__ for issue in report.issues]
    payload = {
        "rows_total": report.metrics["rows_total"],
        "rows_enriched": report.metrics["enriched_rows"],
        "verified_rows": report.metrics["verified_rows"],
        "issues": issues_payload,
        "output_path": str(target),
        "adapter_failures": report.metrics["adapter_failures"],
    }
    if output_format == "json":
        click.echo(json.dumps(payload, indent=2))
    else:
        click.echo(
            "Enrichment complete: "
            f"{payload['rows_enriched']} of {payload['rows_total']} rows updated."
        )
        click.echo(f"Output written to: {payload['output_path']}")
        if payload["adapter_failures"]:
            click.echo(
                f"Warnings: {payload['adapter_failures']} research lookups failed; see logs."
            )


@cli.command("contracts")
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format", "output_format", type=click.Choice(["text", "json"]), default="text"
)
def contracts(input_path: Path, output_format: str) -> None:
    """Run Great Expectations contracts against a curated dataset."""

    result = validate_curated_file(input_path)
    payload: dict[str, Any] = {
        "success": result.success,
        "statistics": result.statistics,
        "unsuccessful_expectations": result.unsuccessful_expectations,
        "expectation_suite_name": result.expectation_suite_name,
        "meta": result.meta,
        "failed_expectations": [
            {
                "expectation_type": entry.get("expectation_config", {}).get(
                    "expectation_type"
                ),
                "kwargs": entry.get("expectation_config", {}).get("kwargs", {}),
                "result": entry.get("result", {}),
            }
            for entry in result.results
            if not entry.get("success", True)
        ],
    }
    if output_format == "json":
        click.echo(json.dumps(payload, indent=2))
    else:
        click.echo(
            "Contracts " + ("passed" if result.success else "failed"),
        )
        click.echo(
            f"Evaluated expectations: {payload['statistics'].get('evaluated_expectations', 0)}"
        )
        if payload["failed_expectations"]:
            click.echo("Failing expectations:")
            for failure in payload["failed_expectations"]:
                expectation = failure.get("expectation_type", "unknown")
                column = failure.get("kwargs", {}).get("column")
                scope = f" on column '{column}'" if column else ""
                click.echo(f" - {expectation}{scope}")
    if not result.success:
        raise click.exceptions.Exit(1)


@cli.command("mcp-server")
@click.option("--stdio/--no-stdio", default=True, help="Run using stdio transport.")
def mcp_server(stdio: bool) -> None:
    """Expose the pipeline via the Model Context Protocol for Copilot."""

    server = CopilotMCPServer(pipeline=Pipeline(evidence_sink=build_evidence_sink()))
    if stdio:
        asyncio.run(server.serve_stdio())
    else:
        raise click.UsageError("Only stdio transport is supported in this build.")


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    cli()
