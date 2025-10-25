"""CLI utilities for exploring the relationship intelligence graph."""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

import click
import networkx as nx
from rich.console import Console
from rich.table import Table

from watercrawl.core import config
from watercrawl.domain import relationships

_DEFAULT_THROTTLE = 0.2


def _load_snapshot() -> relationships.RelationshipGraphSnapshot:
    try:
        snapshot = relationships.load_graph_snapshot(
            graphml_path=config.RELATIONSHIPS_GRAPHML,
            node_csv_path=config.RELATIONSHIPS_CSV,
            edge_csv_path=config.RELATIONSHIPS_EDGES_CSV,
        )
    except FileNotFoundError as exc:  # pragma: no cover - defensive guard
        raise click.ClickException(str(exc)) from exc
    except RuntimeError as exc:  # pragma: no cover - optional dependency guard
        raise click.ClickException(str(exc)) from exc
    return snapshot


def _string_to_list(value: str) -> list[str]:
    return [item for item in (value or "").split(";") if item]


def _organisation_names(graph: nx.MultiDiGraph, node: str) -> list[str]:
    names: list[str] = []
    for neighbour in graph.neighbors(node):
        data = graph.nodes[neighbour]
        if data.get("type") == "organisation":
            names.append(data.get("name", neighbour))
    return names


def _person_nodes_for_source(graph: nx.MultiDiGraph, source_node: str) -> list[str]:
    people: list[str] = []
    for predecessor, _, edge_key in cast(Any, graph).in_edges(source_node, keys=True):
        data = graph.nodes[predecessor]
        if data.get("type") == "person":
            people.append(predecessor)
    if people:
        return people
    organisations = [
        predecessor
        for predecessor, _, _ in cast(Any, graph).in_edges(source_node, keys=True)
        if graph.nodes[predecessor].get("type") == "organisation"
    ]
    for organisation in organisations:
        for _, neighbour, _ in graph.out_edges(organisation, keys=True):
            if graph.nodes[neighbour].get("type") == "person":
                people.append(neighbour)
    return list(dict.fromkeys(people))


@click.group(help="Relationship intelligence graph utilities for analysts.")
def cli() -> None:
    """Entry point for graph exploration commands."""


@cli.command("contacts-by-regulator")
@click.argument("regulator")
@click.option(
    "--throttle",
    type=float,
    default=_DEFAULT_THROTTLE,
    show_default=True,
    help="Delay (seconds) between successive regulator source scans.",
)
def contacts_by_regulator(regulator: str, throttle: float) -> None:
    """List contacts linked to sources from a specific regulator."""

    snapshot = _load_snapshot()
    if snapshot.graph is None:  # pragma: no cover - defensive guard
        raise click.ClickException("Relationship graph has not been materialised yet.")
    graph = snapshot.graph
    console = Console()
    regulator_key = regulator.casefold()
    rows: list[tuple[str, str, str]] = []

    for node, data in graph.nodes(data=True):
        if data.get("type") != "source":
            continue
        publisher = str(data.get("publisher", "")).casefold()
        connector = str(data.get("connector", "")).casefold()
        if regulator_key not in publisher and regulator_key not in connector:
            continue
        for person_node in _person_nodes_for_source(graph, node):
            person_data = graph.nodes[person_node]
            contact_name = person_data.get("name", person_node)
            organisations = _organisation_names(graph, person_node)
            rows.append(
                (contact_name, ", ".join(organisations) or "—", data.get("uri", ""))
            )
        if throttle > 0:
            time.sleep(throttle)

    if not rows:
        console.print(
            f"[yellow]No contacts linked to regulator '{regulator}'.[/yellow]"
        )
        return

    table = Table(title=f"Contacts linked to {regulator}")
    table.add_column("Contact")
    table.add_column("Organisation")
    table.add_column("Source URI")
    for contact, organisation, source in rows:
        table.add_row(contact, organisation, source or "—")
    console.print(table)


@cli.command("sources-for-phone")
@click.argument("phone")
@click.option(
    "--throttle",
    type=float,
    default=_DEFAULT_THROTTLE,
    show_default=True,
    help="Delay (seconds) between successive evidence lookups.",
)
def sources_for_phone(phone: str, throttle: float) -> None:
    """Show sources corroborating a specific phone number."""

    snapshot = _load_snapshot()
    if snapshot.graph is None:  # pragma: no cover - defensive guard
        raise click.ClickException("Relationship graph has not been materialised yet.")
    graph = snapshot.graph
    console = Console()
    normalized = phone.strip()
    matches: list[tuple[str, list[tuple[str, str]]]] = []

    for node, data in graph.nodes(data=True):
        if data.get("type") != "person":
            continue
        phones = {item.strip() for item in _string_to_list(str(data.get("phones", "")))}
        if normalized not in phones:
            continue
        sources: list[tuple[str, str]] = []
        for _, target, _ in graph.out_edges(node, keys=True):
            target_data = graph.nodes[target]
            if target_data.get("type") != "source":
                continue
            sources.append(
                (target_data.get("uri", ""), target_data.get("publisher", ""))
            )
            if throttle > 0:
                time.sleep(throttle)
        matches.append((data.get("name", node), sources))

    if not matches:
        console.print(
            f"[yellow]No sources recorded for phone number {phone}. [/yellow]"
        )
        return

    table = Table(title=f"Sources corroborating {phone}")
    table.add_column("Contact")
    table.add_column("Source URI")
    table.add_column("Publisher")
    for contact, sources in matches:
        if not sources:
            table.add_row(contact, "—", "—")
            continue
        for index, (uri, publisher) in enumerate(sources):
            table.add_row(contact if index == 0 else "", uri or "—", publisher or "—")
    console.print(table)


@cli.command("export-telemetry")
@click.argument("output", type=click.Path(path_type=Path))
def export_telemetry(output: Path) -> None:
    """Export relationship graph telemetry (metrics and anomalies) to JSON."""

    snapshot = _load_snapshot()
    payload = {
        "graphml_path": str(snapshot.graphml_path),
        "node_summary_path": str(snapshot.node_summary_path),
        "edge_summary_path": str(snapshot.edge_summary_path),
        "node_count": snapshot.node_count,
        "edge_count": snapshot.edge_count,
        "centrality": snapshot.centrality,
        "betweenness": snapshot.betweenness,
        "community_assignments": snapshot.community_assignments,
        "anomalies": [asdict(anomaly) for anomaly in snapshot.anomalies],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    console = Console()
    console.print(f"[green]Telemetry exported to {output}[/green]")


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    cli()
