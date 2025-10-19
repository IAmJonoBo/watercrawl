from __future__ import annotations

import asyncio
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from firecrawl_demo.application.pipeline import Pipeline
from firecrawl_demo.application.quality import QualityGate
from firecrawl_demo.domain.models import EvidenceRecord, SchoolRecord
from firecrawl_demo.integrations.adapters.research import (
    ResearchFinding,
    StaticResearchAdapter,
)
from firecrawl_demo.integrations.storage.lakehouse import (
    LakehouseConfig,
    LakehouseManifest,
    LocalLakehouseWriter,
)
from firecrawl_demo.integrations.storage.versioning import (
    VersionInfo,
    VersioningManager,
)
from firecrawl_demo.integrations.telemetry.lineage import (
    LineageArtifacts,
    LineageContext,
    LineageManager,
)


def _minimal_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Name of Organisation": "Example Flight School",
                "Province": "Gauteng",
                "Status": "Candidate",
                "Website URL": "example.com",
                "Contact Person": "",
                "Contact Number": "",
                "Contact Email Address": "",
            }
        ]
    )


def test_pipeline_import():
    assert hasattr(Pipeline, "run_dataframe")


@pytest.mark.asyncio()
async def test_run_dataframe_disallowed_inside_event_loop() -> None:
    pipe = Pipeline()
    frame = _minimal_frame()

    with pytest.raises(
        RuntimeError, match="run_dataframe cannot be used inside an active event loop"
    ):
        pipe.run_dataframe(frame)


@pytest.mark.asyncio()
async def test_run_dataframe_async_rejects_missing_columns() -> None:
    pipe = Pipeline()
    frame = pd.DataFrame([{"Name of Organisation": "Example"}])

    with pytest.raises(ValueError, match="Missing expected columns"):
        await pipe.run_dataframe_async(frame)


class TrackingLakehouseWriter(LocalLakehouseWriter):
    def __init__(self, root: Path) -> None:
        super().__init__(LakehouseConfig(root_path=root, enabled=True))
        self.calls: list[tuple[str, pd.DataFrame]] = []

    def write(self, run_id: str, dataframe: pd.DataFrame) -> LakehouseManifest:
        manifest = super().write(run_id, dataframe)
        self.calls.append((run_id, dataframe.copy()))
        return manifest


class TrackingVersioningManager(VersioningManager):
    def __init__(self, root: Path) -> None:
        super().__init__(
            metadata_root=root, enabled=True, reproduce_command=("enrich",)
        )
        self.calls: list[tuple[str, str]] = []

    def record_snapshot(
        self,
        *,
        run_id: str,
        manifest: LakehouseManifest,
        input_fingerprint: str,
        extras: dict[str, Any] | None = None,
    ) -> VersionInfo:
        info = super().record_snapshot(
            run_id=run_id,
            manifest=manifest,
            input_fingerprint=input_fingerprint,
            extras=extras,
        )
        self.calls.append((run_id, input_fingerprint))
        return info


class TrackingLineageManager(LineageManager):
    def __init__(self, artifact_root: Path) -> None:
        super().__init__(artifact_root=artifact_root, enabled=True)
        self.captured: list[LineageContext] = []

    def capture(self, report: Any, context: LineageContext) -> LineageArtifacts:
        self.captured.append(context)
        run_dir = self.artifact_root / context.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        artifacts = LineageArtifacts(
            run_id=context.run_id,
            openlineage_path=run_dir / "openlineage.json",
            prov_path=run_dir / "prov.json",
            catalog_path=run_dir / "catalog.json",
        )
        for path in (
            artifacts.openlineage_path,
            artifacts.prov_path,
            artifacts.catalog_path,
        ):
            path.write_text("{}", encoding="utf-8")
        return artifacts


class _RecordingEvidenceSink:
    def __init__(self) -> None:
        self.records: list[list[EvidenceRecord]] = []

    def record(self, records: Iterable[EvidenceRecord]) -> None:
        self.records.append(list(records))


