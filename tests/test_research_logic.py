from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from typing import Callable

import pytest

from firecrawl_demo.core import config
from firecrawl_demo.core.external_sources import triangulate_organisation
from firecrawl_demo.governance.secrets import EnvSecretsProvider
from firecrawl_demo.integrations.adapters import research
from firecrawl_demo.integrations.adapters.research import (
    AdapterLoaderSettings,
    NullResearchAdapter,
    ResearchAdapter,
    ResearchFinding,
    TriangulatingResearchAdapter,
    load_enabled_adapters,
    merge_findings,
    register_adapter,
)
from firecrawl_demo.integrations.adapters.research import registry as research_registry


class _DummyLoop:
    def __init__(self) -> None:
        self.executor: object | None = None
        self.calls: list[tuple[Callable[..., object], tuple[object, ...]]] = []

    async def run_in_executor(
        self, executor: object | None, func: Callable[..., object], *args: object
    ) -> object:
        self.executor = executor
        self.calls.append((func, args))
        return func(*args)


class DummyAdapter(ResearchAdapter):
    def __init__(self, finding: ResearchFinding) -> None:
        self._finding = finding

    def lookup(self, organisation: str, province: str) -> ResearchFinding:
        assert organisation
        assert province
        return self._finding


def test_load_enabled_adapters_preserves_order_and_deduplicates(monkeypatch):
    register_adapter(
        "alpha",
        lambda ctx: DummyAdapter(ResearchFinding(notes="alpha")),
    )
    register_adapter(
        "beta",
        lambda ctx: DummyAdapter(ResearchFinding(notes="beta")),
    )

    adapters = load_enabled_adapters(
        AdapterLoaderSettings(sequence=["alpha", "beta", "alpha", "null"])
    )

    lookups = [adapter.lookup("Org", "GP") for adapter in adapters]
    assert [finding.notes for finding in lookups] == ["alpha", "beta", ""]
    assert isinstance(adapters[-1], NullResearchAdapter)


def test_load_enabled_adapters_reads_env_configuration(monkeypatch):
    register_adapter(
        "alpha",
        lambda ctx: DummyAdapter(ResearchFinding(notes="alpha")),
    )
    register_adapter(
        "gamma",
        lambda ctx: DummyAdapter(ResearchFinding(notes="gamma")),
    )
    provider = EnvSecretsProvider({"RESEARCH_ADAPTERS": "gamma, alpha, null"})

    adapters = load_enabled_adapters(AdapterLoaderSettings(provider=provider))
    notes = [adapter.lookup("Org", "GP").notes for adapter in adapters]
    assert notes[:2] == ["gamma", "alpha"]


def test_load_enabled_adapters_reads_yaml_configuration(tmp_path):
    register_adapter(
        "delta",
        lambda ctx: DummyAdapter(ResearchFinding(notes="delta")),
    )
    config_path = tmp_path / "adapters.yaml"
    config_path.write_text("adapters:\n  - delta\n  - null\n", encoding="utf-8")
    provider = EnvSecretsProvider({"RESEARCH_ADAPTERS_FILE": str(config_path)})

    adapters = load_enabled_adapters(AdapterLoaderSettings(provider=provider))

    assert isinstance(adapters[0], DummyAdapter)
    assert adapters[0].lookup("Org", "GP").notes == "delta"
    assert isinstance(adapters[1], NullResearchAdapter)


def test_firecrawl_factory_respects_feature_flags(monkeypatch):
    flags = config.FeatureFlags(
        enable_crawlkit=False,
        enable_press_research=True,
        enable_regulator_lookup=True,
        enable_ml_inference=True,
        investigate_rebrands=True,
    )
    monkeypatch.setattr(config, "FEATURE_FLAGS", flags)

    adapters = load_enabled_adapters(
        AdapterLoaderSettings(sequence=["firecrawl", "null"])
    )

    assert all(
        not isinstance(adapter, research.CrawlkitResearchAdapter)
        for adapter in adapters
    )
    assert any(isinstance(adapter, NullResearchAdapter) for adapter in adapters)


def test_firecrawl_factory_activates_when_feature_enabled(monkeypatch):
    dummy_adapter = DummyAdapter(ResearchFinding(notes="firecrawl"))
    monkeypatch.setattr(
        research_registry,
        "_build_firecrawl_adapter",
        lambda: dummy_adapter,
    )

    flags = config.FeatureFlags(
        enable_crawlkit=True,
        enable_press_research=True,
        enable_regulator_lookup=True,
        enable_ml_inference=True,
        investigate_rebrands=True,
    )
    monkeypatch.setattr(config, "FEATURE_FLAGS", flags)

    adapters = load_enabled_adapters(
        AdapterLoaderSettings(sequence=["firecrawl", "null"])
    )

    assert adapters[0] is dummy_adapter
    assert isinstance(adapters[1], NullResearchAdapter)


