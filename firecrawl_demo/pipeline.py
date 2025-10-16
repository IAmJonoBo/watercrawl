"""Core enrichment pipeline orchestrating Firecrawl lookups with compliance."""

from __future__ import annotations

import itertools
import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

from . import config
from .compliance import (
    append_evidence_log,
    canonical_domain,
    confidence_for_status,
    describe_changes,
    determine_status,
    evidence_entry,
    normalize_phone,
    normalize_province,
    payload_hash,
    validate_email,
)
from .excel import (
    append_enrichment_columns,
    load_cleaned_dataframe,
    load_school_records,
    write_outputs,
)
from .firecrawl_client import FirecrawlClient, summarize_extract_payload
from .models import EnrichmentResult, SchoolRecord


# --- Runbook Plan Logging ---
def build_run_plan(total_records: int, run_records: int) -> dict:
    """Build a run plan dictionary for logging and compliance tracking."""
    return {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds"),
        "total_records": total_records,
        "run_records": run_records,
        "notes": f"Run started for {run_records} of {total_records} records.",
    }


def _register_plan(plan: dict) -> None:
    """Append the run plan to the provenance log for audit trail."""
    path = config.PROVENANCE_CSV
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(plan) + "\n")


logger = logging.getLogger(__name__)

PRIMARY_EXTRACT_PROMPT = (
    "Summarize the official contact details, physical address, regulatory accreditations, "
    "fleet overview, and any program highlights for this flight school. Provide JSON keys: "
    "contact_person, contact_email, contact_phone, physical_address, accreditation, fleet_overview."
)

SOCIAL_SEARCH_QUERIES = [
    "{name} site:linkedin.com",
    "{name} site:facebook.com",
]


def enrich_dataset(api_key: str, *, dry_run_limit: Optional[int] = None) -> None:
    client = FirecrawlClient(api_key=api_key)
    all_records = load_school_records()
    total_records = len(all_records)
    records = all_records[:dry_run_limit] if dry_run_limit is not None else all_records

    plan = build_run_plan(total_records, len(records))
    _register_plan(plan)

    provenance_rows: List[Dict[str, Any]] = []
    enrichment_results: List[EnrichmentResult] = []
    evidence_rows: List[Dict[str, str]] = []
    relationship_rows: List[Dict[str, Any]] = []
    base_df = load_cleaned_dataframe()

    for row_idx, record in enumerate(records, start=2):
        client.await_rate_limit()
        result, evidence, province = enrich_record(client, record, row_idx)
        enrichment_results.append(result)
        evidence_rows.append(evidence)
        base_row = row_idx - 2
        if 0 <= base_row < len(base_df):
            base_df.at[base_row, "Province"] = province
        provenance_rows.append(
            {
                "Name of Organisation": record.name,
                "Source URL": result.source_url,
                "Website URL": record.website_url,
                "Payload Hash": result.payload_hash,
                "Updated At": result.updated_at.isoformat(timespec="seconds"),
            }
        )
        # --- Relationship graph row (multi-role/person support) ---
        org = record.name
        rels = []
        # Main contact
        person = result.org_details.get("contact_person")
        role = "Contact" if person else None
        email_domain = None
        email = result.org_details.get("contact_email")
        if email and "@" in email:
            email_domain = email.split("@", 1)[-1]
        phone = result.org_details.get("contact_phone")
        province_val = province
        source_url1 = result.source_url
        source_url2 = result.org_details.get("website_url")
        rels.append(
            {
                "org": org,
                "person": person,
                "role": role,
                "email_domain": email_domain,
                "phone": phone,
                "province": province_val,
                "source_url1": source_url1,
                "source_url2": source_url2,
            }
        )
        # Example: add more roles/persons if present in external sources (stub)
        # In real use, parse ext_result for additional contacts/roles
        # for ext_func in [query_regulator_api, query_press, query_professional_directory]:
        #     ext_result = ext_func(record.name)
        #     if ext_result and isinstance(ext_result, dict):
        #         contacts = ext_result.get("contacts", [])
        #         for contact in contacts:
        #             rels.append({
        #                 "org": org,
        #                 "person": contact.get("name"),
        #                 "role": contact.get("role"),
        #                 "email_domain": contact.get("email_domain"),
        #                 "phone": contact.get("phone"),
        #                 "province": province_val,
        #                 "source_url1": contact.get("source_url"),
        #                 "source_url2": source_url2,
        #             })
        relationship_rows.extend(rels)

    enriched_df = append_enrichment_columns(base_df, enrichment_results)
    write_outputs(enriched_df, provenance_rows)
    append_evidence_log(evidence_rows)
    _write_summary(enrichment_results)
    # --- Relationship graph output ---
    import pandas as pd

    rel_path = (
        config.RELATIONSHIPS_CSV
        if hasattr(config, "RELATIONSHIPS_CSV")
        else "data/processed/relationships.csv"
    )
    pd.DataFrame(relationship_rows).to_csv(rel_path, index=False)


