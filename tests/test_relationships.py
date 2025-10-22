from __future__ import annotations

from datetime import UTC, datetime

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
