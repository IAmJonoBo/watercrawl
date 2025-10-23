from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

nx = pytest.importorskip("networkx")

from firecrawl_demo.domain import relationships


def _prov(source: str, connector: str | None = None) -> relationships.ProvenanceTag:
    return relationships.ProvenanceTag(
        source=source,
        connector=connector,
        retrieved_at=datetime(2024, 1, 1, tzinfo=UTC),
    )


def test_merge_organisations_accumulates_provenance_and_provinces() -> None:
    base = relationships.Organisation(
        identifier=relationships.canonical_id("organisation", "Aero"),
        name="Aero",
        provinces={"Gauteng"},
        statuses={"Candidate"},
        website_url="https://aero.za",
        aliases={"Aero Training"},
        provenance={_prov("baseline")},
    )
    incoming = relationships.Organisation(
        identifier=base.identifier,
        name="Aero",
        provinces={"Western Cape"},
        statuses={"Verified"},
        website_url="https://www.aero.za",
        aliases={"Aero"},
        provenance={_prov("regulator", connector="regulator")},
    )

    merged = relationships.merge_organisations(base, incoming)

    assert merged.website_url == "https://aero.za"
    assert merged.provinces == {"Gauteng", "Western Cape"}
    assert merged.statuses == {"Candidate", "Verified"}
    assert merged.aliases == {"Aero Training", "Aero"}
    assert len(merged.provenance) == 2


def test_merge_evidence_link_combines_weights_and_metadata() -> None:
    source_id = relationships.canonical_id("organisation", "Aero")
    target_id = relationships.canonical_id("source", "https://example")
    first = relationships.EvidenceLink(
        source=source_id,
        target=target_id,
        kind="corroborated_by",
        weight=0.4,
        provenance={_prov("baseline")},
        attributes={"connector": "press"},
    )
    second = relationships.EvidenceLink(
        source=source_id,
        target=target_id,
        kind="corroborated_by",
        weight=0.6,
        provenance={_prov("press", connector="press")},
        attributes={"headline": "Launch"},
    )

    merged = relationships.merge_evidence_links(first, second)

    assert merged.weight == 1.0
    assert merged.attributes["connector"] == "press"
    assert merged.attributes["headline"] == "Launch"
    assert len(merged.provenance) == 2


def test_canonical_id_is_stable() -> None:
    first = relationships.canonical_id("organisation", "Aero Dynamics Pty Ltd")
    second = relationships.canonical_id("organisation", " aero dynamics pty ltd ")

    assert first == second


def test_load_graph_snapshot_reads_metrics(tmp_path: Path) -> None:
    graph = nx.MultiDiGraph()
    organisation_id = "organisation:aero"
    person_id = "person:sam"
    source_id = "source:regulator"
    graph.add_node(
        organisation_id,
        type="organisation",
        name="Aero",
        provinces="Gauteng;Western Cape",
    )
    graph.add_node(person_id, type="person", name="Sam", phones="+27110000000")
    graph.add_node(
        source_id,
        type="source",
        uri="https://regulator.example",
        publisher="Regulator",
    )
    graph.add_edge(organisation_id, person_id, key="has_contact", kind="has_contact")
    graph.add_edge(
        organisation_id,
        source_id,
        key="corroborated_by",
        kind="corroborated_by",
    )
    graph_path = tmp_path / "relationships.graphml"
    nx.write_graphml(graph, graph_path)
    nodes_csv = tmp_path / "relationships.csv"
    nodes_csv.write_text("id,type\norganisation:aero,organisation\n", encoding="utf-8")
    edges_csv = tmp_path / "relationships_edges.csv"
    edges_csv.write_text(
        "source,target,kind\norganisation:aero,person:sam,has_contact\n",
        encoding="utf-8",
    )

    snapshot = relationships.load_graph_snapshot(
        graphml_path=graph_path,
        node_csv_path=nodes_csv,
        edge_csv_path=edges_csv,
    )

    assert snapshot.graph is not None
    assert snapshot.node_count == 3
    assert snapshot.edge_count == 2
    assert snapshot.node_summary_path == nodes_csv.resolve()
    assert snapshot.edge_summary_path == edges_csv.resolve()
    assert organisation_id in snapshot.centrality
    assert snapshot.anomalies
    assert snapshot.anomalies[0].code == "CONFLICTING_PROVINCE"
