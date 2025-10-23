from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from firecrawl_demo.application.pipeline import (
    Pipeline,
    _CircuitBreaker,
    _LookupCoordinator,
    _RowState,
)
from firecrawl_demo.application.progress import NullPipelineProgressListener
from firecrawl_demo.application.quality import QualityFinding, QualityGate
from firecrawl_demo.application.row_processing import (
    RowProcessingRequest,
    compose_quality_rejection_notes,
    describe_changes,
    process_row,
)
from firecrawl_demo.core import cache as cache_module
from firecrawl_demo.core import config
from firecrawl_demo.domain.contracts import EvidenceRecordContract
from firecrawl_demo.domain.models import (
    EvidenceRecord,
    SchoolRecord,
    evidence_record_from_contract,
)
from firecrawl_demo.integrations.adapters.research import (
    ResearchAdapter,
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
                "Fleet Size": "",
                "Runway Length": "",
                "Runway Length (m)": "",
            }
        ]
    )


def _frame_with_rows(count: int) -> pd.DataFrame:
    frame = pd.concat([_minimal_frame() for _ in range(count)], ignore_index=True)
    for idx in range(count):
        frame.at[idx, "Name of Organisation"] = f"Example Flight School {idx}"
    return frame


@pytest.fixture()
def typed_bulk_frame() -> pd.DataFrame:
    rows = [
        {
            "Name of Organisation": f"Typed Org {idx}",
            "Province": "Gauteng" if idx % 2 == 0 else "Western Cape",
            "Status": "Candidate",
            "Website URL": "",
            "Contact Person": "",
            "Contact Number": "",
            "Contact Email Address": "",
        }
        for idx in range(4)
    ]
    frame = pd.DataFrame(rows)
    string_dtype = pd.StringDtype()
    for column in frame.columns:
        frame[column] = frame[column].astype(string_dtype)
    return frame


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

    def record(
        self, records: Iterable[EvidenceRecord | EvidenceRecordContract]
    ) -> None:
        batch: list[EvidenceRecord] = []
        for record in records:
            if isinstance(record, EvidenceRecord):
                batch.append(record)
            else:
                batch.append(evidence_record_from_contract(record))
        self.records.append(batch)


def test_pipeline_records_lakehouse_versioning_and_lineage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    graphml_path = tmp_path / "relationships.graphml"
    nodes_path = tmp_path / "relationships.csv"
    edges_path = tmp_path / "relationships_edges.csv"
    monkeypatch.setattr(config, "RELATIONSHIPS_GRAPHML", graphml_path)
    monkeypatch.setattr(config, "RELATIONSHIPS_CSV", nodes_path)
    monkeypatch.setattr(config, "RELATIONSHIPS_EDGES_CSV", edges_path)

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
    snapshot = report.relationship_graph
    assert snapshot is not None
    assert snapshot.graphml_path == graphml_path
    assert snapshot.node_summary_path == nodes_path
    assert snapshot.edge_summary_path == edges_path
    assert graphml_path.exists()
    assert nodes_path.exists()
    assert edges_path.exists()
    assert report.metrics["relationship_graph_nodes"] >= 2
    assert report.metrics["relationship_graph_edges"] >= 1
    assert report.metrics["relationship_anomalies"] >= 0


@pytest.mark.asyncio()
async def test_pipeline_lookup_concurrency_improves_throughput(monkeypatch) -> None:
    cache_module._cache.clear()
    monkeypatch.setattr(config, "RESEARCH_CONCURRENCY_LIMIT", 4)
    monkeypatch.setattr(config, "RESEARCH_CACHE_TTL_HOURS", None)
    monkeypatch.setattr(config, "RESEARCH_MAX_RETRIES", 0)
    monkeypatch.setattr(config, "RESEARCH_RETRY_BACKOFF_BASE_SECONDS", 0.0)
    monkeypatch.setattr(config, "RESEARCH_CIRCUIT_BREAKER_FAILURE_THRESHOLD", 5)
    monkeypatch.setattr(config, "RESEARCH_CIRCUIT_BREAKER_RESET_SECONDS", 30.0)

    class SlowAdapter(ResearchAdapter):
        def __init__(self) -> None:
            self.calls = 0

        def lookup(self, organisation: str, province: str) -> ResearchFinding:
            self.calls += 1
            time.sleep(0.05)
            slug = organisation.lower().replace(" ", "-")
            return ResearchFinding(
                website_url=f"https://{slug}.za",
                contact_person="Automation Tester",
                contact_email=f"{slug}@example.za",
                contact_phone="+27105550100",
                sources=["https://example.com"],
                notes="slow adapter",
                confidence=85,
            )

    adapter = SlowAdapter()
    frame = _frame_with_rows(4)
    pipe = Pipeline(
        research_adapter=adapter,
        quality_gate=QualityGate(min_confidence=0, require_official_source=False),
    )

    start = time.perf_counter()
    report = await pipe.run_dataframe_async(frame)
    elapsed = time.perf_counter() - start

    assert adapter.calls == len(frame)
    assert elapsed < 0.25
    assert report.metrics["adapter_retry_attempts"] == 0
    assert report.metrics["research_cache_hits"] == 0
    assert report.metrics["research_queue_latency_avg_ms"] >= 0.0


