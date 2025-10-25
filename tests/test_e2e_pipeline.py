import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from watercrawl.application.pipeline import Pipeline
from watercrawl.application.progress import PipelineProgressListener
from watercrawl.application.quality import QualityGate
from watercrawl.application.row_processing import (
    RowProcessingRequest,
    process_row,
)
from watercrawl.core import config
from watercrawl.domain.models import SchoolRecord
from watercrawl.integrations.adapters.research import (
    ResearchAdapter,
    ResearchFinding,
)
from watercrawl.integrations.telemetry.drift import (
    DriftBaseline,
    log_whylogs_profile,
    save_baseline,
)


class StubResearchAdapter(ResearchAdapter):
    def __init__(self, findings):
        self._findings = findings

    def lookup(self, organisation: str, province: str) -> ResearchFinding:
        try:
            return self._findings[organisation]
        except KeyError as exc:  # pragma: no cover - defensive
            raise LookupError(organisation) from exc

    async def lookup_async(self, organisation: str, province: str) -> ResearchFinding:
        return self.lookup(organisation, province)


class RecordingProgress(PipelineProgressListener):
    def __init__(self) -> None:
        self.events: list[tuple[object, ...]] = []

    def on_start(self, total_rows: int) -> None:
        self.events.append(("start", total_rows))

    def on_row_processed(
        self, index: int, updated: bool, record
    ) -> None:  # pragma: no cover - trivial pass-through
        self.events.append(("row", index, updated, record.name))

    def on_complete(self, metrics: Mapping[str, float | int]) -> None:
        self.events.append(("complete", dict(metrics)))

    def on_error(self, error: Exception, index: int | None = None) -> None:
        self.events.append(("error", index, str(error)))


def _dataset_row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "Name of Organisation": "",
        "Province": "",
        "Status": "",
        "Website URL": "",
        "Contact Person": "",
        "Contact Number": "",
        "Contact Email Address": "",
        "Fleet Size": "",
        "Runway Length": "",
        "Runway Length (m)": "",
    }
    base.update(overrides)
    return base


def test_process_row_accepts_valid_enrichment() -> None:
    row = pd.Series(
        _dataset_row(
            **{
                "Name of Organisation": "SkyReach Aero",
                "Province": "gauteng",
                "Status": "Candidate",
                "Website URL": "skyreachaero.co.za",
                "Contact Person": "",
                "Contact Number": "(011) 555 0100",
            }
        )
    )
    original_record = SchoolRecord.from_dataframe_row(row)
    request = RowProcessingRequest(
        row_id=2,
        original_row=row.to_dict(),
        original_record=original_record,
        working_record=replace(original_record),
        finding=ResearchFinding(
            website_url="https://www.skyreachaero.co.za",
            contact_person="Captain Neo Masuku",
            contact_email="neo.masuku@skyreachaero.co.za",
            contact_phone="011 555 0100",
            sources=[
                "https://www.skyreachaero.co.za/contact",
                "https://www.caa.co.za/operators/skyreachaero",
            ],
            notes="Directory + regulator corroboration",
            confidence=92,
        ),
    )
    gate = QualityGate(min_confidence=70, require_official_source=True)

    result = process_row(request, quality_gate=gate)

    assert result.quality_rejected is False
    assert result.updated is True
    assert result.record.website_url == "https://www.skyreachaero.co.za"
    assert result.record.status == "Verified"
    assert result.evidence_record is not None
    assert result.evidence_record.confidence >= 70
    assert not result.cleared_columns
    assert not result.sanity_findings