def test_pipeline_records_lakehouse_versioning_and_lineage(tmp_path: Path) -> None:
    research_adapter = StaticResearchAdapter(
        {
            "Example Flight School": ResearchFinding(
                website_url="https://official.gov.za",
                contact_person="Lindiwe Nxasana",
                contact_email="lindiwe@official.gov.za",
                contact_phone="+27 10 555 0100",
                sources=[
                    "https://official.gov.za/flight-school",
                    "https://press.example.com/profile",
                ],
                notes="Primary adapter note",
                confidence=80,
                investigation_notes=["Press coverage indicates a rename"],
                physical_address="123 Aviation Way, Pretoria",
            )
        }
    )
    evidence_sink = _RecordingEvidenceSink()
    lakehouse_writer = TrackingLakehouseWriter(tmp_path)
    versioning_manager = TrackingVersioningManager(tmp_path)
    lineage_manager = TrackingLineageManager(tmp_path)

    pipe = Pipeline(
        research_adapter=research_adapter,
        evidence_sink=evidence_sink,
        quality_gate=QualityGate(min_confidence=0, require_official_source=False),
        lakehouse_writer=lakehouse_writer,
        versioning_manager=versioning_manager,
        lineage_manager=lineage_manager,
    )

    frame = _minimal_frame()
    context = LineageContext(
        run_id="run-123",
        namespace="ns",
        job_name="enrichment",
        dataset_name="flight-schools",
        input_uri="file://input.csv",
    )

    report = asyncio.run(pipe.run_dataframe_async(frame, lineage_context=context))

    assert report.metrics["enriched_rows"] == 1
    assert report.lakehouse_manifest is not None
    assert report.version_info is not None
    assert report.lineage_artifacts is not None
    assert pipe.last_report is report

    assert lakehouse_writer.calls and lakehouse_writer.calls[0][0] == "run-123"
    assert versioning_manager.calls == [
        ("run-123", report.version_info.input_fingerprint)
    ]
    assert lineage_manager.captured
    assert (
        lineage_manager.captured[0].lakehouse_uri == report.lakehouse_manifest.table_uri
    )
    assert (
        evidence_sink.records
        and evidence_sink.records[0][0].organisation == "Example Flight School"
    )


def test_frame_from_payload_reads_path(tmp_path: Path) -> None:
    pipe = Pipeline()
    frame = _minimal_frame()
    dataset_path = tmp_path / "dataset.csv"
    frame.to_csv(dataset_path, index=False)

    loaded = pipe._frame_from_payload({"path": str(dataset_path)})
    assert list(loaded.columns) == list(frame.columns)


def test_frame_from_payload_validates_rows_structure() -> None:
    pipe = Pipeline()

    with pytest.raises(ValueError, match="must be a list"):
        pipe._frame_from_payload({"rows": {"not": "a list"}})


def test_frame_from_payload_requires_input() -> None:
    pipe = Pipeline()

    with pytest.raises(ValueError, match="include 'path' or 'rows'"):
        pipe._frame_from_payload({})


def test_detect_duplicate_schools_handles_missing_column() -> None:
    pipe = Pipeline()
    frame = pd.DataFrame([{"Status": "Verified"}])

    assert pipe._detect_duplicate_schools(frame, {}) == []


def test_list_sanity_issues_empty_before_run() -> None:
    pipe = Pipeline()
    assert pipe._list_sanity_issues() == {"status": "empty", "findings": []}


def test_compose_evidence_notes_includes_rebrand_metadata() -> None:
    pipe = Pipeline()
    finding = ResearchFinding(
        notes="Adapter insight",
        investigation_notes=["Possible rename detected"],
        alternate_names=["Example Flight Academy"],
        physical_address="Cape Town International Airport",
    )
    original_row = pd.Series({"Website URL": "https://legacy.example.com"})
    record = SchoolRecord(
        name="Example Flight School",
        province="Gauteng",
        status="Candidate",
        website_url="https://new.example.com",
        contact_person="Analyst",
        contact_number="+27105550100",
        contact_email="analyst@new.example.com",
    )

    notes = pipe._compose_evidence_notes(
        finding,
        original_row,
        record,
        has_official_source=False,
        total_source_count=1,
        fresh_source_count=0,
        sanity_notes=["Removed invalid email"],
    )

    assert "Adapter insight" in notes
    assert "Possible rename" in notes
    assert "Latest address intelligence" in notes
    assert "Evidence shortfall" in notes
