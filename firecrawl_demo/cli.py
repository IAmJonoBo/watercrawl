from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click

from .compliance import append_evidence_log
from .excel import read_dataset
from .mcp.server import CopilotMCPServer
from .pipeline import Pipeline


@click.group()
def cli() -> None:
    """Utilities for validating and enriching ACES Aerodynamics datasets."""


@cli.command()
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format", "output_format", type=click.Choice(["text", "json"]), default="text"
)
def validate(input_path: Path, output_format: str) -> None:
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
def enrich(input_path: Path, output_path: Path | None, output_format: str) -> None:
    """Validate, enrich, and export a dataset."""

    pipeline = Pipeline()
    target = output_path or input_path.with_name(
        f"{input_path.stem}_enriched{input_path.suffix}"
    )
    report = pipeline.run_file(input_path, output_path=target)
    if report.evidence_log:
        append_evidence_log([record.as_dict() for record in report.evidence_log])

    issues_payload = [issue.__dict__ for issue in report.issues]
    payload = {
        "rows_total": report.metrics["rows_total"],
        "rows_enriched": report.metrics["enriched_rows"],
        "verified_rows": report.metrics["verified_rows"],
        "issues": issues_payload,
        "output_path": str(target),
    }
    if output_format == "json":
        click.echo(json.dumps(payload, indent=2))
    else:
        click.echo(
            "Enrichment complete: "
            f"{payload['rows_enriched']} of {payload['rows_total']} rows updated."
        )
        click.echo(f"Output written to: {payload['output_path']}")


@cli.command("mcp-server")
@click.option("--stdio/--no-stdio", default=True, help="Run using stdio transport.")
def mcp_server(stdio: bool) -> None:
    """Expose the pipeline via the Model Context Protocol for Copilot."""

    server = CopilotMCPServer(pipeline=Pipeline())
    if stdio:
        asyncio.run(server.serve_stdio())
    else:
        raise click.UsageError("Only stdio transport is supported in this build.")


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    cli()