def test_pipeline_enriches_missing_fields():
    df = pd.DataFrame(
        [
            _dataset_row(
                **{
                    "Name of Organisation": "SkyReach Aero",
                    "Province": "gauteng",
                    "Status": "Candidate",
                    "Website URL": "",
                    "Contact Person": "",
                    "Contact Number": "(011) 555 0100",
                    "Contact Email Address": "",
                }
            )
        ]
    )

    adapter = StubResearchAdapter(
        {
            "SkyReach Aero": ResearchFinding(
                website_url="https://www.skyreachaero.co.za",
                contact_person="Captain Neo Masuku",
                contact_email="neo.masuku@skyreachaero.co.za",
                contact_phone="011 555 0100",
                sources=[
                    "https://www.skyreachaero.co.za/contact",
                    "https://www.caa.co.za/operators/skyreachaero",
                    "https://linkedin.com/company/skyreachaero",
                ],
                notes="Directory + LinkedIn cross-check",
                confidence=96,
            )
        }
    )

    pipeline = Pipeline(research_adapter=adapter)
    report = pipeline.run_dataframe(df)

    enriched = report.refined_dataframe
    assert enriched.loc[0, "Website URL"] == "https://www.skyreachaero.co.za"
    assert enriched.loc[0, "Contact Email Address"] == "neo.masuku@skyreachaero.co.za"
    assert enriched.loc[0, "Province"] == "Gauteng"
    assert enriched.loc[0, "Status"] == "Verified"

    assert report.metrics["enriched_rows"] == 1
    assert report.metrics["quality_rejections"] == 0
    assert report.rollback_plan is None
    assert report.evidence_log
    enriched_entries = [
        entry
        for entry in report.evidence_log
        if entry.confidence and entry.confidence >= 70
    ]
    assert enriched_entries, "Expected enriched evidence entry with confidence"
    enrichment = enriched_entries[0]
    assert enrichment.row_id == 2
    assert len(enrichment.sources) >= 2
    assert enrichment.confidence == 96
    assert any(entry.confidence == 0 for entry in report.evidence_log)


def test_pipeline_adds_remediation_note_for_sparse_evidence():
    df = pd.DataFrame(
        [
            _dataset_row(
                **{
                    "Name of Organisation": "Sparse Evidence Aero",
                    "Province": "Gauteng",
                    "Status": "Candidate",
                }
            )
        ]
    )

    adapter = StubResearchAdapter(
        {
            "Sparse Evidence Aero": ResearchFinding(
                contact_person="Ayanda Khumalo",
                sources=["https://directory.example.com/sparse-evidence"],
                confidence=72,
            )
        }
    )

    pipeline = Pipeline(research_adapter=adapter)
    report = pipeline.run_dataframe(df)

    evidence = report.evidence_log[0]
    assert "Quality gate rejected enrichment" in evidence.notes
    assert "two independent sources" in evidence.notes
    assert "official" in evidence.notes
    assert report.metrics["quality_rejections"] == 1
    assert report.quality_issues
    assert report.rollback_plan is not None


def test_pipeline_records_rebrand_investigation(monkeypatch):
    df = pd.DataFrame(
        [
            _dataset_row(
                **{
                    "Name of Organisation": "Legacy Flight School",
                    "Province": "Western Cape",
                    "Status": "Candidate",
                    "Website URL": "https://legacy-flight.co.za",
                    "Contact Number": "021 555 0199",
                }
            )
        ]
    )

    finding = ResearchFinding(
        website_url="https://newbrand.aero",
        contact_person="Nomsa Jacobs",
        contact_email="nomsa.jacobs@newbrand.aero",
        contact_phone="0215550199",
        sources=[
            "https://newbrand.aero/contact",
            "https://www.caa.co.za/operators/newbrand",
        ],
        notes="Regulator lists organisation under the new brand",
        confidence=90,
        investigation_notes=[
            "Regulator registry indicates Legacy Flight School now trades as NewBrand Aero (2024).",
        ],
        alternate_names=["Legacy Flight School"],
    )

    adapter = StubResearchAdapter({"Legacy Flight School": finding})
    flags = config.FeatureFlags(
        enable_firecrawl_sdk=False,
        enable_press_research=True,
        enable_regulator_lookup=True,
        enable_ml_inference=True,
        investigate_rebrands=True,
    )
    monkeypatch.setattr(config, "FEATURE_FLAGS", flags)

    pipeline = Pipeline(research_adapter=adapter)
    report = pipeline.run_dataframe(df)

    evidence = report.evidence_log[0]
    assert "newbrand" in evidence.notes.lower()
    assert "legacy flight school" in evidence.notes.lower()
    assert any("caa.co.za" in source for source in evidence.sources)


