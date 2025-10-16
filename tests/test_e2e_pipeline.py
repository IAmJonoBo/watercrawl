import pandas as pd
import pytest

from firecrawl_demo import config
from firecrawl_demo.pipeline import Pipeline
from firecrawl_demo.research import ResearchAdapter, ResearchFinding


class StubResearchAdapter(ResearchAdapter):
    def __init__(self, findings):
        self._findings = findings

    def lookup(self, organisation: str, province: str) -> ResearchFinding:
        try:
            return self._findings[organisation]
        except KeyError as exc:  # pragma: no cover - defensive
            raise LookupError(organisation) from exc


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
