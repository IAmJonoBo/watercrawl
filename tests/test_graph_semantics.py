from __future__ import annotations

from pathlib import Path

import pandas as pd

from firecrawl_demo.core.excel import EXPECTED_COLUMNS
from firecrawl_demo.domain.relationships import (
    EvidenceLink,
    Organisation,
    Person,
    ProvenanceTag,
    SourceDocument,
    canonical_id,
)
from firecrawl_demo.integrations.telemetry.graph_semantics import (
    GraphSemanticsReport,
    GraphValidationIssue,
    build_csvw_metadata,
    build_r2rml_mapping,
    build_relationship_graph,
    generate_graph_semantics_report,
)


def _prov(source: str, connector: str | None = None) -> ProvenanceTag:
    return ProvenanceTag(source=source, connector=connector)


def _sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Name of Organisation": "Aero Academy",
                "Province": "Gauteng",
                "Status": "Verified",
                "Website URL": "https://aero.example",
                "Contact Person": "Sam Analyst",
                "Contact Number": "+27110000000",
                "Contact Email Address": "sam@aero.example",
            }
        ],
        columns=list(EXPECTED_COLUMNS),
    )


def test_csvw_metadata_enumerates_columns(tmp_path: Path) -> None:
    frame = _sample_frame()
    metadata = build_csvw_metadata(
        frame=frame,
        dataset_uri="file://flight-schools.csv",
        evidence_log_uri="file://evidence.csv",
    )

    assert metadata["table"]["url"] == "file://flight-schools.csv"
    column_names = [
        column["name"] for column in metadata["table"]["tableSchema"]["columns"]
    ]
    assert "Province" in column_names
    assert metadata["table"]["notes"]["evidenceLog"] == "file://evidence.csv"


def test_r2rml_mapping_contains_predicates() -> None:
    mapping = build_r2rml_mapping(
        dataset_uri="file://flight-schools.csv", table_name="flight_schools"
    )

    assert "rr:logicalTable" in mapping
    assert "ex:province" in mapping
    assert "rr:template" in mapping


def test_generate_graph_semantics_report_success(tmp_path: Path) -> None:
    frame = _sample_frame()
    report = generate_graph_semantics_report(
        frame=frame,
        dataset_uri="file://flight-schools.csv",
        evidence_log_uri="file://evidence.csv",
    )

    assert isinstance(report, GraphSemanticsReport)
    assert report.valid
    assert report.metrics.organisation_nodes == 1
    assert report.metrics.edge_count == 2
    assert (
        report.csvw_metadata["table"]["notes"]["evidenceLog"] == "file://evidence.csv"
    )


def test_generate_graph_semantics_report_flags_missing_province() -> None:
    frame = _sample_frame()
    frame.loc[0, "Province"] = ""

    report = generate_graph_semantics_report(
        frame=frame,
        dataset_uri="file://flight-schools.csv",
        evidence_log_uri=None,
    )

    assert not report.valid
    issue_codes = [issue.code for issue in report.issues]
    assert "MISSING_PROVINCE" in issue_codes
    assert "PROVINCE_NODE_UNDERFLOW" in issue_codes
    assert any(isinstance(issue, GraphValidationIssue) for issue in report.issues)


def test_generate_graph_semantics_report_flags_low_average_degree() -> None:
    frame = _sample_frame()
    frame.loc[0, "Status"] = ""
    frame.loc[0, "Province"] = ""

    report = generate_graph_semantics_report(
        frame=frame,
        dataset_uri="file://flight-schools.csv",
        evidence_log_uri=None,
    )

    issue_codes = [issue.code for issue in report.issues]
    assert "AVG_DEGREE_UNDERFLOW" in issue_codes


def test_build_relationship_graph_exports_and_flags_conflicts(tmp_path: Path) -> None:
    org = Organisation(
        identifier=canonical_id("organisation", "Aero Example"),
        name="Aero Example",
        provinces={"Gauteng", "Western Cape"},
        statuses={"Verified"},
        website_url="https://aero.example",
        provenance={_prov("dataset")},
    )
    person = Person(
        identifier=canonical_id("person", "Sam Analyst"),
        name="Sam Analyst",
        role="Head of Training",
        emails={"sam@aero.example"},
        phones={"+27115550123"},
        organisations={org.identifier},
        provenance={_prov("dataset")},
    )
    source = SourceDocument(
        identifier=canonical_id("source", "https://sacaa.gov.za/aero"),
        uri="https://sacaa.gov.za/aero",
        publisher="South African Civil Aviation Authority",
        connector="regulator",
        provenance={_prov("regulator", connector="regulator")},
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
                provenance={_prov("dataset")},
            ),
            EvidenceLink(
                source=org.identifier,
                target=source.identifier,
                kind="corroborated_by",
                provenance=source.provenance,
            ),
        ],
        graphml_path=graphml_path,
        nodes_csv_path=nodes_path,
        edges_csv_path=edges_path,
    )

    assert graphml_path.exists()
    assert nodes_path.exists()
    assert edges_path.exists()
    assert snapshot.node_count == 3
    assert snapshot.edge_count == 2
    assert org.identifier in snapshot.centrality
    assert snapshot.anomalies
    assert snapshot.anomalies[0].code == "CONFLICTING_PROVINCE"
