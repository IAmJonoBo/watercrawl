from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd

from firecrawl_demo.core import models
from firecrawl_demo.integrations.lineage import (
    LineageContext,
    LineageManager,
    build_catalog_entry,
    build_openlineage_events,
    build_prov_document,
)


def _sample_report() -> models.PipelineReport:
    frame = pd.DataFrame(
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
        ]
    )
    validation = models.ValidationReport(issues=[], rows=1)
    evidence = [
        models.EvidenceRecord(
            row_id=2,
            organisation="Aero Academy",
            changes="Added contact details",
            sources=["https://aero.example/about", "https://gov.za/registry"],
            notes="Fresh regulator evidence",
            confidence=95,
        )
    ]
    report = models.PipelineReport(
        refined_dataframe=frame,
        validation_report=validation,
        evidence_log=evidence,
        metrics={
            "rows_total": 1,
            "enriched_rows": 1,
            "verified_rows": 1,
            "issues_found": 0,
            "adapter_failures": 0,
            "sanity_issues": 0,
            "quality_rejections": 0,
            "quality_issues": 0,
        },
        sanity_findings=[],
        quality_issues=[],
        rollback_plan=None,
    )
    return report


def test_build_openlineage_events_include_metrics(tmp_path: Path) -> None:
    report = _sample_report()
    manifest_path = tmp_path / "manifest.json"
    version_path = tmp_path / "version.json"
    context = LineageContext(
        run_id="run-123",
        namespace="aces-aerodynamics",
        job_name="enrichment",
        dataset_name="flight-schools",
        input_uri="file://sample.csv",
        output_uri="file://output.csv",
        evidence_path=tmp_path / "evidence.csv",
        dataset_version="2025-10-17",
        lakehouse_uri="file://lakehouse/flight_schools",
        execution_start=datetime(2025, 10, 17, 12, 0, 0),
    )
    context = context.with_lakehouse(
        uri="file://lakehouse/flight_schools",
        version="2025-10-17",
        manifest_path=manifest_path,
        fingerprint="abc123",
    )
    context = context.with_version(
        version="v2025",
        metadata_path=version_path,
        reproduce_command=("poetry", "run", "python"),
        input_fingerprint="input-hash",
        output_fingerprint="output-hash",
    )

    events = build_openlineage_events(report, context)

    assert [event["eventType"] for event in events] == ["START", "COMPLETE"]
    complete_event = events[-1]
    output_facets = complete_event["outputs"][0]["facets"]
    metrics = output_facets["acesMetrics"]["metrics"]
    assert metrics["rows_total"] == 1
    assert output_facets["datasetVersion"]["version"] == "v2025"
    assert output_facets["evidenceLog"]["uri"].startswith("file://")
    assert output_facets["lakehouse"]["fingerprint"] == "abc123"
    assert output_facets["lakehouseManifest"]["uri"].startswith("file://")
    assert output_facets["versionMetadata"]["uri"].startswith("file://")
    assert output_facets["versioning"]["inputFingerprint"] == "input-hash"
    assert output_facets["versioning"]["outputFingerprint"] == "output-hash"
    assert output_facets["versionReproduce"]["command"] == [
        "poetry",
        "run",
        "python",
    ]


def _node_lookup(graph: list[dict[str, Any]], node_id: str) -> dict[str, Any]:
    return next(node for node in graph if node.get("@id") == node_id)