def test_default_sequence_defers_firecrawl_until_opt_in(monkeypatch):
    called = False

    def _tracking_factory() -> ResearchAdapter:
        nonlocal called
        called = True
        return DummyAdapter(ResearchFinding(notes="firecrawl"))

    monkeypatch.setattr(
        research_registry,
        "_build_firecrawl_adapter",
        _tracking_factory,
    )

    adapters = load_enabled_adapters(AdapterLoaderSettings())

    assert not called, "Crawlkit factory should not run without explicit opt-in"
    assert all(
        not isinstance(adapter, research.CrawlkitResearchAdapter)
        for adapter in adapters
    )
    assert isinstance(adapters[-1], NullResearchAdapter)


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


@pytest.mark.asyncio()
async def test_lookup_with_adapter_async_uses_adapter_executor(monkeypatch) -> None:
    loop = _DummyLoop()
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: loop)

    class SyncAdapter(ResearchAdapter):
        def __init__(self) -> None:
            self.calls = 0

        def lookup(self, organisation: str, province: str) -> ResearchFinding:
            self.calls += 1
            return ResearchFinding(notes="ok")

    adapter = SyncAdapter()
    sentinel_executor = object()
    setattr(adapter, "_lookup_executor", sentinel_executor)

    result = await research.lookup_with_adapter_async(adapter, "Org", "GP")

    assert result.notes == "ok"
    assert adapter.calls == 1
    assert loop.executor is sentinel_executor
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


@pytest.mark.parametrize("enable_crawlkit", [True, False])
def test_build_research_adapter_handles_missing_crawlkit(monkeypatch, enable_crawlkit):
    flags = config.FeatureFlags(
        enable_crawlkit=enable_crawlkit,
        enable_press_research=True,
        enable_regulator_lookup=True,
        enable_ml_inference=True,
        investigate_rebrands=True,
    )
    monkeypatch.setattr(config, "FEATURE_FLAGS", flags)

    adapter = research.build_research_adapter()

    finding = adapter.lookup("Nonexistent Org", "Gauteng")
    assert isinstance(finding, ResearchFinding)
    assert finding.sources == []


def test_triangulate_organisation_merges_live_sources(monkeypatch):
    from firecrawl_demo.core import external_sources

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


def test_exemplar_adapters_enrich_from_registry(monkeypatch):
    flags = config.FeatureFlags(
        enable_crawlkit=False,
        enable_press_research=True,
        enable_regulator_lookup=True,
        enable_ml_inference=True,
        investigate_rebrands=True,
    )
    monkeypatch.setattr(config, "FEATURE_FLAGS", flags)

    provider = EnvSecretsProvider({"RESEARCH_ADAPTERS": "regulator, press, ml"})

    adapters = load_enabled_adapters(AdapterLoaderSettings(provider=provider))

    names = {adapter.__class__.__name__ for adapter in adapters}
    assert names == {
        "RegulatorRegistryAdapter",
        "PressMonitoringAdapter",
        "MLInferenceAdapter",
    }

    findings = [
        adapter.lookup("Legacy Flight School", "Western Cape") for adapter in adapters
    ]
    merged = merge_findings(*findings)

    assert merged.website_url == "https://legacy-flight.example.za"
    assert merged.contact_person == "Nomsa Jacobs"
    assert merged.contact_email == "nomsa.jacobs@legacy-flight.example.za"
    assert merged.contact_phone == "+27215550123"
    assert len(merged.sources) >= 3
    assert any("regulator" in note.lower() for note in merged.notes.split("; "))
    assert any(
        "press" in note.lower() or "coverage" in note.lower()
        for note in merged.investigation_notes
    )


@pytest.mark.asyncio()
async def test_composite_adapter_lookup_async_combines_findings() -> None:
    adapter = research.CompositeResearchAdapter(
        (
            DummyAdapter(ResearchFinding(contact_person="Nomsa")),
            DummyAdapter(
                ResearchFinding(
                    contact_email="info@example.org",
                    sources=["https://example.org/profile"],
                )
            ),
        )
    )

    result = await adapter.lookup_async("Example Org", "Gauteng")
    assert result.contact_person == "Nomsa"
    assert result.contact_email == "info@example.org"
    assert "https://example.org/profile" in result.sources