@pytest.mark.asyncio()
async def test_pipeline_preserves_order_with_concurrency_one(monkeypatch) -> None:
    cache_module._cache.clear()
    monkeypatch.setattr(config, "RESEARCH_CONCURRENCY_LIMIT", 1)
    monkeypatch.setattr(config, "RESEARCH_CACHE_TTL_HOURS", None)

    names = [f"Ordered Org {idx}" for idx in range(3)]
    frame = _frame_with_rows(len(names))
    for idx, name in enumerate(names):
        frame.at[idx, "Name of Organisation"] = name

    class RecordingAdapter(ResearchAdapter):
        def __init__(self) -> None:
            self.calls: list[str] = []

        def lookup(self, organisation: str, province: str) -> ResearchFinding:
            self.calls.append(organisation)
            slug = organisation.lower().replace(" ", "-")
            return ResearchFinding(
                website_url=f"https://{slug}.za",
                contact_person=organisation,
                contact_email=f"{slug}@example.za",
                contact_phone="+27105550100",
                sources=[f"https://{slug}.za"],
                notes=organisation,
                confidence=90,
            )

    adapter = RecordingAdapter()
    pipe = Pipeline(
        research_adapter=adapter,
        quality_gate=QualityGate(min_confidence=0, require_official_source=False),
    )

    report = await pipe.run_dataframe_async(frame)

    from collections import Counter

    assert adapter.calls == names
    evidence_counts = Counter(record.organisation for record in report.evidence_log)
    assert evidence_counts == Counter({name: 2 for name in names})
    assert report.metrics["adapter_circuit_rejections"] == 0
    assert report.metrics["research_cache_misses"] == len(names)


@pytest.mark.asyncio()
async def test_lookup_coordinator_taskgroup_tracks_concurrency(monkeypatch) -> None:
    from dataclasses import replace

    cache_module._cache.clear()
    monkeypatch.setattr(config, "RESEARCH_CACHE_TTL_HOURS", None)

    class TimedAdapter(ResearchAdapter):
        def __init__(self) -> None:
            self.calls: list[tuple[str, float, float]] = []

        def lookup(self, organisation: str, province: str) -> ResearchFinding:
            start = time.perf_counter()
            time.sleep(0.05)
            end = time.perf_counter()
            slug = organisation.lower().replace(" ", "-")
            self.calls.append((organisation, start, end))
            return ResearchFinding(
                website_url=f"https://{slug}.za",
                contact_email=f"{slug}@example.za",
                sources=["https://example.com"],
                confidence=88,
            )

    adapter = TimedAdapter()
    listener = NullPipelineProgressListener()
    circuit_breaker = _CircuitBreaker(failure_threshold=5, reset_seconds=30.0)

    states: list[_RowState] = []
    for position in range(4):
        original_row = {
            "Name of Organisation": f"Concurrent Org {position}",
            "Province": "Gauteng",
            "Status": "Candidate",
            "Website URL": "",
            "Contact Person": "",
            "Contact Number": "",
            "Contact Email Address": "",
        }
        base_record = SchoolRecord.from_dataframe_row(original_row)
        states.append(
            _RowState(
                position=position,
                index=position,
                row_id=position + 2,
                original_row=original_row,
                original_record=base_record,
                working_record=replace(base_record),
            )
        )

    coordinator = _LookupCoordinator(
        adapter=adapter,
        listener=listener,
        concurrency=4,
        cache_ttl_hours=None,
        max_retries=0,
        retry_backoff_base_seconds=0.0,
        circuit_breaker=circuit_breaker,
    )

    async with coordinator:
        start = time.perf_counter()
        results = await coordinator.run(states)
        elapsed = time.perf_counter() - start

    assert [result.state.position for result in results] == list(range(len(states)))
    assert elapsed < 0.12
    assert coordinator.metrics.cache_misses == len(states)
    assert coordinator.metrics.cache_hits == 0
    assert len(coordinator.metrics.queue_latencies) == len(states)
    assert adapter.calls and len(adapter.calls) == len(states)