def test_prov_and_catalogue_documents_capture_sources(tmp_path: Path) -> None:
    report = _sample_report()
    manifest_path = tmp_path / "lakehouse" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("{}")
    version_metadata = tmp_path / "version.json"
    version_metadata.write_text("{}")
    lineage_dir = tmp_path / "lineage"
    lineage_dir.mkdir()

    context = LineageContext(
        run_id="run-456",
        namespace="aces-aerodynamics",
        job_name="enrichment",
        dataset_name="flight-schools",
        input_uri="file://sample.csv",
        output_uri="file://output.csv",
        evidence_path=tmp_path / "evidence.csv",
        dataset_version="v1",
        execution_start=datetime(2025, 10, 17, 12, 0, 0),
    )
    context = context.with_lakehouse(
        uri="file://lakehouse/flight_schools",
        version="v1",
        manifest_path=manifest_path,
        fingerprint="abc123",
    ).with_version(
        version="v1",
        metadata_path=version_metadata,
        reproduce_command=("poetry", "run", "cli"),
        input_fingerprint="input-hash",
        output_fingerprint="output-hash",
        extras={"runbook": "docs/ops.md"},
    )

    prov_document = build_prov_document(
        report,
        context,
        artifact_dir=lineage_dir,
        completed_at=datetime(2025, 10, 17, 12, 30, 0),
    )
    catalogue = build_catalog_entry(
        report,
        context,
        artifact_dir=lineage_dir,
        completed_at=datetime(2025, 10, 17, 12, 30, 0),
    )

    graph = prov_document["@graph"]
    activity = _node_lookup(graph, f"urn:uuid:{context.run_id}")
    assert activity["prov:wasAssociatedWith"] == "urn:aces:agent:enrichment"
    assert context.output_uri is not None
    output_entity = _node_lookup(graph, context.output_uri)
    assert output_entity["prov:wasDerivedFrom"] == context.input_uri
    assert output_entity["aces:metrics"]["rows_total"] == 1
    assert _node_lookup(graph, manifest_path.resolve().as_uri())
    assert _node_lookup(graph, version_metadata.resolve().as_uri())
    assert any(node.get("@type") == "prov:Agent" for node in graph)

    assert catalogue["prov:wasGeneratedBy"] == f"urn:uuid:{context.run_id}"
    assert catalogue["dct:identifier"].endswith(context.dataset_version)
    measurements = catalogue["dqv:hasQualityMeasurement"]
    assert any(
        measurement["dqv:isMeasurementOf"]["@id"].endswith("rows_total")
        for measurement in measurements
    )
    distribution_urls = {
        dist["dcat:accessURL"] for dist in catalogue["dcat:distribution"]
    }
    assert cast(str, context.output_uri) in distribution_urls
    assert manifest_path.resolve().as_uri() in distribution_urls
    assert version_metadata.resolve().as_uri() in distribution_urls
    assert lineage_dir.resolve().as_uri() in distribution_urls


def test_lineage_manager_persists_artifacts(tmp_path: Path) -> None:
    report = _sample_report()
    context = LineageContext(
        run_id="run-storage",
        namespace="aces-aerodynamics",
        job_name="enrichment",
        dataset_name="flight-schools",
        input_uri="file://sample.csv",
        output_uri="file://output.csv",
        evidence_path=tmp_path / "evidence.csv",
    )
    manager = LineageManager(artifact_root=tmp_path)

    artifacts = manager.capture(report, context)

    assert artifacts.openlineage_path.exists()
    events = json.loads(artifacts.openlineage_path.read_text())
    assert events[0]["run"]["runId"] == "run-storage"
    assert artifacts.prov_path.exists()
    prov = json.loads(artifacts.prov_path.read_text())
    assert any(node["@id"].startswith("urn:uuid") for node in prov["@graph"])
    assert artifacts.catalog_path.exists()
    catalog_payload = json.loads(artifacts.catalog_path.read_text())
    assert catalog_payload["prov:wasGeneratedBy"].startswith("urn:uuid")
    assert catalog_payload["dqv:hasQualityMeasurement"]

    # Capture again with updated context to ensure idempotent replace semantics.
    initial_payload = artifacts.openlineage_path.read_text()
    newer_context = replace(context, dataset_version="v2")
    new_artifacts = manager.capture(report, newer_context)
    assert new_artifacts.openlineage_path.read_text() != initial_payload


def test_lineage_manager_emits_via_configured_emitter(tmp_path: Path) -> None:
    report = _sample_report()
    context = LineageContext(
        run_id="emit-001",
        namespace="aces-aerodynamics",
        job_name="enrichment",
        dataset_name="flight-schools",
        input_uri="file://sample.csv",
    )

    class DummyEmitter:
        def __init__(self) -> None:
            self.emitted: list[list[dict[str, Any]]] = []

        def emit(self, events: Sequence[dict[str, Any]]) -> None:
            self.emitted.append(list(events))

    emitter = DummyEmitter()
    manager = LineageManager(artifact_root=tmp_path, emitter=emitter)

    manager.capture(report, context)

    assert emitter.emitted, "Emitter should receive OpenLineage payloads"
    assert emitter.emitted[0][0]["run"]["runId"] == "emit-001"
