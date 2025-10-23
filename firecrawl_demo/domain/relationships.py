"""Domain models describing relationship intelligence graphs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

try:  # pragma: no cover - optional dependency during type checking
    import networkx as nx
except Exception:  # pragma: no cover - fallback when networkx unavailable
    nx = None  # type: ignore


_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class ProvenanceTag:
    """Track the origin of an entity or relationship attribute."""

    source: str
    connector: str | None = None
    retrieved_at: datetime | None = None
    notes: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Serialize to a JSON/GraphML friendly dictionary."""

        payload: dict[str, Any] = {
            "source": self.source,
            "connector": self.connector,
            "notes": self.notes,
        }
        if self.retrieved_at:
            payload["retrieved_at"] = self.retrieved_at.isoformat()
        return {key: value for key, value in payload.items() if value is not None}


@dataclass
class Organisation:
    """Organisation node tracked in the relationship graph."""

    identifier: str
    name: str
    provinces: set[str] = field(default_factory=set)
    statuses: set[str] = field(default_factory=set)
    website_url: str | None = None
    aliases: set[str] = field(default_factory=set)
    attributes: dict[str, Any] = field(default_factory=dict)
    external_ids: dict[str, str] = field(default_factory=dict)
    contacts: set[str] = field(default_factory=set)
    provenance: set[ProvenanceTag] = field(default_factory=set)


@dataclass
class Person:
    """Contact node linked to organisations and evidence sources."""

    identifier: str
    name: str
    role: str | None = None
    emails: set[str] = field(default_factory=set)
    phones: set[str] = field(default_factory=set)
    organisations: set[str] = field(default_factory=set)
    provenance: set[ProvenanceTag] = field(default_factory=set)


@dataclass
class SourceDocument:
    """Evidence source describing where information was obtained."""

    identifier: str
    uri: str
    title: str | None = None
    publisher: str | None = None
    connector: str | None = None
    retrieved_at: datetime | None = None
    tags: set[str] = field(default_factory=set)
    summary: str | None = None
    provenance: set[ProvenanceTag] = field(default_factory=set)


@dataclass
class EvidenceLink:
    """Relationship edge linking entities with provenance."""

    source: str
    target: str
    kind: str
    weight: float | None = None
    provenance: set[ProvenanceTag] = field(default_factory=set)
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RelationshipAnomaly:
    """Flag surfaced while analysing the relationship graph."""

    code: str
    message: str
    details: dict[str, Any] | None = None


@dataclass
class RelationshipGraphSnapshot:
    """Materialised artefact describing the exported relationship graph."""

    graphml_path: Path
    node_summary_path: Path
    edge_summary_path: Path
    node_count: int
    edge_count: int
    centrality: dict[str, float]
    betweenness: dict[str, float]
    community_assignments: dict[str, int]
    anomalies: list[RelationshipAnomaly]
    graph: "nx.MultiDiGraph | None" = None


def canonical_id(kind: str, value: str) -> str:
    """Return a deterministic identifier for graph nodes/edges."""

    slug = _SLUG_PATTERN.sub("-", value.strip().casefold()).strip("-")
    if not slug:
        slug = "unknown"
    return f"{kind}:{slug}"


def merge_provenance(*tag_sets: Iterable[ProvenanceTag]) -> set[ProvenanceTag]:
    """Combine provenance tags without duplications."""

    merged: set[ProvenanceTag] = set()
    for tags in tag_sets:
        merged.update(tags)
    return merged


def _merge_attributes(
    primary: Mapping[str, Any], incoming: Mapping[str, Any]
) -> dict[str, Any]:
    merged = dict(primary)
    for key, value in incoming.items():
        if key not in merged or merged[key] in (None, "", []):
            merged[key] = value
    return merged


def merge_organisations(primary: Organisation, incoming: Organisation) -> Organisation:
    """Merge two organisation nodes, preserving provenance."""

    combined = replace(primary)
    combined.provinces = set(primary.provinces) | set(incoming.provinces)
    combined.statuses = set(primary.statuses) | set(incoming.statuses)
    combined.aliases = (
        set(primary.aliases)
        | set(incoming.aliases)
        | ({incoming.name} if incoming.name else set())
    )
    combined.contacts = set(primary.contacts) | set(incoming.contacts)
    combined.external_ids = {**incoming.external_ids, **primary.external_ids}
    combined.attributes = _merge_attributes(primary.attributes, incoming.attributes)
    if not combined.website_url and incoming.website_url:
        combined.website_url = incoming.website_url
    combined.provenance = merge_provenance(primary.provenance, incoming.provenance)
    return combined


def merge_people(primary: Person, incoming: Person) -> Person:
    """Merge person nodes while keeping preferred role/contact details."""

    combined = replace(primary)
    combined.emails = set(primary.emails) | set(incoming.emails)
    combined.phones = set(primary.phones) | set(incoming.phones)
    combined.organisations = set(primary.organisations) | set(incoming.organisations)
    if not combined.role and incoming.role:
        combined.role = incoming.role
    combined.provenance = merge_provenance(primary.provenance, incoming.provenance)
    return combined