@pytest.mark.asyncio()
async def test_lookup_coordinator_circuit_breaker_metrics(monkeypatch) -> None:
    from dataclasses import replace

    cache_module._cache.clear()
    monkeypatch.setattr(config, "RESEARCH_CACHE_TTL_HOURS", None)

    class FailingAdapter(ResearchAdapter):
        def __init__(self) -> None:
            self.calls = 0

        def lookup(self, organisation: str, province: str) -> ResearchFinding:
            self.calls += 1
            raise RuntimeError("simulated adapter failure")

    adapter = FailingAdapter()
    listener = NullPipelineProgressListener()
    circuit_breaker = _CircuitBreaker(failure_threshold=2, reset_seconds=60.0)

    states: list[_RowState] = []
    for position in range(4):
        original_row = {
            "Name of Organisation": f"Breaker Org {position}",
            "Province": "Gauteng",
            "Status": "Candidate",
            "Website URL": "",
            "Contact Person": "",
            "Contact Number": "",
            "Contact Email Address": "",
        }
        base_record = SchoolRecord.from_dataframe_row(original_row)
        states.append(
            _RowState(
                position=position,
                index=position,
                row_id=position + 2,
                original_row=original_row,
                original_record=base_record,
                working_record=replace(base_record),
            )
        )

    coordinator = _LookupCoordinator(
        adapter=adapter,
        listener=listener,
        concurrency=1,
        cache_ttl_hours=None,
        max_retries=0,
        retry_backoff_base_seconds=0.0,
        circuit_breaker=circuit_breaker,
    )

    async with coordinator:
        results = await coordinator.run(states)

    assert adapter.calls == 2
    assert coordinator.metrics.failures == 2
    assert coordinator.metrics.retries == 2
    assert coordinator.metrics.circuit_rejections == len(states) - adapter.calls

    failure_notes = [
        result.finding.notes for result in results[: adapter.calls]
    ]
    assert all("Research adapter failed" in note for note in failure_notes)
    paused_messages = [result.finding.notes for result in results[adapter.calls :]]
    assert paused_messages and all("temporarily paused" in msg for msg in paused_messages)


def test_process_row_quality_rejection_produces_deterministic_artifacts(
    typed_bulk_frame: pd.DataFrame,
) -> None:
    source_row = typed_bulk_frame.iloc[0].copy()
    original_record = SchoolRecord.from_dataframe_row(source_row)
    working_record = replace(original_record)
    finding = ResearchFinding(
        website_url="https://unverified.example",  # not official
        contact_person="Test Contact",
        contact_email="contact@example.net",
        contact_phone="011 555 0100",
        sources=["https://directory.example.net/listing"],
        notes="Single directory source",
        confidence=25,
    )
    request = RowProcessingRequest(
        row_id=2,
        original_row=source_row,
        original_record=original_record,
        working_record=working_record,
        finding=finding,
    )
    gate = QualityGate(min_confidence=80, require_official_source=True)

    result = process_row(request, quality_gate=gate)

    assert result.quality_rejected is True
    assert result.rollback_action is not None
    assert result.quality_issues
    assert result.evidence_record is not None
    assert "Quality gate rejected" in result.evidence_record.notes
    # Notes and rollback columns should be deterministically ordered
    assert result.rollback_action.columns == sorted(result.rollback_action.columns)
    repeated_summary = describe_changes(source_row, result.proposed_record)
    assert repeated_summary == describe_changes(source_row, result.proposed_record)
    rejection_notes = compose_quality_rejection_notes(
        "insufficient evidence",
        repeated_summary,
        [QualityFinding(code="x", severity="block", message="m", remediation="r")],
        ["Sanity note B", "Sanity note A"],
    )
    assert "Sanity note A" in rejection_notes
    assert "Sanity note B" in rejection_notes


def test_pipeline_bulk_updates_preserve_string_dtype(
    typed_bulk_frame: pd.DataFrame,
) -> None:
    findings: dict[str, ResearchFinding] = {}
    for idx, name in enumerate(typed_bulk_frame["Name of Organisation"].tolist()):
        slug = name.lower().replace(" ", "-")
        findings[name] = ResearchFinding(
            website_url=f"https://{slug}.za",  # ensures normalization adds https only once
            contact_person=f"Analyst {idx}",
            contact_email=f"{slug}@official.gov.za",
            contact_phone="+27 10 555 01{:02d}".format(idx),
            sources=[f"https://{slug}.za/about", "https://gov.za/register"],
            confidence=90,
        )

    adapter = StaticResearchAdapter(findings)
    pipe = Pipeline(
        research_adapter=adapter,
        quality_gate=QualityGate(min_confidence=0, require_official_source=False),
    )

    report = asyncio.run(pipe.run_dataframe_async(typed_bulk_frame.copy()))

    result_frame = report.refined_dataframe
    for column in typed_bulk_frame.columns:
        assert result_frame[column].dtype == typed_bulk_frame[column].dtype