def enrich_record(
    client: FirecrawlClient,
    record: SchoolRecord,
    row_id: int,
) -> Tuple[EnrichmentResult, Dict[str, str], str]:
    province = normalize_province(record.province)
    website, supporting_sources = locate_official_website(client, record.name, province)

    scrape_payload: Dict[str, Any] = {}
    extract_payload: Dict[str, Any] = {}
    if website:
        scrape_payload = client.scrape(website)
        extract_payload = client.extract([website], prompt=PRIMARY_EXTRACT_PROMPT)

    structured = summarize_extract_payload(extract_payload)
    social_links = discover_social_links(client, record.name)

    website_url = website or record.website_url
    contact_person = structured.get("contact_person") or record.contact_person
    contact_email = structured.get("contact_email") or record.contact_email
    contact_phone = structured.get("contact_phone") or record.contact_number

    normalized_phone, phone_issues = normalize_phone(contact_phone)
    validated_email, email_issues = validate_email(
        contact_email, canonical_domain(website_url)
    )

    sources = list(
        _unique_sources(
            itertools.chain(
                [s for s in [website_url, record.website_url] if s],
                supporting_sources,
                _extract_payload_sources(scrape_payload, extract_payload),
                [social_links.get("linkedin"), social_links.get("facebook")],
            )
        )
    )
    official_domain = canonical_domain(website_url)
    if not sources:
        logger.debug("No sources collected initially for %s", record.name)
    evidence_ok = _has_sufficient_evidence(sources, official_domain)

    if not evidence_ok:
        extras = _augment_evidence_sources(
            client,
            record.name,
            province,
            official_domain,
            sources,
        )
        if extras:
            logger.debug("Added %d evidence source(s) for %s", len(extras), record.name)
            sources.extend(extras)
            evidence_ok = _has_sufficient_evidence(sources, official_domain)

    has_named_contact = bool(contact_person and "@" not in (contact_person or ""))
    status = determine_status(
        has_website=bool(website_url),
        has_named_contact=has_named_contact,
        phone_issues=phone_issues,
        email_issues=email_issues,
        evidence_ok=evidence_ok,
    )

    compliance_notes = _compose_notes(
        phone_issues, email_issues, evidence_ok, has_named_contact
    )
    confidence = confidence_for_status(status, len(compliance_notes))

    # --- Error and Compliance Logging ---
    if not evidence_ok:
        logger.warning(f"Evidence shortfall for {record.name}: sources={sources}")
    if status == "Needs Review":
        logger.warning(f"Needs Review: {record.name} - Reason(s): {compliance_notes}")
    if status == "Do Not Contact (Compliance)":
        logger.warning(
            f"Compliance block: {record.name} - Reason(s): {compliance_notes}"
        )
    if email_issues:
        logger.info(f"Email issues for {record.name}: {email_issues}")
    if phone_issues:
        logger.info(f"Phone issues for {record.name}: {phone_issues}")

    enriched_contact = {
        "Contact Person": contact_person,
        "Contact Email Address": validated_email,
        "Contact Number": normalized_phone,
    }
    original_contact = {
        "Contact Person": record.contact_person,
        "Contact Email Address": record.contact_email,
        "Contact Number": record.contact_number,
    }

    org_details = {
        "website_url": website_url,
        "contact_person": contact_person,
        "contact_email": validated_email,
        "contact_phone": normalized_phone,
        "physical_address": structured.get("physical_address"),
        "accreditation": structured.get("accreditation"),
        "fleet_overview": structured.get("fleet_overview"),
        "linkedin_url": social_links.get("linkedin"),
        "facebook_url": social_links.get("facebook"),
    }
    result = EnrichmentResult(
        source_url=website,
        status=status,
        confidence=confidence,
        updated_at=datetime.utcnow(),
        payload_hash=payload_hash(
            {
                "scrape": scrape_payload,
                "extract": extract_payload,
            }
        ),
        org_details=org_details,
    )

    evidence = evidence_entry(
        row_id=row_id,
        organisation=record.name,
        changes=describe_changes(original_contact, enriched_contact),
        sources=sources,
        notes=_evidence_notes(evidence_ok, sources) or "",
        confidence=confidence,
    )
    return result, evidence, province