def test_pipeline_rejects_records_missing_required_columns():
    df = pd.DataFrame(
        [
            {
                "Name of Organisation": "Missing Fields Corp",
                "Province": "Western Cape",
            }
        ]
    )
    pipeline = Pipeline()

    with pytest.raises(ValueError) as exc:
        pipeline.run_dataframe(df)

    assert "Missing expected columns" in str(exc.value)


def test_pipeline_emits_progress_events():
    df = pd.DataFrame(
        [
            _dataset_row(
                **{
                    "Name of Organisation": "Event Horizon Aero",
                    "Province": "Gauteng",
                    "Status": "Candidate",
                }
            )
        ]
    )
    adapter = StubResearchAdapter(
        {
            "Event Horizon Aero": ResearchFinding(
                website_url="https://www.event-horizon.aero",
                contact_person="Sifiso Moyo",
                sources=[
                    "https://www.event-horizon.aero/contact",
                    "https://www.caa.co.za/operators/event-horizon",
                ],
                confidence=80,
            )
        }
    )

    listener = RecordingProgress()
    pipeline = Pipeline(research_adapter=adapter)
    report = pipeline.run_dataframe(df, progress=listener)

    assert report.metrics["enriched_rows"] == 1
    assert report.metrics["quality_rejections"] == 0
    assert listener.events[0] == ("start", 1)
    assert any(event[0] == "row" and event[2] is True for event in listener.events)
    assert listener.events[-1][0] == "complete"


def test_pipeline_tracks_adapter_failures_without_crash():
    class FailingAdapter(ResearchAdapter):
        def lookup(self, organisation: str, province: str) -> ResearchFinding:
            raise RuntimeError("adapter boom")

    df = pd.DataFrame(
        [
            _dataset_row(
                **{
                    "Name of Organisation": "Failure Flight",
                    "Province": "Gauteng",
                    "Status": "Candidate",
                }
            )
        ]
    )

    listener = RecordingProgress()
    pipeline = Pipeline(research_adapter=FailingAdapter())
    report = pipeline.run_dataframe(df, progress=listener)

    assert report.metrics["adapter_failures"] == 1
    assert report.metrics["quality_rejections"] == 0
    assert any(event[0] == "error" for event in listener.events)
    # Fallback should keep dataset intact when enrichment fails.
    assert report.refined_dataframe.loc[0, "Name of Organisation"] == "Failure Flight"


def test_pipeline_auto_remediates_sanity_issues():
    df = pd.DataFrame(
        [
            _dataset_row(
                **{
                    "Name of Organisation": "Sanity Check Flight",
                    "Status": "Candidate",
                    "Website URL": "acesaero.co.za",
                    "Contact Number": "555-INVALID",
                    "Contact Email Address": "bad-email",
                }
            )
        ]
    )

    adapter = StubResearchAdapter({"Sanity Check Flight": ResearchFinding()})
    pipeline = Pipeline(research_adapter=adapter)
    report = pipeline.run_dataframe(df)

    enriched = report.refined_dataframe
    assert enriched.loc[0, "Website URL"] == "https://acesaero.co.za"
    assert enriched.loc[0, "Province"] == "Unknown"
    assert enriched.loc[0, "Contact Email Address"] == ""
    assert enriched.loc[0, "Contact Number"] == ""

    issues = {finding.issue for finding in report.sanity_findings}
    assert "website_url_missing_scheme" in issues
    assert "contact_email_invalid" in issues
    assert "contact_number_invalid" in issues
    assert "province_unknown" in issues

    assert report.metrics["sanity_issues"] >= 4


