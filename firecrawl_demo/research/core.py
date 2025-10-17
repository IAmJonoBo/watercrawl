"""Core research adapter primitives and Firecrawl integration helpers."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol, runtime_checkable

from .. import config
from ..compliance import normalize_phone
from ..external_sources import triangulate_organisation
from ..firecrawl_client import FirecrawlClient, summarize_extract_payload

logger = logging.getLogger(__name__)


@runtime_checkable
class SupportsAsyncLookup(Protocol):
    """Protocol for adapters that expose an async lookup API."""

    async def lookup_async(
        self, organisation: str, province: str
    ) -> ResearchFinding: ...


class ResearchAdapter(Protocol):
    """Protocol describing the synchronous adapter surface."""

    def lookup(self, organisation: str, province: str) -> ResearchFinding: ...


@dataclass(frozen=True)
class ResearchFinding:
    """Container for enrichment data returned by research adapters."""

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
        """Normalise collection fields for deterministic comparisons."""

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
    """Fallback adapter that returns empty findings."""

    def lookup(self, organisation: str, province: str) -> ResearchFinding:
        return ResearchFinding()

    async def lookup_async(self, organisation: str, province: str) -> ResearchFinding:
        return ResearchFinding()


class StaticResearchAdapter:
    """Adapter backed by a static mapping for deterministic tests or fixtures."""

    def __init__(self, findings: Mapping[str, ResearchFinding]):
        self._findings = findings

    def lookup(self, organisation: str, province: str) -> ResearchFinding:
        return self._findings.get(organisation, ResearchFinding())

    async def lookup_async(self, organisation: str, province: str) -> ResearchFinding:
        return self.lookup(organisation, province)


@dataclass
class CompositeResearchAdapter:
    """Run multiple adapters and merge their findings."""

    adapters: Sequence[ResearchAdapter]

    def lookup(self, organisation: str, province: str) -> ResearchFinding:
        findings = [adapter.lookup(organisation, province) for adapter in self.adapters]
        return merge_findings(*findings)

    async def lookup_async(self, organisation: str, province: str) -> ResearchFinding:
        findings = await asyncio.gather(
            *[
                lookup_with_adapter_async(adapter, organisation, province)
                for adapter in self.adapters
            ]
        )
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

    async def lookup_async(self, organisation: str, province: str) -> ResearchFinding:
        baseline = await lookup_with_adapter_async(
            self.base_adapter, organisation, province
        )
        triangulated = await asyncio.to_thread(
            self.triangulate, organisation, province, baseline
        )
        return merge_findings(baseline, triangulated)


class FirecrawlResearchAdapter:
    """Adapter that queries the Firecrawl SDK when feature flags allow."""

    def __init__(self, client: FirecrawlClient | None = None) -> None:
        self._client = client or FirecrawlClient()

    def lookup(self, organisation: str, province: str) -> ResearchFinding:
        return self._lookup_sync(organisation, province)

    async def lookup_async(self, organisation: str, province: str) -> ResearchFinding:
        return await self._lookup_async(organisation, province)

    def _lookup_sync(self, organisation: str, province: str) -> ResearchFinding:
        if not config.FEATURE_FLAGS.enable_firecrawl_sdk:
            return ResearchFinding(notes="Firecrawl SDK disabled by feature flag.")
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

        extract_payload: dict[str, object] = {}
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

        return self._finalise_result(sources, notes, extract_payload, confidence)

    async def _lookup_async(self, organisation: str, province: str) -> ResearchFinding:
        if not config.FEATURE_FLAGS.enable_firecrawl_sdk:
            return ResearchFinding(notes="Firecrawl SDK disabled by feature flag.")
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

        try:
            search_result = await asyncio.to_thread(
                self._client.search,
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

        extract_payload: dict[str, object] = {}
        try:
            extract_payload = await asyncio.to_thread(
                self._client.extract,
                sources[: config.FIRECRAWL.behaviour.map_limit],
                (
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

        return self._finalise_result(sources, notes, extract_payload, confidence)

    def _finalise_result(
        self,
        sources: Sequence[str],
        notes: Sequence[str],
        extract_payload: Mapping[str, object],
        confidence: int,
    ) -> ResearchFinding:
        summary = summarize_extract_payload(dict(extract_payload))
        investigation: list[str] = []
        for key in ("ownership_change", "rebrand_note"):
            value = summary.get(key)
            if isinstance(value, str) and value:
                investigation.append(value)

        message = "; ".join(notes) if notes else "Firecrawl insight gathered"
        return ResearchFinding(
            website_url=summary.get("website_url"),
            contact_person=summary.get("contact_person"),
            contact_email=summary.get("contact_email"),
            contact_phone=summary.get("contact_phone"),
            sources=_unique(list(sources)),
            notes=message,
            confidence=confidence,
            investigation_notes=investigation,
            physical_address=summary.get("physical_address"),
        )


def merge_findings(*findings: ResearchFinding) -> ResearchFinding:
    """Combine multiple findings, favouring non-empty attributes from later entries."""

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
        notes="; ".join(notes) if notes else "",
        confidence=confidence,
        alternate_names=alternate_names,
        investigation_notes=investigation_notes,
        physical_address=physical_address,
    )


def triangulate_via_sources(
    organisation: str, province: str, baseline: ResearchFinding
) -> ResearchFinding:
    """Use deterministic offline sources to augment Firecrawl findings."""

    flags = config.FEATURE_FLAGS
    return triangulate_organisation(
        organisation,
        province,
        baseline,
        include_press=flags.enable_press_research,
        include_regulator=flags.enable_regulator_lookup,
        investigate_rebrands=flags.investigate_rebrands,
    )


def build_research_adapter() -> ResearchAdapter:
    """Assemble the default adapter stack declared in configuration."""

    from .registry import AdapterLoaderSettings, load_enabled_adapters

    settings = AdapterLoaderSettings(provider=config.SECRETS_PROVIDER)
    adapters = load_enabled_adapters(settings)

    if not adapters:
        adapters = [NullResearchAdapter()]

    if len(adapters) == 1:
        base: ResearchAdapter = adapters[0]
    else:
        base = CompositeResearchAdapter(tuple(adapters))

    return TriangulatingResearchAdapter(
        base_adapter=base, triangulate=triangulate_via_sources
    )


def _build_firecrawl_adapter() -> ResearchAdapter | None:
    try:
        client = FirecrawlClient()
        if config.ALLOW_NETWORK_RESEARCH:
            client._client()
    except Exception as exc:  # pragma: no cover - defensive
        logger.info("Firecrawl adapter unavailable: %s", exc)
        return None
    return FirecrawlResearchAdapter(client)


async def lookup_with_adapter_async(
    adapter: ResearchAdapter, organisation: str, province: str
) -> ResearchFinding:
    if isinstance(adapter, SupportsAsyncLookup):
        result = adapter.lookup_async(organisation, province)
        if isinstance(result, Awaitable):
            return await result
        return result  # type: ignore[return-value]
    return await asyncio.to_thread(adapter.lookup, organisation, province)


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