def locate_official_website(
    client: FirecrawlClient,
    name: str,
    province: str,
) -> Tuple[Optional[str], List[str]]:
    query = f"{name} flight school {province}"
    payload = client.search(query)
    candidates: List[Tuple[int, str]] = []
    data = getattr(payload, "data", None)
    if isinstance(data, dict):
        web = data.get("web")
        if isinstance(web, list):
            for row in web:
                url = row.get("url") if isinstance(row, dict) else None
                if not isinstance(url, str):
                    continue
                normalized = _ensure_https(url)
                domain = canonical_domain(normalized)
                if not normalized or not domain:
                    continue
                score = _score_candidate(domain, name)
                if score > 0:
                    candidates.append((score, normalized))
    if not candidates:
        return None, []
    candidates.sort(key=lambda item: item[0], reverse=True)
    primary = candidates[0][1]
    supporting = [url for _, url in candidates[1:4]]
    return primary, supporting


def discover_social_links(
    client: FirecrawlClient, name: str
) -> Dict[str, Optional[str]]:
    results: Dict[str, Optional[str]] = {"linkedin": None, "facebook": None}
    for template in SOCIAL_SEARCH_QUERIES:
        query = template.format(name=name)
        payload = client.search(query)
        data = getattr(payload, "data", None)
        if not isinstance(data, dict):
            continue
        for url in _collect_search_urls(payload):
            if "linkedin.com" in url and not results["linkedin"]:
                results["linkedin"] = _ensure_https(url)
            if "facebook.com" in url and not results["facebook"]:
                results["facebook"] = _ensure_https(url)
    return results


def _extract_payload_sources(
    scrape_payload: Dict[str, Any], extract_payload: Dict[str, Any]
) -> List[str]:
    sources: List[str] = []
    data = scrape_payload.get("data") if isinstance(scrape_payload, dict) else None
    if isinstance(data, dict):
        source_url = data.get("url")
        if isinstance(source_url, str):
            sources.append(_ensure_https(source_url))
    data = extract_payload.get("data") if isinstance(extract_payload, dict) else None
    if isinstance(data, dict):
        meta_sources = data.get("sources")
        if isinstance(meta_sources, list):
            for item in meta_sources:
                if isinstance(item, str):
                    sources.append(_ensure_https(item))
    return sources


def _unique_sources(sources: Iterable[Optional[str]]) -> Iterable[str]:
    seen: set[str] = set()
    for source in sources:
        if not source:
            continue
        normalized = _ensure_https(source)
        if normalized in seen:
            continue
        seen.add(normalized)
        yield normalized


def _ensure_https(url: str) -> str:
    parsed = urlparse(url.strip())
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc or parsed.path
    path = parsed.path if parsed.netloc else ""
    rebuilt = f"{scheme}://{netloc}{path}"
    if not rebuilt.startswith("https://"):
        rebuilt = "https://" + rebuilt.split("://", 1)[-1]
    return rebuilt.rstrip("/")


