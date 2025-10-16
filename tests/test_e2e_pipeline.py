import pandas as pd  # type: ignore[import-untyped]
import pytest

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