def test_pipeline_reports_duplicate_names_in_sanity_findings():
    df = pd.DataFrame(
        [
            _dataset_row(
                **{
                    "Name of Organisation": "Duplicate Aero",
                    "Province": "Gauteng",
                    "Status": "Candidate",
                }
            ),
            _dataset_row(
                **{
                    "Name of Organisation": "Duplicate Aero",
                    "Province": "Western Cape",
                    "Status": "Candidate",
                }
            ),
        ]
    )

    adapter = StubResearchAdapter({"Duplicate Aero": ResearchFinding()})
    pipeline = Pipeline(research_adapter=adapter)
    report = pipeline.run_dataframe(df)

    duplicate_findings = [
        finding
        for finding in report.sanity_findings
        if finding.issue == "duplicate_organisation"
    ]
    assert duplicate_findings, "Expected duplicate organisation sanity findings"
    assert {finding.row_id for finding in duplicate_findings} == {2, 3}
    assert report.metrics["quality_rejections"] == 0


def test_pipeline_surfaces_drift_baseline_missing(monkeypatch, tmp_path):
    df = pd.DataFrame(
        [
            _dataset_row(
                **{
                    "Name of Organisation": "Baseline Check Aero",
                    "Province": "Gauteng",
                    "Status": "Candidate",
                }
            )
        ]
    )

    adapter = StubResearchAdapter({"Baseline Check Aero": ResearchFinding()})
    missing_baseline = tmp_path / "missing_baseline.json"
    patched_settings = replace(
        config.DRIFT,
        baseline_path=missing_baseline,
        whylogs_baseline_path=None,
        require_baseline=True,
        require_whylogs_metadata=True,
    )
    monkeypatch.setattr(config, "DRIFT", patched_settings)

    pipeline = Pipeline(research_adapter=adapter)
    report = pipeline.run_dataframe(df)

    issues = {finding.issue for finding in report.sanity_findings}
    assert "drift_baseline_missing" in issues
    assert report.metrics.get("drift_missing_baseline", 0) == 1


def test_pipeline_flags_missing_whylogs_metadata(monkeypatch, tmp_path):
    df = pd.DataFrame(
        [
            _dataset_row(
                **{
                    "Name of Organisation": "Baseline Check Aero",
                    "Province": "Gauteng",
                    "Status": "Candidate",
                }
            )
        ]
    )

    adapter = StubResearchAdapter({"Baseline Check Aero": ResearchFinding()})
    baseline_path = tmp_path / "baseline.json"
    save_baseline(
        DriftBaseline(
            status_counts={"Candidate": 1},
            province_counts={"Gauteng": 1},
            total_rows=1,
        ),
        baseline_path,
    )
    missing_metadata = tmp_path / "missing_meta.json"
    patched_settings = replace(
        config.DRIFT,
        baseline_path=baseline_path,
        whylogs_baseline_path=missing_metadata,
        require_baseline=True,
        require_whylogs_metadata=True,
        whylogs_output_dir=tmp_path,
    )
    monkeypatch.setattr(config, "DRIFT", patched_settings)

    pipeline = Pipeline(research_adapter=adapter)
    report = pipeline.run_dataframe(df)

    issues = {finding.issue for finding in report.sanity_findings}
    assert "whylogs_baseline_missing" in issues


