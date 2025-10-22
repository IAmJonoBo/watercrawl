from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Protocol

from firecrawl_demo.core import config
from firecrawl_demo.core.external_sources import (
    query_press,
    query_professional_directory,
    query_regulator_api,
)
from firecrawl_demo.domain.compliance import normalize_phone
from firecrawl_demo.integrations.crawl_policy import CrawlPolicyManager

logger = logging.getLogger(__name__)

_POLITENESS_MANAGER = CrawlPolicyManager()


@dataclass(frozen=True)
class ConnectorRequest:
    """Context passed to connectors for a lookup."""

    organisation: str
    province: str
    allow_personal_data: bool
    rate_limit_delay: float = 0.0


@dataclass(frozen=True)
class ConnectorObservation:
    """Partial finding contributed by a connector."""

    website_url: str | None = None
    contact_person: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    notes: list[str] = field(default_factory=list)
    alternate_names: list[str] = field(default_factory=list)
    physical_address: str | None = None

    def __post_init__(self) -> None:  # pragma: no cover - dataclass hook
        object.__setattr__(self, "notes", _unique(self.notes))
        object.__setattr__(self, "alternate_names", _unique(self.alternate_names))


@dataclass(frozen=True)
class ConnectorEvidence:
    """Structured evidence trail emitted by a connector."""

    connector: str
    sources: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    latency_seconds: float | None = None
    success: bool = False
    privacy_filtered_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:  # pragma: no cover - dataclass hook
        object.__setattr__(self, "sources", _unique(self.sources))
        object.__setattr__(self, "notes", _unique(self.notes))


@dataclass(frozen=True)
class ConnectorResult:
    """Composite return value for connector execution."""

    connector: str
    observation: ConnectorObservation
    sources: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    success: bool = False
    latency_seconds: float | None = None
    raw_payload: Mapping[str, Any] | None = None
    privacy_filtered_fields: tuple[str, ...] = ()
    error: str | None = None

    def __post_init__(self) -> None:  # pragma: no cover - dataclass hook
        object.__setattr__(self, "sources", _unique(self.sources))
        object.__setattr__(self, "notes", _unique(self.notes))


class ResearchConnector(Protocol):
    """Interface implemented by all research connectors."""

    name: str

    def collect(self, request: ConnectorRequest) -> ConnectorResult: ...


