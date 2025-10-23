"""End-user CLI entrypoint that wraps the analyst tooling for deployment builds."""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from firecrawl_demo.interfaces import analyst_cli
from firecrawl_demo.integrations.integration_plugins import contract_registry

_USER_FACING_COMMANDS = {
    "validate": "Inspect a dataset and report quality issues before enrichment.",
    "enrich": "Validate, enrich, and export a curated dataset with evidence logging.",
    "contracts": "Run Great Expectations and dbt contracts to guard publishes.",
    "coverage": "Report contract coverage across curated tables.",
}


@click.group(help="User-facing utilities for ACES Aerodynamics dataset operations.")
def cli() -> None:
    """Expose analyst commands with user-centric descriptions."""


for _name in _USER_FACING_COMMANDS:
    cli.add_command(analyst_cli.cli.commands[_name], name=_name)


@cli.command()
def overview() -> None:
    """Show available commands and the recommended workflow order."""

    console = Console()
    table = Table(title="ACES Aerodynamics dataset workflow")
    table.add_column("Step", justify="right", style="cyan", no_wrap=True)
    table.add_column("Command", style="magenta")
    table.add_column("Description", style="white")
    ordered_commands = ["validate", "enrich", "contracts", "coverage"]
    for index, name in enumerate(ordered_commands, start=1):
        description = _USER_FACING_COMMANDS.get(name, "")
        table.add_row(str(index), name, description)
    console.print(table)
    console.print("[green]\nSample dataset:[/green] data/sample.csv")
    console.print(
        "[yellow]Tip:[/yellow] Use `--format json` to integrate results into automation pipelines."
    )

    registry = contract_registry()
    contract_table = Table(title="Contract registry")
    contract_table.add_column("Contract", style="cyan", no_wrap=True)
    contract_table.add_column("Version", style="green", no_wrap=True)
    contract_table.add_column("Schema URI", style="magenta")
    for contract_name in ("ValidationReport", "PipelineReport", "PlanArtifact", "CommitArtifact"):
        metadata = registry.get(contract_name)
        if metadata is None:
            continue
        contract_table.add_row(
            contract_name,
            str(metadata.get("version", "unknown")),
            metadata.get("schema_uri", "n/a"),
        )
    console.print("")
    console.print(contract_table)


# Expose optional MCP bridge without highlighting it in the overview table.
cli.add_command(analyst_cli.cli.commands["mcp-server"], name="mcp-server")


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    cli()