def test_pipeline_writes_drift_dashboard_outputs(monkeypatch, tmp_path):
    baseline_frame = pd.DataFrame(
        [
            _dataset_row(
                **{
                    "Name of Organisation": "Baseline Org",
                    "Province": "Gauteng",
                    "Status": "Verified",
                }
            ),
            _dataset_row(
                **{
                    "Name of Organisation": "Baseline Org 2",
                    "Province": "Gauteng",
                    "Status": "Verified",
                }
            ),
        ]
    )
    observed_frame = pd.DataFrame(
        [
            _dataset_row(
                **{
                    "Name of Organisation": "Observed Org",
                    "Province": "Gauteng",
                    "Status": "Candidate",
                }
            ),
            _dataset_row(
                **{
                    "Name of Organisation": "Observed Org 2",
                    "Province": "Western Cape",
                    "Status": "Candidate",
                }
            ),
        ]
    )

    baseline_path = tmp_path / "baseline.json"
    save_baseline(
        DriftBaseline(
            status_counts={"Verified": 2},
            province_counts={"Gauteng": 2},
            total_rows=2,
        ),
        baseline_path,
    )
    baseline_profile = log_whylogs_profile(
        baseline_frame, tmp_path / "baseline_profile.bin"
    )
    patched_settings = replace(
        config.DRIFT,
        baseline_path=baseline_path,
        whylogs_baseline_path=baseline_profile.metadata_path,
        whylogs_output_dir=tmp_path / "profiles",
        alert_output_path=tmp_path / "alerts.json",
        prometheus_output_path=tmp_path / "metrics.prom",
        threshold=0.05,
    )
    monkeypatch.setattr(config, "DRIFT", patched_settings)

    adapter = StubResearchAdapter(
        {
            "Observed Org": ResearchFinding(),
            "Observed Org 2": ResearchFinding(),
        }
    )
    pipeline = Pipeline(research_adapter=adapter)
    report = pipeline.run_dataframe(observed_frame)
    assert report.drift_report is not None
    assert report.metrics.get("drift_alerts", 0) > 0

    alert_payload = json.loads(
        (patched_settings.alert_output_path).read_text(encoding="utf-8")
    )
    assert alert_payload, "Expected drift alert log entry"
    latest_alert = alert_payload[-1]
    assert latest_alert["dataset"] == config.LINEAGE.dataset_name
    assert latest_alert["status_drift"]

    metrics_content = patched_settings.prometheus_output_path.read_text(
        encoding="utf-8"
    )
    assert "whylogs_drift_alerts_total" in metrics_content
    assert "whylogs_drift_exceeded_threshold" in metrics_content


def test_pipeline_blocks_low_quality_adapter_updates():
    df = pd.DataFrame(
        [
            _dataset_row(
                **{
                    "Name of Organisation": "Hallucinated Aero",
                    "Province": "KwaZulu-Natal",
                    "Status": "Candidate",
                }
            )
        ]
    )

    adapter = StubResearchAdapter(
        {
            "Hallucinated Aero": ResearchFinding(
                website_url="https://totally-not-real.biz",
                contact_person="Fabricated Pilot",
                contact_email="pilot@totally-not-real.biz",
                contact_phone="021 555 0987",
                sources=["https://random-directory.example.com/hallucinated"],
                notes="Single directory listing with no corroboration",
                confidence=24,
            )
        }
    )

    pipeline = Pipeline(research_adapter=adapter)
    report = pipeline.run_dataframe(df)

    refined = report.refined_dataframe
    # Website and contacts should remain blank because the adapter output was rejected.
    assert refined.loc[0, "Website URL"] == ""
    assert refined.loc[0, "Contact Email Address"] == ""
    assert refined.loc[0, "Contact Number"] == ""
    # Row should be flagged for follow-up.
    assert refined.loc[0, "Status"] == "Needs Review"

    assert report.metrics["enriched_rows"] == 0
    assert report.metrics["quality_rejections"] == 1

    # Quality issues surface detailed context for analysts.
    assert report.quality_issues, "Expected quality issues for rejected enrichment"
    rejection = report.quality_issues[0]
    assert "Hallucinated Aero" in rejection.organisation
    assert rejection.severity == "block"
    messages = " ".join(issue.message.lower() for issue in report.quality_issues)
    assert "official" in messages
    assert "source" in messages

    # Rollback plan captures how to restore attempted changes.
    assert report.rollback_plan is not None
    action = report.rollback_plan.actions[0]
    assert action.organisation == "Hallucinated Aero"
    assert "Website URL" in action.columns
    assert "Contact Email Address" in action.columns
    assert "official" in action.reason.lower()

    # Evidence log should document the rejection for audit trails.
    assert report.evidence_log
    log_entry = report.evidence_log[0]
    assert "quality gate" in log_entry.notes.lower()