def merge_sources(primary: SourceDocument, incoming: SourceDocument) -> SourceDocument:
    """Merge source documents, preferring earlier metadata when duplicates appear."""

    combined = replace(primary)
    combined.tags = set(primary.tags) | set(incoming.tags)
    if not combined.title and incoming.title:
        combined.title = incoming.title
    if not combined.publisher and incoming.publisher:
        combined.publisher = incoming.publisher
    if not combined.connector and incoming.connector:
        combined.connector = incoming.connector
    if not combined.retrieved_at and incoming.retrieved_at:
        combined.retrieved_at = incoming.retrieved_at
    if not combined.summary and incoming.summary:
        combined.summary = incoming.summary
    combined.provenance = merge_provenance(primary.provenance, incoming.provenance)
    return combined


def merge_evidence_links(primary: EvidenceLink, incoming: EvidenceLink) -> EvidenceLink:
    """Merge evidence edges, summing weights and provenance."""

    combined = replace(primary)
    base_weight = primary.weight or 0.0
    incoming_weight = incoming.weight or 0.0
    combined.weight = (base_weight + incoming_weight) or None
    combined.attributes = _merge_attributes(primary.attributes, incoming.attributes)
    combined.provenance = merge_provenance(primary.provenance, incoming.provenance)
    return combined


def load_graph_snapshot(
    *,
    graphml_path: Path,
    node_csv_path: Path | None = None,
    edge_csv_path: Path | None = None,
) -> RelationshipGraphSnapshot:
    """Load a previously exported relationship graph snapshot."""

    if nx is None:  # pragma: no cover - optional dependency guard
        raise RuntimeError("networkx is required to load the relationship graph")

    graphml_path = graphml_path.expanduser().resolve()
    if not graphml_path.exists():
        raise FileNotFoundError(
            f"Relationship graph snapshot not found at {graphml_path}"
        )

    raw_graph = nx.read_graphml(graphml_path)
    if isinstance(raw_graph, nx.MultiDiGraph):
        graph = raw_graph
    else:
        graph = nx.MultiDiGraph()
        graph.add_nodes_from(raw_graph.nodes(data=True))
        for source, target, data in raw_graph.edges(data=True):
            attributes = dict(data)
            edge_key = attributes.pop("key", None)
            if edge_key is not None:
                graph.add_edge(source, target, key=edge_key, **attributes)
            else:
                graph.add_edge(source, target, **attributes)
    nodes_csv = (
        node_csv_path.expanduser().resolve()
        if node_csv_path is not None
        else graphml_path.with_suffix(".csv")
    )
    edges_csv = (
        edge_csv_path.expanduser().resolve()
        if edge_csv_path is not None
        else graphml_path.with_name(f"{graphml_path.stem}_edges.csv")
    )

    simple_graph = nx.Graph(graph)
    if simple_graph.number_of_nodes():
        centrality = nx.degree_centrality(simple_graph)
        betweenness = nx.betweenness_centrality(simple_graph)
        try:
            communities = list(
                nx.algorithms.community.greedy_modularity_communities(simple_graph)
            )
        except Exception:  # pragma: no cover - community detection optional
            communities = []
    else:
        centrality = {}
        betweenness = {}
        communities = []

    community_assignments: dict[str, int] = {}
    for index, community in enumerate(communities):
        for node in community:
            community_assignments[str(node)] = index

    anomalies: list[RelationshipAnomaly] = []
    for node, data in graph.nodes(data=True):
        if data.get("type") != "organisation":
            continue
        raw = str(data.get("provinces", ""))
        provinces = {item for item in raw.split(";") if item}
        if len(provinces) > 1:
            anomalies.append(
                RelationshipAnomaly(
                    code="CONFLICTING_PROVINCE",
                    message=(
                        f"Organisation '{data.get('name', node)}' has conflicting"
                        f" provinces {sorted(provinces)}"
                    ),
                    details={
                        "organisation": data.get("name", node),
                        "provinces": sorted(provinces),
                        "identifier": str(node),
                    },
                )
            )

    return RelationshipGraphSnapshot(
        graphml_path=graphml_path,
        node_summary_path=nodes_csv,
        edge_summary_path=edges_csv,
        node_count=graph.number_of_nodes(),
        edge_count=graph.number_of_edges(),
        centrality={str(key): value for key, value in centrality.items()},
        betweenness={str(key): value for key, value in betweenness.items()},
        community_assignments=community_assignments,
        anomalies=anomalies,
        graph=graph,
    )


__all__ = [
    "EvidenceLink",
    "Organisation",
    "Person",
    "ProvenanceTag",
    "RelationshipAnomaly",
    "RelationshipGraphSnapshot",
    "SourceDocument",
    "canonical_id",
    "load_graph_snapshot",
    "merge_evidence_links",
    "merge_organisations",
    "merge_people",
    "merge_provenance",
    "merge_sources",
]
