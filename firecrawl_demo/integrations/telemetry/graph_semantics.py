from __future__ import annotations

from typing import Any

try:
    import pandas as pd

    _PANDAS_AVAILABLE = True
except ImportError:
    pd = None  # type: ignore
    _PANDAS_AVAILABLE = False

from firecrawl_demo.integrations.integration_plugins import (
    IntegrationPlugin,
    PluginConfigSchema,
    PluginContext,
    PluginHealthStatus,
    register_plugin,
)


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


__all__ = ["build_csvw_metadata", "build_r2rml_mapping"]


def _graph_health_probe(context: PluginContext) -> PluginHealthStatus:
    details = {
        "metadata_context": "csvw",
        "optional_dependencies": ["pandas"],
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
        },
        config_schema=PluginConfigSchema(
            optional_dependencies=("pandas",),
            description="Generate CSVW metadata and R2RML mappings for curated datasets.",
        ),
        health_probe=_graph_health_probe,
        summary="CSVW and R2RML helpers",
    )
)
