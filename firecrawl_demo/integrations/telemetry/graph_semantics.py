from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import networkx as nx
except ImportError:  # pragma: no cover - optional dependency
    nx = None  # type: ignore

try:
    import pandas as pd

    _PANDAS_AVAILABLE = True
except ImportError:
    pd = None  # type: ignore
    _PANDAS_AVAILABLE = False

from firecrawl_demo.core import config
from firecrawl_demo.domain.relationships import (
    EvidenceLink,
    Organisation,
    Person,
    RelationshipAnomaly,
    RelationshipGraphSnapshot,
    SourceDocument,
)
from firecrawl_demo.integrations.integration_plugins import (
    IntegrationPlugin,
    PluginConfigSchema,
    PluginContext,
    PluginHealthStatus,
    register_plugin,
)

REQUIRED_COLUMNS = (
    "Name of Organisation",
    "Province",
    "Status",
)


@dataclass
class GraphValidationIssue:
    code: str
    message: str
    details: dict[str, Any] | None = None


@dataclass
class GraphMetrics:
    organisation_nodes: int
    province_nodes: int
    status_nodes: int
    edge_count: int
    min_degree: int
    max_degree: int
    average_degree: float
    node_count: int = field(init=False)

    def __post_init__(self) -> None:
        self.node_count = (
            self.organisation_nodes + self.province_nodes + self.status_nodes
        )


@dataclass
class GraphSemanticsReport:
    csvw_metadata: dict[str, Any]
    r2rml_mapping: str
    metrics: GraphMetrics
    issues: list[GraphValidationIssue]

    @property
    def valid(self) -> bool:
        return not self.issues


def build_csvw_metadata(
    *, frame: Any, dataset_uri: str, evidence_log_uri: str | None = None
) -> dict[str, Any]:
    """Return CSVW metadata describing the enriched dataset."""

    columns = [
        {
            "name": column,
            "titles": column,
            "datatype": "string",
        }
        for column in frame.columns
    ]
    metadata: dict[str, Any] = {
        "@context": "http://www.w3.org/ns/csvw",
        "table": {
            "url": dataset_uri,
            "tableSchema": {"columns": columns},
            "notes": {},
        },
    }
    if evidence_log_uri:
        metadata["table"]["notes"]["evidenceLog"] = evidence_log_uri
    return metadata


def build_r2rml_mapping(*, dataset_uri: str, table_name: str) -> str:
    """Produce a simple Turtle mapping for R2RML consumers."""

    template = dataset_uri.replace(".csv", "/{row_id}")
    mapping = f"""
@prefix rr: <http://www.w3.org/ns/r2rml#> .
@prefix ex: <https://data.acesaero.co.za/schema/> .

<{table_name}> a rr:TriplesMap ;
    rr:logicalTable [ rr:tableName "{table_name}" ] ;
    rr:subjectMap [ rr:template "{template}" ; rr:class ex:FlightSchool ] ;
    rr:predicateObjectMap [
        rr:predicate ex:name ;
        rr:objectMap [ rr:column "Name of Organisation" ]
    ] ;
    rr:predicateObjectMap [
        rr:predicate ex:province ;
        rr:objectMap [ rr:column "Province" ]
    ] ;
    rr:predicateObjectMap [
        rr:predicate ex:status ;
        rr:objectMap [ rr:column "Status" ]
    ] .
"""
    return mapping.strip()


def _validate_required_columns(frame: Any) -> Iterable[GraphValidationIssue]:
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    for column in missing:
        yield GraphValidationIssue(
            code="MISSING_COLUMN",
            message=f"Required column '{column}' not found in dataset.",
            details={"column": column},
        )


def _validate_csvw(
    metadata: dict[str, Any], frame: Any
) -> Iterable[GraphValidationIssue]:
    schema_columns = metadata.get("table", {}).get("tableSchema", {}).get("columns", [])
    csvw_columns = [column.get("name") for column in schema_columns]
    extra_columns = [column for column in csvw_columns if column not in frame.columns]
    for column in extra_columns:
        yield GraphValidationIssue(
            code="CSVW_UNKNOWN_COLUMN",
            message=f"CSVW metadata references unknown column '{column}'.",
            details={"column": column},
        )


R2RML_COLUMN_PATTERN = re.compile(r'rr:column\s+"(?P<column>[^"]+)"')


