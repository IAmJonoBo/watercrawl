from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path

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
        extras={
            "lakehouse_manifest": manifest_path,
            "lakehouse_fingerprint": "abc123",
        },
        execution_start=datetime(2025, 10, 17, 12, 0, 0),
    )

    events = build_openlineage_events(report, context)

    assert [event["eventType"] for event in events] == ["START", "COMPLETE"]
    complete_event = events[-1]
    output_facets = complete_event["outputs"][0]["facets"]
    metrics = output_facets["acesMetrics"]["metrics"]
    assert metrics["rows_total"] == 1
    assert output_facets["datasetVersion"]["version"] == "2025-10-17"
    assert output_facets["evidenceLog"]["uri"].startswith("file://")
    assert output_facets["lakehouse"]["fingerprint"] == "abc123"
    assert output_facets["lakehouseManifest"]["uri"].startswith("file://")


def test_prov_and_catalogue_documents_capture_sources(tmp_path: Path) -> None:
    report = _sample_report()
    context = LineageContext(
        run_id="run-456",
        namespace="aces-aerodynamics",
        job_name="enrichment",
        dataset_name="flight-schools",
        input_uri="file://sample.csv",
        output_uri="file://output.csv",
        evidence_path=tmp_path / "evidence.csv",
        dataset_version="v1",
    )

    prov_document = build_prov_document(report, context)
    catalogue = build_catalog_entry(report, context)

    activity_ids = {node["@id"] for node in prov_document["@graph"]}
    assert f"urn:uuid:{context.run_id}" in activity_ids
    assert any("distribution" in key for key in catalogue)
    assert catalogue["dct:identifier"].endswith(context.dataset_version)


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
    assert artifacts.catalog_path.read_text()

    # Capture again with updated context to ensure idempotent replace semantics.
    initial_payload = artifacts.openlineage_path.read_text()
    newer_context = replace(context, dataset_version="v2")
    new_artifacts = manager.capture(report, newer_context)
    assert new_artifacts.openlineage_path.read_text() != initial_payload