@pytest.mark.asyncio()
async def test_lookup_with_adapter_async_prefers_async_method() -> None:
    class AsyncAdapter:
        async def lookup_async(
            self, organisation: str, province: str
        ) -> ResearchFinding:
            assert organisation and province
            return ResearchFinding(notes="async-path")

        def lookup(
            self, organisation: str, province: str
        ) -> ResearchFinding:  # pragma: no cover
            raise AssertionError("Synchronous lookup should not be used")

    result = await research.lookup_with_adapter_async(AsyncAdapter(), "Org", "GP")
    assert result.notes == "async-path"


@pytest.mark.asyncio()
async def test_lookup_with_adapter_async_wraps_sync_adapter() -> None:
    class SyncAdapter:
        def __init__(self) -> None:
            self.called = False

        def lookup(self, organisation: str, province: str) -> ResearchFinding:
            self.called = True
            return ResearchFinding(notes="sync-path")

    adapter = SyncAdapter()
    result = await research.lookup_with_adapter_async(adapter, "Org", "GP")
    assert adapter.called
    assert result.notes == "sync-path"


def test_crawlkit_research_adapter_respects_feature_flag(monkeypatch) -> None:
    flags = config.FeatureFlags(
        enable_crawlkit=False,
        enable_press_research=True,
        enable_regulator_lookup=True,
        enable_ml_inference=True,
        investigate_rebrands=True,
    )
    monkeypatch.setattr(config, "FEATURE_FLAGS", flags)
    monkeypatch.setattr(config, "ALLOW_NETWORK_RESEARCH", True)

    adapter = research.CrawlkitResearchAdapter()
    result = adapter.lookup("Example Org", "Gauteng")
    assert "disabled by feature flag" in result.notes


def test_crawlkit_research_adapter_blocks_when_network_disabled(monkeypatch) -> None:
    flags = config.FeatureFlags(
        enable_crawlkit=True,
        enable_press_research=True,
        enable_regulator_lookup=True,
        enable_ml_inference=True,
        investigate_rebrands=True,
    )
    monkeypatch.setattr(config, "FEATURE_FLAGS", flags)
    monkeypatch.setattr(config, "ALLOW_NETWORK_RESEARCH", False)

    calls: list[str] = []

    def seed(_: str, __: str) -> tuple[ResearchFinding, list[str]]:  # pragma: no cover
        calls.append("seed")
        return ResearchFinding(), ["https://example.org"]

    adapter = research.CrawlkitResearchAdapter(seed_url_provider=seed)
    result = adapter.lookup("Example Org", "Gauteng")
    assert "network research disabled" in result.notes
    assert not calls


def test_crawlkit_research_adapter_collects_sources(monkeypatch) -> None:
    flags = config.FeatureFlags(
        enable_crawlkit=True,
        enable_press_research=True,
        enable_regulator_lookup=True,
        enable_ml_inference=True,
        investigate_rebrands=True,
    )
    monkeypatch.setattr(config, "FEATURE_FLAGS", flags)
    monkeypatch.setattr(config, "ALLOW_NETWORK_RESEARCH", True)

    def seed(_: str, __: str) -> tuple[ResearchFinding, list[str]]:
        baseline = ResearchFinding(website_url="https://official.gov.za/profile")
        return baseline, ["https://official.gov.za/profile"]

    def fake_fetch(
        url: str,
        *,
        policy: Mapping[str, object] | None = None,
        depth: int = 1,
        include_subpaths: bool = False,
    ) -> Mapping[str, object]:  # pragma: no cover - deterministic stub
        assert policy is not None
        assert depth == 1
        assert not include_subpaths
        return {
            "url": url,
            "markdown": "",
            "text": "",
            "metadata": {"description": "Verified contact"},
            "entities": {
                "emails": [
                    {"address": "thabo.ndlovu@official.gov.za", "status": "mx_only"}
                ],
                "phones": [{"number": "+27 10 555 0100", "kind": "business"}],
                "people": [{"name": "Thabo Ndlovu", "role": "Director"}],
            },
        }

    adapter = research.CrawlkitResearchAdapter(
        fetcher=fake_fetch,
        seed_url_provider=seed,
    )
    result = adapter.lookup("Example Org", "Gauteng")

    assert result.contact_person == "Thabo Ndlovu"
    assert result.contact_email == "thabo.ndlovu@official.gov.za"
    assert result.contact_phone == "+27105550100"
    assert "https://official.gov.za/profile" in result.sources
    assert result.confidence == 70
    assert "Verified contact" in result.investigation_notes


