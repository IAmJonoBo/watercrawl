"""Core research adapter primitives and Firecrawl integration helpers."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from concurrent.futures import Executor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable
from urllib.parse import urlparse

from crawlkit.adapter.firecrawl_compat import fetch_markdown
from crawlkit.types import Entities, FetchPolicy

from firecrawl_demo.core import config
from firecrawl_demo.core.external_sources import triangulate_organisation
from firecrawl_demo.domain.compliance import normalize_phone

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - typing helpers
    from .connectors import ConnectorEvidence
    from .validators import ValidationReport


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
    evidence_by_connector: dict[str, "ConnectorEvidence"] = field(
        default_factory=dict
    )
    validation: "ValidationReport | None" = None

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
        object.__setattr__(
            self, "evidence_by_connector", dict(self.evidence_by_connector)
        )


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


class CrawlkitResearchAdapter:
    """Adapter that uses Crawlkit fetch/distill/extract pipelines for enrichment."""

    SeedProvider = Callable[[str, str], tuple[ResearchFinding, list[str]]]
    PolicyFactory = Callable[[str, str], Mapping[str, Any]]

    def __init__(
        self,
        fetcher: Callable[[str, int, bool, Mapping[str, Any] | None], Mapping[str, Any]] | None = None,
        *,
        seed_url_provider: SeedProvider | None = None,
        policy_factory: PolicyFactory | None = None,
    ) -> None:
        self._fetcher = fetcher or fetch_markdown
        self._seed_urls = seed_url_provider or self._default_seed_urls
        self._policy_factory = policy_factory or self._default_policy

    def lookup(self, organisation: str, province: str) -> ResearchFinding:
        return self._lookup_sync(organisation, province)

    async def lookup_async(self, organisation: str, province: str) -> ResearchFinding:
        return await asyncio.to_thread(self._lookup_sync, organisation, province)

    def _lookup_sync(self, organisation: str, province: str) -> ResearchFinding:
        if not config.FEATURE_FLAGS.enable_crawlkit:
            return ResearchFinding(notes="Crawlkit adapter disabled by feature flag.")
        if not config.ALLOW_NETWORK_RESEARCH:
            return ResearchFinding(
                notes=(
                    "Crawlkit adapter available but network research disabled. "
                    "Set ALLOW_NETWORK_RESEARCH=1 to enable live enrichment."
                )
            )

        baseline, urls = self._seed_urls(organisation, province)
        if not urls:
            note = baseline.notes or "Crawlkit found no candidate URLs"
            return merge_findings(baseline, ResearchFinding(notes=note))

        findings: list[ResearchFinding] = []
        policy = self._policy_factory(organisation, province)
        seen: set[str] = set()
        failures: list[str] = []

        for url in _unique(urls):
            if not isinstance(url, str) or not url:
                continue
            if url in seen:
                continue
            seen.add(url)
            try:
                result = self._fetcher(url, policy=policy)
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.warning("Crawlkit fetch failed for %s (%s): %s", organisation, url, exc)
                failures.append(url)
                continue

            records: list[Mapping[str, Any]]
            if isinstance(result.get("items"), list):
                records = [item for item in result.get("items", []) if isinstance(item, Mapping)]
            else:
                records = [result]

            for item in records:
                finding = self._build_finding_from_record(item)
                if finding:
                    findings.append(finding)

        if not findings:
            notes: list[str] = [
                baseline.notes or "Crawlkit returned no enrichments"
            ]
            if failures:
                notes.append(_format_failure_note(failures))
            return merge_findings(
                baseline,
                ResearchFinding(notes="; ".join(notes)),
            )

        enriched = merge_findings(*findings)
        if failures:
            enriched = merge_findings(
                enriched,
                ResearchFinding(notes=_format_failure_note(failures)),
            )
        return merge_findings(baseline, enriched)

    def _default_seed_urls(
        self, organisation: str, province: str
    ) -> tuple[ResearchFinding, list[str]]:
        try:
            baseline = triangulate_organisation(
                organisation,
                province,
                ResearchFinding(),
                include_press=config.FEATURE_FLAGS.enable_press_research,
                include_regulator=config.FEATURE_FLAGS.enable_regulator_lookup,
                investigate_rebrands=config.FEATURE_FLAGS.investigate_rebrands,
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.warning("Triangulation failed for %s: %s", organisation, exc)
            baseline = ResearchFinding(notes=f"Triangulation failed: {exc}")

        urls: list[str] = []
        if baseline.website_url:
            urls.append(baseline.website_url)
        urls.extend([source for source in baseline.sources if isinstance(source, str)])
        return baseline, _unique(urls)

    def _default_policy(self, organisation: str, province: str) -> Mapping[str, Any]:
        policy = FetchPolicy(region="ZA")
        policy.max_depth = 1
        policy.max_pages = 5
        return policy.to_dict()

    def _build_finding_from_record(self, record: Mapping[str, Any]) -> ResearchFinding | None:
        url = _coerce_url(record)
        entities = Entities.from_mapping(record.get("entities"))
        emails = entities.emails
        phones = entities.phones
        people = entities.people

        contact_email = _first_str(emails, "address")
        contact_phone = _first_str(phones, "number")
        contact_person = _first_str(people, "name")

        notes: list[str] = []
        if contact_email:
            notes.append("Email extracted via Crawlkit")
        if contact_phone:
            notes.append("Phone extracted via Crawlkit")
        if contact_person:
            notes.append("Contact person referenced in content")

        description = _metadata_value(record, "description")
        investigation_notes: list[str] = []
        if description:
            investigation_notes.append(description)

        if not (contact_email or contact_phone or contact_person):
            notes.append("Crawlkit fetch completed with no direct contacts")

        domain_hint = urlparse(url).netloc if isinstance(url, str) else None
        if entities.emails and not contact_email and domain_hint:
            first_email = entities.emails[0]
            if isinstance(first_email, Mapping):
                contact_email = first_email.get("address")  # type: ignore[assignment]

        confidence = 70 if (contact_email or contact_phone) else 50

        return ResearchFinding(
            website_url=url,
            contact_person=contact_person,
            contact_email=contact_email,
            contact_phone=contact_phone,
            sources=[url] if isinstance(url, str) else [],
            notes="; ".join(notes) if notes else "Crawlkit insight gathered",
            confidence=confidence,
            alternate_names=[
                str(person.get("name"))
                for person in people[1:4]
                if isinstance(person.get("name"), str)
            ],
            investigation_notes=investigation_notes,
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
    evidence_by_connector: dict[str, "ConnectorEvidence"] = {}
    validation: "ValidationReport | None" = None

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
        if finding.evidence_by_connector:
            evidence_by_connector.update(finding.evidence_by_connector)
        if finding.validation is not None:
            validation = finding.validation

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
        evidence_by_connector=evidence_by_connector,
        validation=validation,
    )


def _format_failure_note(failures: Sequence[str]) -> str:
    """Summarise Crawlkit fetch failures for analyst visibility."""

    display = [url for url in failures if url][:3]
    more = max(len(failures) - len(display), 0)
    summary = ", ".join(display)
    if more:
        summary = f"{summary}, … (+{more} more)" if summary else f"… (+{more} more)"
    urls_fragment = f": {summary}" if summary else ""
    return f"Crawlkit skipped {len(failures)} URL(s) due to fetch errors{urls_fragment}."


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
    from .multi_source import MultiSourceResearchAdapter

    settings = AdapterLoaderSettings(provider=config.SECRETS_PROVIDER)
    adapters = load_enabled_adapters(settings)

    base_connectors = MultiSourceResearchAdapter()
    if adapters:
        adapters = [base_connectors, *adapters]
    else:
        adapters = [base_connectors]

    if len(adapters) == 1:
        base: ResearchAdapter = adapters[0]
    else:
        base = CompositeResearchAdapter(tuple(adapters))

    return TriangulatingResearchAdapter(
        base_adapter=base, triangulate=triangulate_via_sources
    )


def _build_firecrawl_adapter() -> ResearchAdapter | None:
    if not config.FEATURE_FLAGS.enable_crawlkit:
        logger.info("Crawlkit adapter disabled via feature flag")
        return None
    return CrawlkitResearchAdapter()


async def lookup_with_adapter_async(
    adapter: ResearchAdapter,
    organisation: str,
    province: str,
    *,
    executor: Executor | None = None,
) -> ResearchFinding:
    if isinstance(adapter, SupportsAsyncLookup):
        result = adapter.lookup_async(organisation, province)
        if isinstance(result, Awaitable):
            return await result
        return result  # type: ignore[return-value]
    loop = asyncio.get_running_loop()
    candidate_executor = executor
    if candidate_executor is None:
        candidate_executor = getattr(adapter, "_lookup_executor", None)
    return await loop.run_in_executor(
        candidate_executor, adapter.lookup, organisation, province
    )


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


def _metadata_value(record: Mapping[str, Any], key: str) -> str | None:
    metadata = record.get("metadata")
    if not isinstance(metadata, Mapping):
        return None
    value = metadata.get(key)
    return str(value) if isinstance(value, str) and value else None


def _first_str(items: Iterable[Mapping[str, Any]], key: str) -> str | None:
    for item in items:
        if not isinstance(item, Mapping):
            continue
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _coerce_url(record: Mapping[str, Any]) -> str | None:
    raw = record.get("url")
    if isinstance(raw, str) and raw:
        return raw
    metadata = record.get("metadata")
    if isinstance(metadata, Mapping):
        for candidate in ("canonical_url", "url", "source_url"):
            value = metadata.get(candidate)
            if isinstance(value, str) and value:
                return value
    return None
