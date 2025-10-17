from __future__ import annotations

from typing import Any

import pandas as pd


def build_csvw_metadata(
    *, frame: pd.DataFrame, dataset_uri: str, evidence_log_uri: str | None = None
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
