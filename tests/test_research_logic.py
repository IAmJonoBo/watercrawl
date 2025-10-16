import pytest

from firecrawl_demo import config
from firecrawl_demo import research
from firecrawl_demo.research import (
    ResearchAdapter,
    ResearchFinding,
    TriangulatingResearchAdapter,
)
from firecrawl_demo.external_sources import triangulate_organisation


class DummyAdapter(ResearchAdapter):
    def __init__(self, finding: ResearchFinding) -> None:
        self._finding = finding

    def lookup(self, organisation: str, province: str) -> ResearchFinding:
        assert organisation
        assert province
        return self._finding


def test_triangulating_adapter_merges_sources_and_notes():
    base_finding = ResearchFinding(
        website_url=None,
        contact_person=None,
        contact_email=None,
        contact_phone=None,
        sources=["https://existing.example.com"],
        notes="Base note",
        confidence=55,
    )

    def fake_triangulate(
        organisation: str, province: str, baseline: ResearchFinding
    ) -> ResearchFinding:
        assert organisation == "Example Flight Academy"
        assert province == "Gauteng"
        assert baseline is base_finding
        return ResearchFinding(
            website_url="https://triangulated.example.com",
            contact_person="New Investigator",
            contact_email="intel@example.com",
            contact_phone="0115550100",
            sources=[
                "https://regulator.example.com/example-flight-academy",
                "https://press.example.com/rebrand",
            ],
            notes="Regulator and press corroboration",
            confidence=88,
            alternate_names=["Example Flight Academy"],
            investigation_notes=[
                "Press coverage indicates a 2024 rebrand to Example Flight Academy.",
            ],
        )

    adapter = TriangulatingResearchAdapter(
        base_adapter=DummyAdapter(base_finding),
        triangulate=fake_triangulate,
    )

    result = adapter.lookup("Example Flight Academy", "Gauteng")

    assert result.website_url == "https://triangulated.example.com"
    assert result.contact_person == "New Investigator"
    assert result.contact_email == "intel@example.com"
    assert result.contact_phone == "+27115550100"
    assert sorted(result.sources) == sorted(
        [
            "https://existing.example.com",
            "https://regulator.example.com/example-flight-academy",
            "https://press.example.com/rebrand",
        ]
    )
    assert "Regulator" in result.notes
    assert any("rebrand" in note.lower() for note in result.investigation_notes)
    assert "Example Flight Academy" in result.alternate_names
    assert result.confidence == 88


@pytest.mark.parametrize("enable_firecrawl", [True, False])
def test_build_research_adapter_handles_missing_firecrawl(
    monkeypatch, enable_firecrawl
):
    flags = config.FeatureFlags(
        enable_firecrawl_sdk=enable_firecrawl,
        enable_press_research=True,
        enable_regulator_lookup=True,
        investigate_rebrands=True,
    )
    monkeypatch.setattr(research.config, "FEATURE_FLAGS", flags)

    adapter = research.build_research_adapter()

    finding = adapter.lookup("Nonexistent Org", "Gauteng")
    assert isinstance(finding, ResearchFinding)
    assert finding.sources == []


def test_triangulate_organisation_merges_live_sources(monkeypatch):
    from firecrawl_demo import external_sources

    monkeypatch.setattr(config, "ALLOW_NETWORK_RESEARCH", True)

    def fake_regulator(_: str) -> dict[str, object]:
        return {
            "officialWebsite": "https://newbrand.aero",
            "contactPerson": "Nomsa Jacobs",
            "contactEmail": "nomsa.jacobs@newbrand.aero",
            "contactPhone": "0215550199",
            "address": "Cape Town International Airport",
            "source": "https://www.caa.co.za/operators/newbrand",
            "knownAliases": ["Legacy Flight School"],
            "ownershipChange": "Registry indicates rename in 2024",
        }

    def fake_directory(_: str) -> dict[str, object]:
        return {
            "results": [
                {
                    "website": "https://directory.newbrand.aero",
                    "contact": "Operations Desk",
                    "email": "ops@newbrand.aero",
                    "phone": "0215550199",
                }
            ]
        }

    def fake_press(_: str) -> dict[str, object]:
        return {
            "articles": [
                {
                    "url": "https://press.example.com/newbrand-rebrands",
                    "title": "Legacy Flight School rebrands as NewBrand Aero",
                    "summary": "Acquisition-driven rebrand confirmed by SACAA records.",
                }
            ]
        }

    monkeypatch.setattr(external_sources, "query_regulator_api", fake_regulator)
    monkeypatch.setattr(
        external_sources, "query_professional_directory", fake_directory
    )
    monkeypatch.setattr(external_sources, "query_press", fake_press)

    baseline = ResearchFinding(website_url="https://legacy-flight.co.za")
    result = triangulate_organisation(
        "Legacy Flight School",
        "Western Cape",
        baseline,
        include_press=True,
        include_regulator=True,
        investigate_rebrands=True,
    )

    assert result.website_url == "https://newbrand.aero"
    assert "+27215550199" == result.contact_phone
    assert any("caa.co.za" in source for source in result.sources)
    assert any("rebrand" in note.lower() for note in result.investigation_notes)
    assert result.physical_address == "Cape Town International Airport"