def _score_candidate(domain: str, organisation_name: str) -> int:
    score = 0
    tokens = _organisation_tokens(organisation_name)
    if domain.endswith(".za"):
        score += 2
    if any(token in domain for token in tokens):
        score += 3
    if domain.count("-") <= 2:
        score += 1
    return score


def _organisation_tokens(name: str) -> List[str]:
    stop_words = {"flight", "school", "academy", "aviation", "pty", "ltd"}
    return [
        token
        for token in re.split(r"\W+", name.lower())
        if token and token not in stop_words
    ]


def _has_sufficient_evidence(
    sources: Sequence[str], official_domain: Optional[str]
) -> bool:
    if len(sources) < config.MIN_EVIDENCE_SOURCES:
        return False
    if not official_domain:
        return False
    return any(canonical_domain(source) == official_domain for source in sources)


def _compose_notes(
    phone_issues: Sequence[str],
    email_issues: Sequence[str],
    evidence_ok: bool,
    has_named_contact: bool,
) -> List[str]:
    notes: List[str] = []
    notes.extend(phone_issues)
    notes.extend(email_issues)
    if not evidence_ok:
        notes.append("Insufficient evidence sources")
    if not has_named_contact:
        notes.append("Missing named contact")
    return notes


def _evidence_notes(evidence_ok: bool, sources: Sequence[str]) -> Optional[str]:
    if evidence_ok:
        return None
    return f"Evidence shortfall: collected {len(sources)} source(s)"


def _write_summary(results: Sequence[EnrichmentResult]) -> None:
    if not results:
        return
    status_counts: Dict[str, int] = {}
    for result in results:
        status_counts[result.status] = status_counts.get(result.status, 0) + 1
    total = len(results)
    verified = status_counts.get("Verified", 0)
    candidate = status_counts.get("Candidate", 0)
    needs_review = status_counts.get("Needs Review", 0)
    notes: List[str] = []
    if needs_review:
        notes.append(f"{needs_review} record(s) flagged for follow-up")
    if candidate:
        notes.append(
            "candidate entries missing at least one named contact or clean channel"
        )
    summary = f"Processed {total} record(s): {verified} Verified, {candidate} Candidate, {needs_review} Needs Review."
    if notes:
        summary += " Key gaps: " + "; ".join(notes) + "."
    summary += " Next focus: close evidence gaps and upgrade candidate contacts."
    config.SUMMARY_TXT.parent.mkdir(parents=True, exist_ok=True)
    config.SUMMARY_TXT.write_text(summary + "\n", encoding="utf-8")


def _collect_search_urls(payload: Dict[str, Any]) -> List[str]:
    results: List[str] = []
    data = getattr(payload, "data", None)
    if isinstance(data, dict):
        web = data.get("web")
        if isinstance(web, list):
            for row in web:
                url = row.get("url") if isinstance(row, dict) else None
                if isinstance(url, str):
                    results.append(_ensure_https(url))
    return results


def _augment_evidence_sources(
    client: FirecrawlClient,
    name: str,
    province: str,
    official_domain: Optional[str],
    existing_sources: Sequence[str],
) -> List[str]:
    extras: List[str] = []
    seen = set(existing_sources)
    for template in config.EVIDENCE_QUERIES:
        query = template.format(name=name, province=province)
        logger.debug("Evidence augmentation search: %s", query)
        payload = client.search(query)
        for url in _collect_search_urls(payload):
            if url in seen:
                continue
            domain = canonical_domain(url)
            # Prefer official domain matches, but accept regulator domains.
            if official_domain and domain == official_domain:
                extras.append(url)
                seen.add(url)
            elif domain and any(
                keyword in domain for keyword in ("caa.co.za", "gov.za", "aviation")
            ):
                extras.append(url)
                seen.add(url)
        if len(seen) >= config.MIN_EVIDENCE_SOURCES and extras:
            break
    return extras