class BaseConnector:
    """Base implementation shared by concrete connectors."""

    name: str
    _requester_factory: Callable[[ConnectorRequest], Mapping[str, Any] | None] | None

    def __init__(
        self,
        *,
        requester: Callable[[ConnectorRequest], Mapping[str, Any] | None] | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._requester_factory = requester
        self._timeout = timeout

    def collect(self, request: ConnectorRequest) -> ConnectorResult:
        start = monotonic()
        payload: Mapping[str, Any] | None = None
        filtered: list[str] = []
        try:
            payload = self._fetch_payload(request)
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.warning("%s connector failed: %s", self.name, exc, exc_info=exc)
            return ConnectorResult(
                connector=self.name,
                observation=ConnectorObservation(),
                notes=[f"Connector {self.name} failed: {exc}"],
                success=False,
                error=str(exc),
            )

        if request.rate_limit_delay > 0:
            time.sleep(request.rate_limit_delay)

        observation, sources, notes, filtered = self._parse_payload(
            request, payload or {}
        )
        sources = self._apply_politeness(request, list(sources), notes, payload or {})
        latency = monotonic() - start if payload is not None else None
        return ConnectorResult(
            connector=self.name,
            observation=observation,
            sources=sources,
            notes=notes,
            success=bool(payload),
            latency_seconds=latency,
            raw_payload=payload,
            privacy_filtered_fields=tuple(filtered),
        )

    def _apply_politeness(
        self,
        _request: ConnectorRequest,
        sources: list[str],
        notes: list[str],
        payload: Mapping[str, Any],
    ) -> list[str]:
        """Filter sources that violate robots.txt or ToS guidance."""

        allowed: list[str] = []
        tos_blocked: set[str] = set()
        for key in ("tos_forbidden_sources", "terms_of_service_blocked"):
            value = payload.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                tos_blocked.update(str(item) for item in value if item)
            elif isinstance(value, str) and value:
                tos_blocked.add(value)

        skipped_for_policy: list[str] = []
        skipped_for_tos: list[str] = []
        for source in sources:
            canonical = _POLITENESS_MANAGER.canonicalize_url(source)
            if canonical != source:
                notes.append(f"Canonicalized {source} to {canonical}")
            if canonical in tos_blocked:
                skipped_for_tos.append(canonical)
                continue
            if not _POLITENESS_MANAGER.can_fetch(canonical):
                skipped_for_policy.append(canonical)
                continue
            allowed.append(canonical)

        if skipped_for_policy:
            sample = ", ".join(skipped_for_policy[:2])
            notes.append(
                f"Skipped {len(skipped_for_policy)} sources blocked by robots.txt or crawl policy ({sample})"
            )
        if skipped_for_tos:
            suggestion = next(
                iter(config.EVIDENCE_QUERIES), "official regulator search"
            )
            notes.append(
                "Terms of Service restrictions prevented {count} sources; suggested alternate query: {query}".format(
                    count=len(skipped_for_tos), query=suggestion
                )
            )
        return allowed

    def _fetch_payload(self, request: ConnectorRequest) -> Mapping[str, Any] | None:
        if self._requester_factory is not None:
            return self._requester_factory(request)
        if not config.ALLOW_NETWORK_RESEARCH:
            return None
        return self._call_external_source(request)

    def _call_external_source(
        self, request: ConnectorRequest
    ) -> Mapping[str, Any] | None:
        raise NotImplementedError

    def _parse_payload(
        self, request: ConnectorRequest, payload: Mapping[str, Any]
    ) -> tuple[ConnectorObservation, list[str], list[str], list[str]]:
        raise NotImplementedError


class RegulatorConnector(BaseConnector):
    name = "regulator"

    def __init__(
        self,
        *,
        requester: Callable[[ConnectorRequest], Mapping[str, Any] | None] | None = None,
        timeout: float = 10.0,
    ) -> None:
        super().__init__(requester=requester, timeout=timeout)

    def _call_external_source(
        self, request: ConnectorRequest
    ) -> Mapping[str, Any] | None:
        return query_regulator_api(request.organisation)

    def _parse_payload(
        self, request: ConnectorRequest, payload: Mapping[str, Any]
    ) -> tuple[ConnectorObservation, list[str], list[str], list[str]]:
        notes: list[str] = []
        sources: list[str] = []
        filtered: list[str] = []
        website = _extract_first(payload, ["officialWebsite", "website", "url"])
        contact_person = _extract_first(payload, ["contactPerson", "contact_person"])
        contact_email = _extract_first(payload, ["contactEmail", "contact_email"])
        contact_phone = _extract_first(payload, ["contactPhone", "contact_phone"])
        address = _extract_first(payload, ["address", "physicalAddress", "location"])
        for item in _ensure_list(payload.get("sources")):
            if isinstance(item, str):
                sources.append(item)
        possible_source = payload.get("source") or payload.get("url")
        if isinstance(possible_source, str):
            sources.append(possible_source)
        notes.append("Regulator registry corroboration")
        if not request.allow_personal_data:
            filtered.extend(
                _prune_personal_fields(
                    {
                        "contact_person": contact_person,
                        "contact_email": contact_email,
                        "contact_phone": contact_phone,
                    }
                )
            )
            if "contact_person" in filtered:
                contact_person = None
            if "contact_email" in filtered:
                contact_email = None
            if "contact_phone" in filtered:
                contact_phone = None
        normalized_phone, _ = normalize_phone(contact_phone)
        if normalized_phone:
            contact_phone = normalized_phone
        return (
            ConnectorObservation(
                website_url=website,
                contact_person=contact_person,
                contact_email=contact_email,
                contact_phone=contact_phone,
                physical_address=address,
                alternate_names=_ensure_list(payload.get("knownAliases", [])),
            ),
            sources,
            notes,
            filtered,
        )


class PressConnector(BaseConnector):
    name = "press"

    def _call_external_source(
        self, request: ConnectorRequest
    ) -> Mapping[str, Any] | None:
        return query_press(request.organisation)

    def _parse_payload(
        self, request: ConnectorRequest, payload: Mapping[str, Any]
    ) -> tuple[ConnectorObservation, list[str], list[str], list[str]]:
        sources: list[str] = []
        coverage_notes: list[str] = []
        articles = _ensure_list(payload.get("articles"))
        for article in articles:
            if not isinstance(article, Mapping):
                continue
            url = article.get("url") or article.get("link")
            if isinstance(url, str):
                sources.append(url)
            headline = article.get("title") or article.get("headline")
            summary = article.get("summary") or article.get("description")
            if headline:
                coverage_notes.append(f"Press coverage: {headline}")
            if summary and not headline:
                coverage_notes.append(f"Press coverage: {summary}")
        return ConnectorObservation(notes=coverage_notes), sources, coverage_notes, []


class CorporateFilingsConnector(BaseConnector):
    name = "corporate_filings"

    def _call_external_source(
        self, request: ConnectorRequest
    ) -> Mapping[str, Any] | None:
        return query_professional_directory(request.organisation)

    def _parse_payload(
        self, request: ConnectorRequest, payload: Mapping[str, Any]
    ) -> tuple[ConnectorObservation, list[str], list[str], list[str]]:
        sources: list[str] = []
        notes: list[str] = []
        filtered: list[str] = []
        contact_person: str | None = None
        contact_email: str | None = None
        contact_phone: str | None = None
        website: str | None = None
        address: str | None = None
        for entry in _iterate_results(payload):
            url = entry.get("website") or entry.get("url")
            if isinstance(url, str):
                sources.append(url)
                website = website or url
            address = address or entry.get("address")
            contact_person = (
                contact_person or entry.get("contact") or entry.get("contactPerson")
            )
            contact_email = contact_email or entry.get("email")
            contact_phone = contact_phone or entry.get("phone")
        if sources:
            notes.append("Corporate filings or directory corroboration")
        if not request.allow_personal_data:
            filtered.extend(
                _prune_personal_fields(
                    {
                        "contact_person": contact_person,
                        "contact_email": contact_email,
                        "contact_phone": contact_phone,
                    }
                )
            )
            if "contact_person" in filtered:
                contact_person = None
            if "contact_email" in filtered:
                contact_email = None
            if "contact_phone" in filtered:
                contact_phone = None
        normalized_phone, _ = normalize_phone(contact_phone)
        if normalized_phone:
            contact_phone = normalized_phone
        return (
            ConnectorObservation(
                website_url=website,
                contact_person=contact_person,
                contact_email=contact_email,
                contact_phone=contact_phone,
                physical_address=address,
            ),
            sources,
            notes,
            filtered,
        )


class SocialConnector(BaseConnector):
    name = "social"

    def _call_external_source(
        self, request: ConnectorRequest
    ) -> Mapping[str, Any] | None:
        directory_payload = query_professional_directory(request.organisation)
        if directory_payload:
            return directory_payload
        return None

    def _parse_payload(
        self, request: ConnectorRequest, payload: Mapping[str, Any]
    ) -> tuple[ConnectorObservation, list[str], list[str], list[str]]:
        notes: list[str] = []
        sources: list[str] = []
        handles: list[str] = []
        for entry in _iterate_results(payload):
            for handle in _ensure_list(entry.get("socialProfiles")):
                if isinstance(handle, Mapping):
                    url = handle.get("url")
                else:
                    url = handle
                if isinstance(url, str):
                    sources.append(url)
                    handles.append(url)
        if handles:
            notes.append("Social footprint discovered")
        return ConnectorObservation(notes=notes), sources, notes, []


def _unique(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _extract_first(payload: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _ensure_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value:
        return [value]
    return []


def _iterate_results(payload: Mapping[str, Any]) -> Sequence[MutableMapping[str, Any]]:
    if "results" in payload and isinstance(payload["results"], list):
        return [item for item in payload["results"] if isinstance(item, MutableMapping)]
    if isinstance(payload, MutableMapping):
        return [payload]
    return []


def _prune_personal_fields(fields: Mapping[str, str | None]) -> list[str]:
    filtered: list[str] = []
    for key, value in fields.items():
        if value:
            filtered.append(key)
    return filtered


__all__ = [
    "ConnectorEvidence",
    "ConnectorObservation",
    "ConnectorRequest",
    "ConnectorResult",
    "CorporateFilingsConnector",
    "PressConnector",
    "RegulatorConnector",
    "ResearchConnector",
    "SocialConnector",
]