def test_pipeline_rejects_updates_without_fresh_sources():
    df = pd.DataFrame(
        [
            _dataset_row(
                **{
                    "Name of Organisation": "Stale Evidence Aero",
                    "Province": "Gauteng",
                    "Status": "Candidate",
                    "Website URL": "https://www.staleevidence.gov.za",
                }
            )
        ]
    )

    adapter = StubResearchAdapter(
        {
            "Stale Evidence Aero": ResearchFinding(
                contact_person="Speculative Lead",
                sources=["https://www.staleevidence.gov.za/about"],
                notes="No new corroborating evidence, reused existing site",
                confidence=92,
            )
        }
    )

    pipeline = Pipeline(research_adapter=adapter)
    report = pipeline.run_dataframe(df)

    refined = report.refined_dataframe
    assert refined.loc[0, "Contact Person"] == ""
    assert refined.loc[0, "Status"] == "Needs Review"

    assert report.metrics["quality_rejections"] == 1
    assert report.metrics["enriched_rows"] == 0

    assert report.rollback_plan is not None
    action = report.rollback_plan.actions[0]
    assert action.organisation == "Stale Evidence Aero"
    assert "Contact Person" in action.columns
    assert "fresh" in action.reason.lower()

    assert report.quality_issues
    messages = " ".join(issue.message.lower() for issue in report.quality_issues)
    assert "fresh" in messages
    assert "official" in messages

    assert report.evidence_log
    notes = report.evidence_log[0].notes.lower()
    assert "fresh" in notes
    assert "quality gate" in notes


@pytest.mark.asyncio
async def test_pipeline_run_dataframe_async():
    df = pd.DataFrame(
        [
            _dataset_row(
                **{
                    "Name of Organisation": "SkyReach Aero",
                    "Province": "gauteng",
                    "Status": "Candidate",
                    "Contact Number": "(011) 555 0100",
                }
            )
        ]
    )

    adapter = StubResearchAdapter(
        {
            "SkyReach Aero": ResearchFinding(
                website_url="https://www.skyreachaero.co.za",
                contact_person="Captain Neo Masuku",
                contact_email="neo.masuku@skyreachaero.co.za",
                contact_phone="011 555 0100",
                sources=[
                    "https://www.skyreachaero.co.za/contact",
                    "https://www.caa.co.za/operators/skyreachaero",
                    "https://linkedin.com/company/skyreachaero",
                ],
                notes="Directory + LinkedIn cross-check",
                confidence=96,
            )
        }
    )

    pipeline = Pipeline(research_adapter=adapter)
    report = await pipeline.run_dataframe_async(df)

    enriched = report.refined_dataframe
    assert enriched.loc[0, "Website URL"] == "https://www.skyreachaero.co.za"
    assert enriched.loc[0, "Contact Email Address"] == "neo.masuku@skyreachaero.co.za"
    assert enriched.loc[0, "Status"] == "Verified"
    assert report.metrics["enriched_rows"] == 1


@pytest.mark.asyncio
async def test_pipeline_run_file_async(tmp_path: Path):
    input_path = tmp_path / "async-input.csv"
    df = pd.DataFrame(
        [
            _dataset_row(
                **{
                    "Name of Organisation": "Async File School",
                    "Province": "Western Cape",
                    "Status": "Candidate",
                    "Contact Number": "021 555 0100",
                }
            )
        ]
    )
    df.to_csv(input_path, index=False)

    adapter = StubResearchAdapter(
        {
            "Async File School": ResearchFinding(
                website_url="https://async-file.aero",
                contact_person="Zinhle Samuels",
                contact_email="zinhle.samuels@async-file.aero",
                contact_phone="021 555 0100",
                sources=[
                    "https://async-file.aero/contact",
                    "https://caa.co.za/operators/async-file",
                ],
                notes="Firecrawl + regulator insight",
                confidence=90,
            )
        }
    )

    pipeline = Pipeline(research_adapter=adapter)
    output_path = tmp_path / "async-output.csv"
    report = await pipeline.run_file_async(input_path, output_path)

    assert output_path.exists()
    saved = pd.read_csv(output_path)
    assert saved.loc[0, "Website URL"] == "https://async-file.aero"
    assert report.metrics["enriched_rows"] == 1