def _validate_r2rml(mapping: str, frame: Any) -> Iterable[GraphValidationIssue]:
    referenced_columns = R2RML_COLUMN_PATTERN.findall(mapping)
    for column in referenced_columns:
        if column not in frame.columns:
            yield GraphValidationIssue(
                code="R2RML_UNKNOWN_COLUMN",
                message=f"R2RML mapping references unknown column '{column}'.",
                details={"column": column},
            )


def _build_graph_metrics(frame: Any) -> tuple[GraphMetrics, list[GraphValidationIssue]]:
    issues: list[GraphValidationIssue] = []
    if not _PANDAS_AVAILABLE or not hasattr(frame, "dropna"):
        return (
            GraphMetrics(
                organisation_nodes=0,
                province_nodes=0,
                status_nodes=0,
                edge_count=0,
                min_degree=0,
                max_degree=0,
                average_degree=0.0,
            ),
            [
                GraphValidationIssue(
                    code="PANDAS_REQUIRED",
                    message="Graph metric calculation requires pandas.",
                )
            ],
        )

    organisations = frame["Name of Organisation"].dropna().astype(str)
    provinces = frame["Province"].dropna().astype(str)
    statuses = frame["Status"].dropna().astype(str)

    organisations = organisations[organisations.str.strip() != ""]
    provinces = provinces[provinces.str.strip() != ""]
    statuses = statuses[statuses.str.strip() != ""]

    org_nodes = len(organisations.unique())
    province_nodes = len(provinces.unique())
    status_nodes = len(statuses.unique())

    degree_map: dict[str, int] = {}
    edge_count = 0
    for _, row in frame.iterrows():
        org = str(row.get("Name of Organisation", "")).strip()
        province = str(row.get("Province", "")).strip()
        status = str(row.get("Status", "")).strip()

        if not org:
            issues.append(
                GraphValidationIssue(
                    code="MISSING_ORGANISATION",
                    message="Row missing organisation name for graph construction.",
                )
            )
            continue

        degree_map.setdefault(org, 0)

        if province:
            degree_map[org] += 1
            edge_count += 1
        else:
            issues.append(
                GraphValidationIssue(
                    code="MISSING_PROVINCE",
                    message=f"Organisation '{org}' missing province edge.",
                    details={"organisation": org},
                )
            )

        if status:
            degree_map[org] += 1
            edge_count += 1
        else:
            issues.append(
                GraphValidationIssue(
                    code="MISSING_STATUS",
                    message=f"Organisation '{org}' missing status edge.",
                    details={"organisation": org},
                )
            )

    degrees = list(degree_map.values()) or [0]
    metrics = GraphMetrics(
        organisation_nodes=org_nodes,
        province_nodes=province_nodes,
        status_nodes=status_nodes,
        edge_count=edge_count,
        min_degree=min(degrees),
        max_degree=max(degrees),
        average_degree=sum(degrees) / len(degrees),
    )

    for organisation, degree in degree_map.items():
        if degree == 0:
            issues.append(
                GraphValidationIssue(
                    code="ISOLATED_ORGANISATION",
                    message=f"Organisation '{organisation}' has zero degree.",
                    details={"organisation": organisation},
                )
            )
    return metrics, issues


def _validate_metric_ranges(metrics: GraphMetrics) -> Iterable[GraphValidationIssue]:
    settings = getattr(config, "GRAPH_SEMANTICS", None)
    if settings is None or not getattr(settings, "enabled", True):
        return

    def _issue(
        code: str, message: str, value: Any | None = None
    ) -> GraphValidationIssue:
        details = {"value": value} if value is not None else None
        return GraphValidationIssue(code=code, message=message, details=details)

    if metrics.organisation_nodes < settings.min_organisation_nodes:
        yield _issue(
            "ORG_NODE_UNDERFLOW",
            (
                f"Organisation node count {metrics.organisation_nodes} below "
                f"minimum {settings.min_organisation_nodes}."
            ),
            metrics.organisation_nodes,
        )
    if metrics.province_nodes < settings.min_province_nodes:
        yield _issue(
            "PROVINCE_NODE_UNDERFLOW",
            (
                f"Province node count {metrics.province_nodes} below "
                f"minimum {settings.min_province_nodes}."
            ),
            metrics.province_nodes,
        )
    if metrics.status_nodes < settings.min_status_nodes:
        yield _issue(
            "STATUS_NODE_UNDERFLOW",
            (
                f"Status node count {metrics.status_nodes} below "
                f"minimum {settings.min_status_nodes}."
            ),
            metrics.status_nodes,
        )
    if metrics.province_nodes > settings.max_province_nodes:
        yield _issue(
            "PROVINCE_NODE_OVERFLOW",
            (
                f"Province node count {metrics.province_nodes} exceeds "
                f"maximum {settings.max_province_nodes}."
            ),
            metrics.province_nodes,
        )
    if metrics.status_nodes > settings.max_status_nodes:
        yield _issue(
            "STATUS_NODE_OVERFLOW",
            (
                f"Status node count {metrics.status_nodes} exceeds "
                f"maximum {settings.max_status_nodes}."
            ),
            metrics.status_nodes,
        )
    if metrics.edge_count < settings.min_edge_count:
        yield _issue(
            "EDGE_UNDERFLOW",
            (
                f"Edge count {metrics.edge_count} below minimum "
                f"{settings.min_edge_count}."
            ),
            metrics.edge_count,
        )

    if metrics.average_degree < settings.min_average_degree:
        yield _issue(
            "AVG_DEGREE_UNDERFLOW",
            (
                f"Average degree {metrics.average_degree:.2f} below minimum "
                f"{settings.min_average_degree:.2f}."
            ),
            metrics.average_degree,
        )
    if metrics.average_degree > settings.max_average_degree:
        yield _issue(
            "AVG_DEGREE_OVERFLOW",
            (
                f"Average degree {metrics.average_degree:.2f} exceeds maximum "
                f"{settings.max_average_degree:.2f}."
            ),
            metrics.average_degree,
        )


