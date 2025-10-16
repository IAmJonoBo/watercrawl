from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .. import config
from ..compliance import normalize_phone
from ..external_sources import triangulate_organisation
from ..firecrawl_client import FirecrawlClient, summarize_extract_payload

logger = logging.getLogger(__name__)


class ResearchAdapter(Protocol):
    def lookup(self, organisation: str, province: str) -> ResearchFinding: ...


@dataclass(frozen=True)
class ResearchFinding:
    website_url: str | None = None
    contact_person: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    sources: list[str] = field(default_factory=list)
    notes: str = ""
    confidence: int = 0
    alternate_names: list[str] = field(default_factory=list)
    investigation_notes: list[str] = field(default_factory=list)
    physical_address: str | None = None

    def __post_init__(self) -> None:  # pragma: no cover - dataclass hook
        object.__setattr__(self, "sources", _unique(self.sources))
        object.__setattr__(self, "alternate_names", _unique(self.alternate_names))
        object.__setattr__(
            self, "investigation_notes", _unique(self.investigation_notes)
        )
        if self.contact_phone:
            normalized, _ = normalize_phone(self.contact_phone)
            if normalized:
                object.__setattr__(self, "contact_phone", normalized)


class NullResearchAdapter:
    """Fallback adapter that provides empty research findings."""

    def lookup(self, organisation: str, province: str) -> ResearchFinding:
        return ResearchFinding()


class StaticResearchAdapter:
    """Adapter backed by a static mapping for deterministic tests or fixtures."""

    def __init__(self, findings: Mapping[str, ResearchFinding]):
        self._findings = findings

    def lookup(self, organisation: str, province: str) -> ResearchFinding:
        return self._findings.get(organisation, ResearchFinding())


@dataclass
class CompositeResearchAdapter:
    """Run multiple adapters and merge their findings."""

    adapters: Sequence[ResearchAdapter]

    def lookup(self, organisation: str, province: str) -> ResearchFinding:
        findings = [adapter.lookup(organisation, province) for adapter in self.adapters]
        return merge_findings(*findings)


TriangulationCallable = Callable[[str, str, ResearchFinding], ResearchFinding]


@dataclass
class TriangulatingResearchAdapter:
    """Augments baseline adapters with triangulated intelligence."""

    base_adapter: ResearchAdapter
    triangulate: TriangulationCallable

    def lookup(self, organisation: str, province: str) -> ResearchFinding:
        baseline = self.base_adapter.lookup(organisation, province)
        triangulated = self.triangulate(organisation, province, baseline)
        return merge_findings(baseline, triangulated)


