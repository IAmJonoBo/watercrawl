from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from firecrawl_demo import config, models


def _as_uri(value: str | Path | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, Path):
        return value.resolve().as_uri()
    if value.startswith("file://"):
        return value
    return Path(value).resolve().as_uri()


@dataclass(slots=True)
class LineageContext:
    """Runtime metadata required to emit lineage documents."""

    run_id: str
    namespace: str
    job_name: str
    dataset_name: str
    input_uri: str
    output_uri: str | None = None
    evidence_path: Path | None = None
    dataset_version: str | None = None
    lakehouse_uri: str | None = None
    execution_start: datetime = field(default_factory=lambda: datetime.utcnow())
    extras: dict[str, Any] = field(default_factory=dict)

    def with_lakehouse(
        self,
        uri: str | None,
        version: str | None,
        *,
        manifest_path: Path | None = None,
        fingerprint: str | None = None,
    ) -> LineageContext:
        """Return a new context capturing lakehouse outputs."""

        extras = dict(self.extras)
        if manifest_path is not None:
            extras["lakehouse_manifest"] = manifest_path
        if fingerprint is not None:
            extras["lakehouse_fingerprint"] = fingerprint
        return replace(
            self,
            lakehouse_uri=uri,
            dataset_version=version or self.dataset_version,
            extras=extras,
        )


@dataclass(frozen=True)
class LineageArtifacts:
    """Paths to stored lineage artefacts for a pipeline run."""

    run_id: str
    openlineage_path: Path
    prov_path: Path
    catalog_path: Path


@dataclass(slots=True)
class LineageManager:
    """Persist lineage artefacts derived from pipeline runs."""

    artifact_root: Path = field(default_factory=lambda: config.LINEAGE.artifact_root)
    namespace: str = field(default_factory=lambda: config.LINEAGE.namespace)
    job_name: str = field(default_factory=lambda: config.LINEAGE.job_name)
    dataset_name: str = field(default_factory=lambda: config.LINEAGE.dataset_name)
    enabled: bool = field(default_factory=lambda: config.LINEAGE.enabled)

    def capture(
        self, report: models.PipelineReport, context: LineageContext
    ) -> LineageArtifacts:
        if not self.enabled:
            artifact_dir = self.artifact_root / "lineage" / context.run_id
            artifact_dir.mkdir(parents=True, exist_ok=True)
            placeholder = artifact_dir / "disabled.json"
            placeholder.write_text(
                json.dumps({"enabled": False, "run_id": context.run_id})
            )
            return LineageArtifacts(
                run_id=context.run_id,
                openlineage_path=placeholder,
                prov_path=placeholder,
                catalog_path=placeholder,
            )

        artifact_dir = self.artifact_root / "lineage" / context.run_id
        artifact_dir.mkdir(parents=True, exist_ok=True)

        events = build_openlineage_events(report, context)
        openlineage_path = artifact_dir / "openlineage.json"
        openlineage_path.write_text(json.dumps(events, indent=2, sort_keys=True))

        prov_document = build_prov_document(report, context)
        prov_path = artifact_dir / "prov.jsonld"
        prov_path.write_text(json.dumps(prov_document, indent=2, sort_keys=True))

        catalog_entry = build_catalog_entry(report, context)
        catalog_path = artifact_dir / "catalog.jsonld"
        catalog_path.write_text(json.dumps(catalog_entry, indent=2, sort_keys=True))

        return LineageArtifacts(
            run_id=context.run_id,
            openlineage_path=openlineage_path,
            prov_path=prov_path,
            catalog_path=catalog_path,
        )


def _metrics_facet(metrics: dict[str, int]) -> dict[str, Any]:
    return {
        "acesMetrics": {"metrics": metrics},
    }


def _dataset_facets(context: LineageContext, metrics: dict[str, int]) -> dict[str, Any]:
    facets: dict[str, Any] = _metrics_facet(metrics)
    if context.dataset_version:
        facets["datasetVersion"] = {"version": context.dataset_version}
    evidence_uri = _as_uri(context.evidence_path)
    if evidence_uri:
        facets["evidenceLog"] = {"uri": evidence_uri}
    manifest_path = context.extras.get("lakehouse_manifest")
    if manifest_path:
        facets["lakehouseManifest"] = {"uri": _as_uri(manifest_path)}
    if context.lakehouse_uri:
        lakehouse_facet: dict[str, Any] = {"uri": context.lakehouse_uri}
        fingerprint = context.extras.get("lakehouse_fingerprint")
        if fingerprint:
            lakehouse_facet["fingerprint"] = fingerprint
        facets["lakehouse"] = lakehouse_facet
    return facets


