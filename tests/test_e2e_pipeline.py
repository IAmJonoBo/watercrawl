from collections.abc import Mapping

import pandas as pd
import pytest

from firecrawl_demo import config
from firecrawl_demo.pipeline import Pipeline
from firecrawl_demo.progress import PipelineProgressListener
from firecrawl_demo.research import ResearchAdapter, ResearchFinding


class StubResearchAdapter(ResearchAdapter):
    def __init__(self, findings):
        self._findings = findings

    def lookup(self, organisation: str, province: str) -> ResearchFinding:
        try:
            return self._findings[organisation]
        except KeyError as exc:  # pragma: no cover - defensive
            raise LookupError(organisation) from exc


class RecordingProgress(PipelineProgressListener):
    def __init__(self) -> None:
        self.events: list[tuple[object, ...]] = []

    def on_start(self, total_rows: int) -> None:
        self.events.append(("start", total_rows))

    def on_row_processed(
        self, index: int, updated: bool, record
    ) -> None:  # pragma: no cover - trivial pass-through
        self.events.append(("row", index, updated, record.name))

    def on_complete(self, metrics: Mapping[str, int]) -> None:
        self.events.append(("complete", dict(metrics)))

    def on_error(self, error: Exception, index: int | None = None) -> None:
        self.events.append(("error", index, str(error)))


def test_pipeline_enriches_missing_fields():
    df = pd.DataFrame(
        [
            {
                "Name of Organisation": "SkyReach Aero",
                "Province": "gauteng",
                "Status": "Candidate",
                "Website URL": "",
                "Contact Person": "",
                "Contact Number": "(011) 555 0100",
                "Contact Email Address": "",
            }
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
    assert len(report.evidence_log) == 1
    entry = report.evidence_log[0]
    assert entry.row_id == 2
    assert len(entry.sources) >= 2
    assert entry.confidence == 96


def test_pipeline_adds_remediation_note_for_sparse_evidence():
    df = pd.DataFrame(
        [
            {
                "Name of Organisation": "Sparse Evidence Aero",
                "Province": "Gauteng",
                "Status": "Candidate",
                "Website URL": "",
                "Contact Person": "",
                "Contact Number": "",
                "Contact Email Address": "",
            }
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
    assert "Evidence shortfall" in evidence.notes
    assert "second independent source" in evidence.notes
    assert "official" in evidence.notes


def test_pipeline_records_rebrand_investigation(monkeypatch):
    df = pd.DataFrame(
        [
            {
                "Name of Organisation": "Legacy Flight School",
                "Province": "Western Cape",
                "Status": "Candidate",
                "Website URL": "https://legacy-flight.co.za",
                "Contact Person": "",
                "Contact Number": "021 555 0199",
                "Contact Email Address": "",
            }
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
            {
                "Name of Organisation": "Event Horizon Aero",
                "Province": "Gauteng",
                "Status": "Candidate",
                "Website URL": "",
                "Contact Person": "",
                "Contact Number": "",
                "Contact Email Address": "",
            }
        ]
    )
    adapter = StubResearchAdapter(
        {
            "Event Horizon Aero": ResearchFinding(
                website_url="https://www.event-horizon.aero",
                contact_person="Sifiso Moyo",
                sources=["https://www.event-horizon.aero/contact"],
                confidence=80,
            )
        }
    )

    listener = RecordingProgress()
    pipeline = Pipeline(research_adapter=adapter)
    report = pipeline.run_dataframe(df, progress=listener)

    assert report.metrics["enriched_rows"] == 1
    assert listener.events[0] == ("start", 1)
    assert any(event[0] == "row" and event[2] is True for event in listener.events)
    assert listener.events[-1][0] == "complete"


def test_pipeline_tracks_adapter_failures_without_crash():
    class FailingAdapter(ResearchAdapter):
        def lookup(self, organisation: str, province: str) -> ResearchFinding:
            raise RuntimeError("adapter boom")

    df = pd.DataFrame(
        [
            {
                "Name of Organisation": "Failure Flight",
                "Province": "Gauteng",
                "Status": "Candidate",
                "Website URL": "",
                "Contact Person": "",
                "Contact Number": "",
                "Contact Email Address": "",
            }
        ]
    )

    listener = RecordingProgress()
    pipeline = Pipeline(research_adapter=FailingAdapter())
    report = pipeline.run_dataframe(df, progress=listener)

    assert report.metrics["adapter_failures"] == 1
    assert any(event[0] == "error" for event in listener.events)
    # Fallback should keep dataset intact when enrichment fails.
    assert report.refined_dataframe.loc[0, "Name of Organisation"] == "Failure Flight"
