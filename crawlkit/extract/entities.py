"""Entity extraction and enrichment helpers for Crawlkit."""

from __future__ import annotations

import re
from typing import Iterable

from ..types import DistilledDoc, Entities

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_RE = re.compile(
    r"""
    \+?27[0-9]{9}|
    (?:0[1-9][0-9]{1})[0-9]{7}
    """,
    re.VERBOSE,
)
PERSON_RE = re.compile(r"(?P<name>[A-Z][a-z]+\s+[A-Z][a-z]+)")


def _unique(sequence: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[tuple[str, object], ...]] = set()
    results: list[dict[str, object]] = []
    for item in sequence:
        key_items: list[tuple[str, object]] = []
        for key, value in sorted(item.items()):
            if isinstance(value, list):
                key_items.append((key, tuple(value)))
            elif isinstance(value, dict):
                key_items.append((key, tuple(sorted(value.items()))))
            else:
                key_items.append((key, value))
        key = tuple(key_items)
        if key in seen:
            continue
        seen.add(key)
        results.append(item)
    return results


def _mx_status(domain: str | None) -> str:
    if not domain:
        return "mx_unchecked"
    try:  # pragma: no cover - optional dependency
        import dns.resolver
    except Exception:  # pragma: no cover - optional dependency missing
        return "mx_unchecked"
    try:
        answers = dns.resolver.resolve(domain, "MX")
    except Exception:
        return "mx_missing"
    return "mx_only" if answers else "mx_missing"


def extract_entities(
    doc: DistilledDoc, enrich: bool = True, domain_hint: str | None = None
) -> Entities:
    """Extract entities from a :class:`DistilledDoc`."""

    emails: list[dict[str, object]] = []
    phones: list[dict[str, object]] = []
    people: list[dict[str, object]] = []

    for match in EMAIL_RE.finditer(doc.markdown):
        address = match.group(0).lower()
        domain = address.split("@", 1)[1]
        status = "mx_unchecked"
        if enrich:
            status = _mx_status(domain_hint or domain)
        emails.append(
            {
                "address": address,
                "domain": domain,
                "status": status,
                "sources": [doc.url],
            }
        )

    for match in PHONE_RE.finditer(doc.markdown):
        number = re.sub(r"[^0-9+]", "", match.group(0))
        if number.startswith("0"):
            number = "+27" + number[1:]
        if not number.startswith("+"):
            number = "+" + number
        phones.append({"number": number, "kind": "business", "sources": [doc.url]})

    if doc.microdata.get("json_ld"):
        for entry in doc.microdata["json_ld"]:
            if not isinstance(entry, dict):
                continue
            entry_type = entry.get("@type")
            if entry_type in {"Person", "Organization"}:
                name = entry.get("name")
                if isinstance(name, str):
                    people.append(
                        {
                            "name": name,
                            "role": entry.get("jobTitle"),
                            "sources": [doc.url],
                        }
                    )

    for match in PERSON_RE.finditer(doc.text):
        name = match.group("name")
        people.append({"name": name, "role": None, "sources": [doc.url]})

    emails = _unique(emails)
    phones = _unique(phones)
    people = _unique(people)

    org = {}
    if doc.meta.get("og:title"):
        org["name"] = doc.meta["og:title"]
    elif doc.meta.get("title"):
        org["name"] = doc.meta["title"]
    if doc.meta.get("description"):
        org["description"] = doc.meta["description"]

    return Entities(people=people, emails=emails, phones=phones, org=org, aviation=None)


__all__ = ["extract_entities"]
