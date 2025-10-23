# Research Pipeline Orchestration

The enrichment pipeline orchestrates multiple intelligence sources through the
`MultiSourceResearchAdapter`. Each connector contributes structured evidence
while enforcing POPIA guardrails and polite crawling semantics.

## Connector topology

The adapter composes four deterministic connectors:

- **Regulator** – prioritises official SACAA and regulator payloads for websites,
  contact, and licensing metadata.
- **Press** – surfaces recent coverage and rebrand signals while avoiding
  personal data.
- **Corporate filings** – inspects professional directories and corporate
  registries for addresses and ownership artefacts.
- **Social** – captures social-footprint breadcrumbs when available for manual
  review.

Connector enablement, rate limits, and privacy overrides are configured in the
active refinement profile (`profiles/*.yaml`). Each connector entry accepts:

```yaml
research:
  allow_personal_data: false
  rate_limit_seconds: 0.3
  connectors:
    regulator:
      enabled: true
      rate_limit_seconds: 0.25
    corporate_filings:
      enabled: true
      allow_personal_data: false
```

White-label tenants can ship profiles that toggle connectors or adjust rate
limits without code changes. The adapter consults
`config.RESEARCH_CONNECTOR_SETTINGS` at runtime, so per-tenant overrides take
immediate effect.

## Privacy and POPIA compliance

- `allow_personal_data` guards whether connectors may emit named contacts,
  direct emails, or phone numbers. When disabled, sensitive fields are filtered
  and flagged in the evidence payload.
- Normalisation logic enforces `+27` E.164 formatting and role-inbox policies
  defined in the profile.
- `ALLOW_NETWORK_RESEARCH=1` must be set to permit live HTTP requests. Without
  it, connectors degrade gracefully and emit advisory notes.
- `FEATURE_ENABLE_CRAWLKIT=1` enables the first-party Crawlkit adapters. `FEATURE_ENABLE_FIRECRAWL_SDK=1` then opts into the optional SDK once network research is authorised.

## Cross-validation and confidence scoring

The cross-validation engine (`validators.py`) inspects aggregated findings to:

- Confirm phone/E.164 parity.
- Check leadership titles for seniority markers.
- Compare email and website domains, annotating contradictions for the quality
  gate.
- Record domain history mismatches for rebrand investigations.

Each pipeline run emits connector-level evidence via
`ResearchFinding.evidence_by_connector`, capturing latency, success, and any
privacy filters applied. `ResearchFinding.validation` stores the computed
confidence adjustment and the detailed check outcomes.

## Pipeline metrics

`Pipeline._LookupMetrics` aggregates new telemetry:

- `connector_latency[connector]` – per-connector execution timings.
- `connector_success[connector]` – success/failure booleans for hit ratios.
- `confidence_deltas` – tuples of `(base, adjustment, final)` confidence scores
  per lookup.

These metrics complement the existing queue-latency and retry counters and are
available to downstream Prometheus exporters.

## Required configuration and environment

| Setting | Purpose |
| --- | --- |
| `REFINEMENT_PROFILE` / `REFINEMENT_PROFILE_PATH` | Selects the profile that defines connector toggles and privacy policy. |
| `ALLOW_NETWORK_RESEARCH` | Enables outbound HTTP requests for connectors. |
| `FEATURE_ENABLE_CRAWLKIT` | Toggle Crawlkit fetch/distill/orchestrate modules. |
| `FEATURE_ENABLE_FIRECRAWL_SDK` | Optional Firecrawl enrichment once Crawlkit is enabled and credentials are supplied. |
| `FEATURE_ENABLE_PRESS_RESEARCH`, `FEATURE_ENABLE_REGULATOR_LOOKUP` | Legacy feature flags remain honoured for compatibility. |

When deploying to white-label tenants, ensure profiles document which
connectors are enabled and whether personal data collection is permissible.
Profile updates are the single source of truth for these behaviours.
