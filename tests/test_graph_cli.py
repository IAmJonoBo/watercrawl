import json
from pathlib import Path

import pytest
from click.testing import CliRunner

pytest.importorskip("networkx")

from apps.analyst.graph_cli import cli
from firecrawl_demo.core import config
from firecrawl_demo.domain.relationships import (
    EvidenceLink,
    Organisation,
    Person,
    ProvenanceTag,
    RelationshipGraphSnapshot,
    SourceDocument,
    canonical_id,
)
from firecrawl_demo.integrations.telemetry.graph_semantics import (
    build_relationship_graph,
)


def _snapshot(tmp_path: Path) -> RelationshipGraphSnapshot:
    org = Organisation(
        identifier=canonical_id("organisation", "Aero Example"),
        name="Aero Example",
        provinces={"Gauteng"},
        statuses={"Verified"},
        website_url="https://aero.example",
        provenance={ProvenanceTag(source="dataset")},
    )
    person = Person(
        identifier=canonical_id("person", "Sam Analyst"),
        name="Sam Analyst",
        role="Head of Training",
        emails={"sam@aero.example"},
        phones={"+27115550123"},
        organisations={org.identifier},
        provenance={ProvenanceTag(source="dataset")},
    )
    source = SourceDocument(
        identifier=canonical_id("source", "https://sacaa.gov.za/aero"),
        uri="https://sacaa.gov.za/aero",
        publisher="South African Civil Aviation Authority",
        connector="regulator",
        provenance={ProvenanceTag(source="regulator", connector="regulator")},
    )
    graphml_path = tmp_path / "relationships.graphml"
    nodes_path = tmp_path / "relationships.csv"
    edges_path = tmp_path / "relationships_edges.csv"
    snapshot = build_relationship_graph(
        organisations=[org],
        people=[person],
        sources=[source],
        evidence=[
            EvidenceLink(
                source=org.identifier,
                target=person.identifier,
                kind="has_contact",
                provenance=person.provenance,
            ),
            EvidenceLink(
                source=org.identifier,
                target=source.identifier,
                kind="corroborated_by",
                provenance=source.provenance,
            ),
            EvidenceLink(
                source=person.identifier,
                target=source.identifier,
                kind="contact_evidence",
                provenance=source.provenance,
            ),
        ],
        graphml_path=graphml_path,
        nodes_csv_path=nodes_path,
        edges_csv_path=edges_path,
    )
    return snapshot


def test_contacts_by_regulator_lists_people(monkeypatch, tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    monkeypatch.setattr(config, "RELATIONSHIPS_GRAPHML", snapshot.graphml_path)
    monkeypatch.setattr(config, "RELATIONSHIPS_CSV", snapshot.node_summary_path)
    monkeypatch.setattr(config, "RELATIONSHIPS_EDGES_CSV", snapshot.edge_summary_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "contacts-by-regulator",
            "South African Civil Aviation Authority",
        ],
    )

    assert result.exit_code == 0
    assert "Sam Analyst" in result.output


def test_sources_for_phone_lists_documents(monkeypatch, tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    monkeypatch.setattr(config, "RELATIONSHIPS_GRAPHML", snapshot.graphml_path)
    monkeypatch.setattr(config, "RELATIONSHIPS_CSV", snapshot.node_summary_path)
    monkeypatch.setattr(config, "RELATIONSHIPS_EDGES_CSV", snapshot.edge_summary_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "sources-for-phone",
            "+27115550123",
        ],
    )

    assert result.exit_code == 0
    assert "https://sacaa.gov.za/aero" in result.output


def test_export_telemetry_writes_payload(monkeypatch, tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    monkeypatch.setattr(config, "RELATIONSHIPS_GRAPHML", snapshot.graphml_path)
    monkeypatch.setattr(config, "RELATIONSHIPS_CSV", snapshot.node_summary_path)
    monkeypatch.setattr(config, "RELATIONSHIPS_EDGES_CSV", snapshot.edge_summary_path)
    output = tmp_path / "telemetry.json"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "export-telemetry",
            str(output),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["node_count"] == 3
    assert payload["edge_count"] == 3
    assert payload["graphml_path"] == str(snapshot.graphml_path)
    assert payload["anomalies"] == []