def generate_graph_semantics_report(
    *,
    frame: Any,
    dataset_uri: str,
    evidence_log_uri: str | None = None,
    table_name: str = "flight_schools",
) -> GraphSemanticsReport:
    csvw_metadata = build_csvw_metadata(
        frame=frame,
        dataset_uri=dataset_uri,
        evidence_log_uri=evidence_log_uri,
    )
    r2rml_mapping = build_r2rml_mapping(
        dataset_uri=dataset_uri,
        table_name=table_name,
    )

    issues: list[GraphValidationIssue] = list(_validate_required_columns(frame))
    issues.extend(_validate_csvw(csvw_metadata, frame))
    issues.extend(_validate_r2rml(r2rml_mapping, frame))
    metrics, metric_issues = _build_graph_metrics(frame)
    issues.extend(metric_issues)
    issues.extend(_validate_metric_ranges(metrics))

    return GraphSemanticsReport(
        csvw_metadata=csvw_metadata,
        r2rml_mapping=r2rml_mapping,
        metrics=metrics,
        issues=issues,
    )


def _json_dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if _PANDAS_AVAILABLE and pd is not None:
        frame = pd.DataFrame(rows)
        frame.to_csv(path, index=False)
    else:  # pragma: no cover - exercised when pandas unavailable
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)


def _stringify_collection(values: Iterable[Any]) -> str:
    return ";".join(sorted(str(value) for value in values if value))


