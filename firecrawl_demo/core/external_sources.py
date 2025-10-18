from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any

import requests

if TYPE_CHECKING:  # pragma: no cover - typing aid
    from firecrawl_demo.integrations.research import ResearchFinding

from firecrawl_demo.domain.compliance import canonical_domain, normalize_phone

from . import config

logger = logging.getLogger(__name__)

_REBRAND_KEYWORDS = ("rebrand", "acquired", "merger", "renamed", "ownership")


def query_regulator_api(org_name: str) -> dict[str, Any] | None:
    endpoint = f"https://api.regulator.gov.za/orgs?name={org_name}"
    try:
        resp = requests.get(endpoint, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        logger.warning("Regulator API returned status %s", resp.status_code)
    except requests.RequestException as exc:
        logger.warning("Regulator API request failed: %s", exc)
    return None


def query_press(org_name: str) -> dict[str, Any] | None:
    endpoint = f"https://newsapi.org/v2/everything?q={org_name}&apiKey=YOUR_KEY"
    try:
        resp = requests.get(endpoint, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        logger.warning("Press lookup returned status %s", resp.status_code)
    except requests.RequestException as exc:
        logger.warning("Press lookup failed: %s", exc)
    return None


def query_professional_directory(org_name: str) -> dict[str, Any] | None:
    endpoint = f"https://directory.example.com/search?query={org_name}"
    try:
        resp = requests.get(endpoint, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        logger.warning("Directory lookup returned status %s", resp.status_code)
    except requests.RequestException as exc:
        logger.warning("Directory lookup failed: %s", exc)
    return None


def triangulate_organisation(
    organisation: str,
    province: str,
    baseline: ResearchFinding,
    *,
    include_press: bool,
    include_regulator: bool,
    investigate_rebrands: bool,
) -> ResearchFinding:
    from firecrawl_demo.integrations.research import (  # local import to avoid circular dependency
        ResearchFinding,
    )

    website = baseline.website_url
    contact_person = baseline.contact_person
    contact_email = baseline.contact_email
    contact_phone = baseline.contact_phone
    physical_address = baseline.physical_address
    notes: list[str] = []
    sources: list[str] = []
    alternate_names: list[str] = list(baseline.alternate_names)
    investigation_notes: list[str] = list(baseline.investigation_notes)
    confidence = baseline.confidence

    regulator_payload: dict[str, Any] | None = None
    if include_regulator and config.ALLOW_NETWORK_RESEARCH:
        regulator_payload = query_regulator_api(organisation)

    if regulator_payload:
        regulator_website = _extract_first(
            regulator_payload,
            ["officialWebsite", "website", "url"],
        )
        if regulator_website:
            if not website or canonical_domain(website) != canonical_domain(
                regulator_website
            ):
                website = regulator_website
        contact_person = contact_person or _extract_first(
            regulator_payload, ["contactPerson", "contact_person"]
        )
        contact_email = contact_email or _extract_first(
            regulator_payload, ["contactEmail", "contact_email"]
        )
        contact_phone = contact_phone or _extract_first(
            regulator_payload, ["contactPhone", "contact_phone"]
        )
        physical_address = physical_address or _extract_first(
            regulator_payload, ["address", "physicalAddress", "location"]
        )
        sources.extend(_ensure_list(regulator_payload.get("sources")))
        possible_source = regulator_payload.get("source") or regulator_payload.get(
            "url"
        )
        if isinstance(possible_source, str):
            sources.append(possible_source)
        notes.append("Regulator registry corroboration")
        confidence = max(confidence, 80)
        alternate_names.extend(_ensure_list(regulator_payload.get("knownAliases", [])))
        if investigate_rebrands:
            change_note = _extract_first(
                regulator_payload,
                ["ownershipChange", "rebrandNote", "tradingAs"],
            )
            if change_note:
                investigation_notes.append(str(change_note))

    directory_payload: dict[str, Any] | None = None
    if config.ALLOW_NETWORK_RESEARCH:
        directory_payload = query_professional_directory(organisation)

    if directory_payload:
        for entry in _iterate_results(directory_payload):
            source_url = entry.get("website") or entry.get("url")
            if source_url:
                sources.append(str(source_url))
            new_site = entry.get("website")
            if isinstance(new_site, str) and new_site and not website:
                website = new_site
            if not contact_person:
                contact_person = entry.get("contact") or entry.get("contactPerson")
            if not contact_email:
                contact_email = entry.get("email")
            if not contact_phone:
                contact_phone = entry.get("phone")
            if not physical_address:
                physical_address = entry.get("address")
        if directory_payload:
            notes.append("Professional directory corroboration")
            confidence = max(confidence, 65)

    if include_press and config.ALLOW_NETWORK_RESEARCH:
        press_payload = query_press(organisation)
    else:
        press_payload = None

    if press_payload:
        articles = _ensure_list(press_payload.get("articles"))
        for article in articles:
            url = article.get("url") or article.get("link")
            if url:
                sources.append(str(url))
            if investigate_rebrands and _contains_keyword(article, _REBRAND_KEYWORDS):
                headline = article.get("title") or article.get("headline")
                summary = article.get("summary") or article.get("description")
                investigation_notes.append(
                    f"Press coverage: {headline or 'Unnamed article'} — {summary or 'See source.'}"
                )
        if articles:
            notes.append("Press monitoring located supporting coverage")
            confidence = max(confidence, 60)

    # Encourage intelligent follow-up when website domain changes
    if investigate_rebrands and website and baseline.website_url:
        old_domain = canonical_domain(baseline.website_url)
        new_domain = canonical_domain(website)
        if old_domain and new_domain and old_domain != new_domain:
            investigation_notes.append(
                f"Website changed from {old_domain} to {new_domain}; verify if organisation renamed or changed ownership."
            )

    normalized_phone, phone_issues = normalize_phone(contact_phone)
    if normalized_phone:
        contact_phone = normalized_phone
    elif phone_issues and contact_phone:
        investigation_notes.append(
            "Phone number could not be normalised to +27 format."
        )

    return ResearchFinding(
        website_url=website,
        contact_person=contact_person,
        contact_email=contact_email,
        contact_phone=contact_phone,
        sources=_deduplicate(sources),
        notes="; ".join(notes),
        confidence=confidence,
        alternate_names=_deduplicate(alternate_names),
        investigation_notes=_deduplicate(investigation_notes),
        physical_address=physical_address,
    )


def _extract_first(payload: dict[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    nested = payload.get("contact") or payload.get("details")
    if isinstance(nested, dict):
        for key in keys:
            value = nested.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _iterate_results(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
    candidates = []
    for key in ("results", "entries", "data"):
        maybe = payload.get(key)
        if isinstance(maybe, list):
            candidates.extend(maybe)
    if candidates:
        return [item for item in candidates if isinstance(item, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


def _contains_keyword(article: dict[str, Any], keywords: tuple[str, ...]) -> bool:
    haystacks = []
    for key in ("title", "headline", "summary", "description"):
        value = article.get(key)
        if isinstance(value, str):
            haystacks.append(value.lower())
    for hay in haystacks:
        if any(keyword in hay for keyword in keywords):
            return True
    return False


def _deduplicate(values: Iterable[Any]) -> list[Any]:
    seen: list[Any] = []
    for value in values:
        if not value:
            continue
        if value in seen:
            continue
        seen.append(value)
    return seen


class ExternalSourceFetcher:
    """Legacy stub retained for backwards-compatible tests."""

    pass