def build_openlineage_events(
    report: models.PipelineReport, context: LineageContext
) -> list[dict[str, Any]]:
    """Serialise OpenLineage start/complete events for the run."""

    run = {
        "runId": context.run_id,
    }
    job = {
        "namespace": context.namespace,
        "name": context.job_name,
    }

    inputs = [
        {
            "namespace": context.namespace,
            "name": context.dataset_name,
            "facets": {
                "dataset": {"uri": context.input_uri},
            },
        }
    ]
    outputs = [
        {
            "namespace": context.namespace,
            "name": context.dataset_name,
            "facets": _dataset_facets(context, report.metrics),
        }
    ]

    start_event = {
        "eventType": "START",
        "eventTime": context.execution_start.isoformat(),
        "run": run,
        "job": job,
        "inputs": inputs,
    }
    complete_event = {
        "eventType": "COMPLETE",
        "eventTime": datetime.utcnow().isoformat(),
        "run": run,
        "job": job,
        "inputs": inputs,
        "outputs": outputs,
    }
    return [start_event, complete_event]


def build_prov_document(
    report: models.PipelineReport, context: LineageContext
) -> dict[str, Any]:
    """Generate a PROV-O JSON-LD document capturing the run."""

    activity_id = f"urn:uuid:{context.run_id}"
    used_entities: list[dict[str, Any]] = [
        {
            "@id": context.input_uri,
            "@type": "prov:Entity",
            "dct:title": context.dataset_name,
        }
    ]
    if context.evidence_path:
        used_entities.append(
            {
                "@id": _as_uri(context.evidence_path),
                "@type": "prov:Entity",
                "dct:title": "Evidence Log",
            }
        )

    generated_entities: list[dict[str, Any]] = []
    if context.output_uri:
        generated_entities.append(
            {
                "@id": context.output_uri,
                "@type": "prov:Entity",
                "dct:title": f"{context.dataset_name} (enriched)",
            }
        )
    if context.lakehouse_uri:
        generated_entities.append(
            {
                "@id": context.lakehouse_uri,
                "@type": "prov:Entity",
                "dct:title": f"{context.dataset_name} Lakehouse Table",
            }
        )

    activity = {
        "@id": activity_id,
        "@type": "prov:Activity",
        "prov:startedAtTime": context.execution_start.isoformat(),
        "prov:endedAtTime": datetime.utcnow().isoformat(),
        "prov:used": [entity["@id"] for entity in used_entities],
        "prov:generated": [entity["@id"] for entity in generated_entities],
    }

    graph: list[dict[str, Any]] = [activity, *used_entities, *generated_entities]
    return {
        "@context": {
            "prov": "http://www.w3.org/ns/prov#",
            "dct": "http://purl.org/dc/terms/",
        },
        "@graph": graph,
    }


def build_catalog_entry(
    report: models.PipelineReport, context: LineageContext
) -> dict[str, Any]:
    """Produce a minimal DCAT dataset entry for the run."""

    identifier = context.dataset_version or context.run_id
    distributions: list[dict[str, Any]] = []
    dataset = {
        "@context": {
            "dcat": "http://www.w3.org/ns/dcat#",
            "dct": "http://purl.org/dc/terms/",
        },
        "@type": "dcat:Dataset",
        "dct:title": f"{context.dataset_name} enrichment",
        "dct:identifier": f"urn:aces:{identifier}",
        "dct:issued": context.execution_start.date().isoformat(),
        "dcat:keyword": ["enrichment", "flight-schools", "evidence"],
        "dcat:distribution": distributions,
    }
    if context.output_uri:
        distributions.append(
            {
                "@type": "dcat:Distribution",
                "dcat:accessURL": context.output_uri,
                "dct:format": "text/csv",
            }
        )
    if context.lakehouse_uri:
        distributions.append(
            {
                "@type": "dcat:Distribution",
                "dcat:accessURL": context.lakehouse_uri,
                "dct:format": f"application/{config.LAKEHOUSE.backend}",
            }
        )
    evidence_uri = _as_uri(context.evidence_path)
    if evidence_uri:
        notes: dict[str, Any] = cast(dict[str, Any], dataset.setdefault("notes", {}))
        notes["evidenceLog"] = evidence_uri
    return dataset


__all__ = [
    "LineageContext",
    "LineageArtifacts",
    "LineageManager",
    "build_openlineage_events",
    "build_prov_document",
    "build_catalog_entry",
]