class FirecrawlResearchAdapter:
    """Adapter that queries the Firecrawl SDK when feature flags allow."""

    def __init__(self, client: FirecrawlClient) -> None:
        self._client = client

    def lookup(self, organisation: str, province: str) -> ResearchFinding:
        if not config.ALLOW_NETWORK_RESEARCH:
            return ResearchFinding(
                notes=(
                    "Firecrawl SDK available but network research disabled. "
                    "Run with ALLOW_NETWORK_RESEARCH=1 to enable live enrichment."
                )
            )

        query = f"{organisation} {province} South Africa flight school"
        sources: list[str] = []
        notes: list[str] = []
        confidence = 0
        extract_payload = {}

        try:
            search_result = self._client.search(
                query,
                limit=config.FIRECRAWL.behaviour.search_limit,
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.warning("Firecrawl search failed for %s: %s", organisation, exc)
            notes.append(f"Firecrawl search failed: {exc}")
        else:
            sources.extend(_extract_urls(search_result))

        if not sources:
            notes.append("Firecrawl search returned no actionable URLs")
            return ResearchFinding(notes="; ".join(notes))

        try:
            extract_payload = self._client.extract(
                urls=sources[: config.FIRECRAWL.behaviour.map_limit],
                prompt=(
                    "Summarise contact information, official website, and any recent "
                    "ownership or brand changes for {organisation} in {province}, "
                    "South Africa."
                ).format(organisation=organisation, province=province),
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.warning("Firecrawl extract failed for %s: %s", organisation, exc)
            notes.append(f"Firecrawl extract failed: {exc}")
        else:
            confidence = 70

        summary = summarize_extract_payload(extract_payload)
        investigation: list[str] = []
        for key in ("ownership_change", "rebrand_note"):
            value = summary.get(key)
            if isinstance(value, str) and value:
                investigation.append(value)

        finding = ResearchFinding(
            website_url=summary.get("website_url"),
            contact_person=summary.get("contact_person"),
            contact_email=summary.get("contact_email"),
            contact_phone=summary.get("contact_phone"),
            sources=sources,
            notes="; ".join(notes) if notes else "Firecrawl insight gathered",
            confidence=confidence,
            investigation_notes=investigation,
        )
        return finding


def merge_findings(*findings: ResearchFinding) -> ResearchFinding:
    website_url: str | None = None
    contact_person: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    notes: list[str] = []
    sources: list[str] = []
    confidence = 0
    alternate_names: list[str] = []
    investigation_notes: list[str] = []
    physical_address: str | None = None

    for finding in findings:
        if finding.website_url:
            website_url = finding.website_url
        if finding.contact_person:
            contact_person = finding.contact_person
        if finding.contact_email:
            contact_email = finding.contact_email
        if finding.contact_phone:
            contact_phone = finding.contact_phone
        if finding.physical_address:
            physical_address = finding.physical_address
        if finding.notes:
            notes.append(finding.notes)
        for source in finding.sources:
            if source not in sources:
                sources.append(source)
        for alt in finding.alternate_names:
            if alt not in alternate_names:
                alternate_names.append(alt)
        for note in finding.investigation_notes:
            if note not in investigation_notes:
                investigation_notes.append(note)
        confidence = max(confidence, finding.confidence)

    return ResearchFinding(
        website_url=website_url,
        contact_person=contact_person,
        contact_email=contact_email,
        contact_phone=contact_phone,
        sources=sources,
        notes="; ".join(notes),
        confidence=confidence,
        alternate_names=alternate_names,
        investigation_notes=investigation_notes,
        physical_address=physical_address,
    )


def triangulate_via_sources(
    organisation: str, province: str, baseline: ResearchFinding
) -> ResearchFinding:
    features = config.FEATURE_FLAGS
    if not (features.enable_press_research or features.enable_regulator_lookup):
        return ResearchFinding()

    if not config.ALLOW_NETWORK_RESEARCH:
        investigation = []
        if features.investigate_rebrands:
            investigation.append(
                f"Manual verification required to confirm any rebrand for {organisation}."
            )
        return ResearchFinding(
            notes="Network research disabled; perform manual triangulation.",
            investigation_notes=investigation,
        )

    return triangulate_organisation(
        organisation,
        province,
        baseline,
        include_press=features.enable_press_research,
        include_regulator=features.enable_regulator_lookup,
        investigate_rebrands=features.investigate_rebrands,
    )


def build_research_adapter() -> ResearchAdapter:
    """Assemble the active research pipeline based on the adapter registry."""

    from .registry import AdapterLoaderSettings, load_enabled_adapters

    settings = AdapterLoaderSettings(provider=config.SECRETS_PROVIDER)
    adapters = load_enabled_adapters(settings)

    if not adapters:
        adapters = [NullResearchAdapter()]

    base: ResearchAdapter
    if len(adapters) == 1:
        base = adapters[0]
    else:
        base = CompositeResearchAdapter(tuple(adapters))

    return TriangulatingResearchAdapter(
        base_adapter=base, triangulate=triangulate_via_sources
    )


def _build_firecrawl_adapter() -> ResearchAdapter | None:
    try:
        client = FirecrawlClient()
        # Trigger lazy validation of credentials
        if config.ALLOW_NETWORK_RESEARCH:
            client._client()
    except Exception as exc:  # pragma: no cover - defensive
        logger.info("Firecrawl adapter unavailable: %s", exc)
        return None
    return FirecrawlResearchAdapter(client)


def _extract_urls(payload: object) -> list[str]:
    urls: list[str] = []
    if isinstance(payload, dict):
        data = payload.get("data", payload)
        if isinstance(data, dict) and "results" in data:
            entries = data.get("results")
        else:
            entries = data
    else:
        entries = payload

    if isinstance(entries, dict):
        iterable: Iterable = entries.values()
    elif isinstance(entries, list):
        iterable = entries
    else:
        iterable = []

    for item in iterable:
        if isinstance(item, dict):
            url = item.get("url") or item.get("link") or item.get("website")
            if isinstance(url, str):
                urls.append(url)
    return _unique(urls)


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values