def test_crawlkit_research_adapter_merges_multiple_seed_urls(monkeypatch) -> None:
    flags = config.FeatureFlags(
        enable_crawlkit=True,
        enable_press_research=True,
        enable_regulator_lookup=True,
        enable_ml_inference=True,
        investigate_rebrands=True,
    )
    monkeypatch.setattr(config, "FEATURE_FLAGS", flags)
    monkeypatch.setattr(config, "ALLOW_NETWORK_RESEARCH", True)

    baseline = ResearchFinding(
        website_url="https://primary.example.za",
        sources=[
            "https://press.example.za/article",
            "https://regulator.example.za/profile",
        ],
    )

    def seed(_: str, __: str) -> tuple[ResearchFinding, list[str]]:
        return baseline, [
            "https://primary.example.za",
            "https://press.example.za/article",
            "https://regulator.example.za/profile",
            "https://press.example.za/article",
        ]

    seen: list[str] = []

    def fake_fetch(
        url: str,
        *,
        policy: Mapping[str, object] | None = None,
        depth: int = 1,
        include_subpaths: bool = False,
    ) -> Mapping[str, object]:  # pragma: no cover - deterministic stub
        assert policy is not None
        assert depth == 1
        assert not include_subpaths
        seen.append(url)
        if "press" in url:
            return {
                "items": [
                    {
                        "url": url,
                        "entities": {
                            "people": [
                                {"name": "Press Liaison", "role": "Spokesperson"}
                            ],
                            "phones": [{"number": "+27 12 555 0101", "kind": "media"}],
                        },
                    }
                ]
            }
        if "regulator" in url:
            return {
                "url": url,
                "entities": {
                    "emails": [{"address": "compliance@regulator.example.za"}],
                },
            }
        return {
            "url": url,
            "entities": {
                "people": [{"name": "Amina Dlamini", "role": "Managing Director"}],
                "phones": [{"number": "+27 11 555 0123", "kind": "switchboard"}],
            },
        }

    adapter = research.CrawlkitResearchAdapter(
        fetcher=fake_fetch,
        seed_url_provider=seed,
    )

    result = adapter.lookup("Example Org", "Gauteng")

    assert seen == [
        "https://primary.example.za",
        "https://press.example.za/article",
        "https://regulator.example.za/profile",
    ]
    assert result.contact_person == "Press Liaison"
    assert result.contact_phone == "+27125550101"
    assert result.contact_email == "compliance@regulator.example.za"
    assert result.sources == [
        "https://press.example.za/article",
        "https://regulator.example.za/profile",
        "https://primary.example.za",
    ]


def test_crawlkit_research_adapter_reports_failed_urls(monkeypatch) -> None:
    flags = config.FeatureFlags(
        enable_crawlkit=True,
        enable_press_research=True,
        enable_regulator_lookup=True,
        enable_ml_inference=True,
        investigate_rebrands=True,
    )
    monkeypatch.setattr(config, "FEATURE_FLAGS", flags)
    monkeypatch.setattr(config, "ALLOW_NETWORK_RESEARCH", True)

    def seed(_: str, __: str) -> tuple[ResearchFinding, list[str]]:
        return ResearchFinding(), [
            "https://success.example.za",
            "https://failure.example.za",
        ]

    def fake_fetch(
        url: str,
        *,
        policy: Mapping[str, object] | None = None,
        depth: int = 1,
        include_subpaths: bool = False,
    ) -> Mapping[str, object]:  # pragma: no cover - deterministic stub
        assert policy is not None
        assert depth == 1
        assert not include_subpaths
        if "failure" in url:
            raise RuntimeError("boom")
        return {
            "url": url,
            "entities": {
                "emails": [{"address": "contact@success.example.za"}],
            },
        }

    adapter = research.CrawlkitResearchAdapter(
        fetcher=fake_fetch,
        seed_url_provider=seed,
    )

    result = adapter.lookup("Example Org", "Gauteng")

    assert result.contact_email == "contact@success.example.za"
    assert "Crawlkit skipped 1 URL" in result.notes
    assert "https://failure.example.za" in result.notes


def test_extract_urls_and_unique_filters_duplicates() -> None:
    urls = research.core._extract_urls(
        {
            "data": {
                "results": [
                    {"url": "https://example.org"},
                    {"website": "https://example.org"},
                    {"link": "https://official.gov.za"},
                ]
            }
        }
    )
    assert urls == ["https://example.org", "https://official.gov.za"]

    assert research.core._unique(
        ["", "https://official.gov.za", "https://official.gov.za"]
    ) == ["https://official.gov.za"]
