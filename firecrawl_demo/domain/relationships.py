"""Domain models describing relationship intelligence graphs."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
import re
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


__all__ = [
    "EvidenceLink",
    "Organisation",
    "Person",
    "ProvenanceTag",
    "RelationshipAnomaly",
    "RelationshipGraphSnapshot",
    "SourceDocument",
    "canonical_id",
    "merge_evidence_links",
    "merge_organisations",
    "merge_people",
    "merge_provenance",
    "merge_sources",
]