def build_relationship_graph(
    *,
    organisations: Iterable[Organisation],
    people: Iterable[Person],
    sources: Iterable[SourceDocument],
    evidence: Iterable[EvidenceLink],
    graphml_path: Path,
    nodes_csv_path: Path,
    edges_csv_path: Path,
) -> RelationshipGraphSnapshot:
    """Materialise the relationship intelligence graph and derived metrics."""

    if nx is None:  # pragma: no cover - optional dependency guard
        raise RuntimeError("networkx is required to build the relationship graph")

    graphml_path.parent.mkdir(parents=True, exist_ok=True)
    nodes_csv_path.parent.mkdir(parents=True, exist_ok=True)
    edges_csv_path.parent.mkdir(parents=True, exist_ok=True)

    graph = nx.MultiDiGraph()
    node_rows: list[dict[str, Any]] = []
    for organisation in organisations:
        provenance = [tag.as_dict() for tag in organisation.provenance]
        graph.add_node(
            organisation.identifier,
            type="organisation",
            name=organisation.name,
            provinces=_stringify_collection(organisation.provinces),
            statuses=_stringify_collection(organisation.statuses),
            website=organisation.website_url or "",
            aliases=_stringify_collection(organisation.aliases),
            contacts=_stringify_collection(organisation.contacts),
            provenance=_json_dump(provenance),
        )
        node_rows.append(
            {
                "id": organisation.identifier,
                "type": "organisation",
                "name": organisation.name,
                "provinces": _stringify_collection(organisation.provinces),
                "statuses": _stringify_collection(organisation.statuses),
                "website": organisation.website_url or "",
                "aliases": _stringify_collection(organisation.aliases),
                "contacts": _stringify_collection(organisation.contacts),
                "provenance": _json_dump(provenance),
            }
        )

    for person in people:
        provenance = [tag.as_dict() for tag in person.provenance]
        graph.add_node(
            person.identifier,
            type="person",
            name=person.name,
            role=person.role or "",
            emails=_stringify_collection(person.emails),
            phones=_stringify_collection(person.phones),
            organisations=_stringify_collection(person.organisations),
            provenance=_json_dump(provenance),
        )
        node_rows.append(
            {
                "id": person.identifier,
                "type": "person",
                "name": person.name,
                "role": person.role or "",
                "emails": _stringify_collection(person.emails),
                "phones": _stringify_collection(person.phones),
                "organisations": _stringify_collection(person.organisations),
                "provenance": _json_dump(provenance),
            }
        )

    for source in sources:
        provenance = [tag.as_dict() for tag in source.provenance]
        graph.add_node(
            source.identifier,
            type="source",
            uri=source.uri,
            title=source.title or "",
            publisher=source.publisher or "",
            connector=source.connector or "",
            tags=_stringify_collection(source.tags),
            summary=source.summary or "",
            provenance=_json_dump(provenance),
        )
        node_rows.append(
            {
                "id": source.identifier,
                "type": "source",
                "uri": source.uri,
                "title": source.title or "",
                "publisher": source.publisher or "",
                "connector": source.connector or "",
                "tags": _stringify_collection(source.tags),
                "summary": source.summary or "",
                "provenance": _json_dump(provenance),
            }
        )

    edge_rows: list[dict[str, Any]] = []
    for link in evidence:
        if not graph.has_node(link.source) or not graph.has_node(link.target):
            continue
        provenance = [tag.as_dict() for tag in link.provenance]
        attributes = {
            key: value for key, value in link.attributes.items() if value is not None
        }
        graph.add_edge(
            link.source,
            link.target,
            key=link.kind,
            kind=link.kind,
            weight=link.weight or 0.0,
            provenance=_json_dump(provenance),
            attributes=_json_dump(attributes),
        )
        edge_rows.append(
            {
                "source": link.source,
                "target": link.target,
                "kind": link.kind,
                "weight": link.weight or 0.0,
                "provenance": _json_dump(provenance),
                "attributes": _json_dump(attributes),
            }
        )

    nx.write_graphml(graph, graphml_path)
    _write_csv(node_rows, nodes_csv_path)
    _write_csv(edge_rows, edges_csv_path)

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
    for organisation in organisations:
        if len(organisation.provinces) > 1:
            anomalies.append(
                RelationshipAnomaly(
                    code="CONFLICTING_PROVINCE",
                    message=(
                        f"Organisation '{organisation.name}' has conflicting provinces"
                        f" {sorted(organisation.provinces)}"
                    ),
                    details={
                        "organisation": organisation.name,
                        "provinces": sorted(organisation.provinces),
                        "identifier": organisation.identifier,
                    },
                )
            )

    return RelationshipGraphSnapshot(
        graphml_path=graphml_path,
        node_summary_path=nodes_csv_path,
        edge_summary_path=edges_csv_path,
        node_count=graph.number_of_nodes(),
        edge_count=graph.number_of_edges(),
        centrality=centrality,
        betweenness=betweenness,
        community_assignments=community_assignments,
        anomalies=anomalies,
        graph=graph,
    )


__all__ = [
    "build_relationship_graph",
    "GraphMetrics",
    "GraphSemanticsReport",
    "GraphValidationIssue",
    "build_csvw_metadata",
    "build_r2rml_mapping",
    "generate_graph_semantics_report",
]


def _graph_health_probe(context: PluginContext) -> PluginHealthStatus:
    details = {
        "metadata_context": "csvw",
        "optional_dependencies": ["pandas", "networkx"],
    }
    return PluginHealthStatus(
        healthy=True,
        reason="Graph semantics helpers available",
        details=details,
    )


register_plugin(
    IntegrationPlugin(
        name="graph_semantics",
        category="telemetry",
        factory=lambda ctx: {
            "build_csvw_metadata": build_csvw_metadata,
            "build_r2rml_mapping": build_r2rml_mapping,
            "generate_graph_semantics_report": generate_graph_semantics_report,
            "build_relationship_graph": build_relationship_graph,
        },
        config_schema=PluginConfigSchema(
            optional_dependencies=("pandas", "networkx"),
            description="Generate CSVW metadata and R2RML mappings for curated datasets.",
        ),
        health_probe=_graph_health_probe,
        summary="CSVW and R2RML helpers",
    )
)