def test_pipeline_sends_slack_alert_on_drift(tmp_path: Path, monkeypatch) -> None:
    baseline_path = tmp_path / "baseline.json"
    baseline_payload = {
        "status_counts": {"Candidate": 1},
        "province_counts": {"Gauteng": 1},
        "total_rows": 1,
    }
    baseline_path.write_text(json.dumps(baseline_payload), encoding="utf-8")

    baseline_meta_path = tmp_path / "baseline_meta.json"
    baseline_meta_payload = {
        "generated_at": "2025-01-01T00:00:00+00:00",
        "backend": "fallback",
        "status_counts": {"Candidate": 1},
        "province_counts": {"Gauteng": 1},
        "total_rows": 1,
        "profile_path": str(tmp_path / "baseline.whylogs"),
    }
    baseline_meta_path.write_text(json.dumps(baseline_meta_payload), encoding="utf-8")

    output_dir = tmp_path / "whylogs"
    alerts_path = tmp_path / "alerts.json"
    metrics_path = tmp_path / "metrics.prom"

    env_vars = {
        "DRIFT_BASELINE_PATH": str(baseline_path),
        "DRIFT_WHYLOGS_BASELINE": str(baseline_meta_path),
        "DRIFT_WHYLOGS_OUTPUT": str(output_dir),
        "DRIFT_ALERT_OUTPUT": str(alerts_path),
        "DRIFT_PROMETHEUS_OUTPUT": str(metrics_path),
        "DRIFT_SLACK_WEBHOOK": "https://hooks.slack.com/services/test",
        "DRIFT_DASHBOARD_URL": "https://grafana.example/dashboard",
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    config.configure()

    captured: dict[str, dict[str, str]] = {}

    def fake_send_slack_alert(**kwargs):
        captured["kwargs"] = kwargs
        return True

    monkeypatch.setattr(
        "firecrawl_demo.application.pipeline.send_slack_alert", fake_send_slack_alert
    )

    research_adapter = StaticResearchAdapter({})
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

    frame = pd.DataFrame(
        [
            {
                "Name of Organisation": "Example Flight School",
                "Province": "Western Cape",
                "Status": "Verified",
                "Website URL": "example.com",
                "Contact Person": "",
                "Contact Number": "",
                "Contact Email Address": "",
            }
        ]
    )
    context = LineageContext(
        run_id="run-drift-1",
        namespace="ns",
        job_name="enrichment",
        dataset_name="flight-schools",
        input_uri="file://input.csv",
    )

    report = asyncio.run(pipe.run_dataframe_async(frame, lineage_context=context))

    assert "kwargs" in captured
    assert captured["kwargs"]["dataset"] == "flight-schools"
    assert report.metrics.get("drift_alert_notifications") == 1

    for key in env_vars:
        monkeypatch.delenv(key, raising=False)
    config.configure()


def test_pipeline_records_email_issue_for_bare_domain() -> None:
    frame = pd.DataFrame(
        [
            {
                "Name of Organisation": "Bare Domain Flight",
                "Province": "Gauteng",
                "Status": "Candidate",
                "Website URL": "example.com",
                "Contact Person": "",
                "Contact Number": "",
                "Contact Email Address": "INFO@other.org",
            }
        ]
    )

    research_adapter = StaticResearchAdapter(
        {
            "Bare Domain Flight": ResearchFinding(
                sources=[
                    "https://www.caa.co.za/operators/bare-domain-flight",
                    "https://press.example.com/bare-domain-flight",
                ],
                confidence=80,
            )
        }
    )

    pipe = Pipeline(
        research_adapter=research_adapter,
        quality_gate=QualityGate(min_confidence=0, require_official_source=False),
    )

    report = asyncio.run(pipe.run_dataframe_async(frame))

    assert report.quality_issues
    email_issue = next(
        (issue for issue in report.quality_issues if issue.code == "invalid_email"),
        None,
    )
    assert email_issue is not None
    assert "Email domain does not match official domain" in email_issue.message


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
