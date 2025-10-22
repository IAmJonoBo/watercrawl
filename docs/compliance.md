# Compliance Workflows

This guide explains how POPIA-aligned compliance is enforced throughout the
ACES Aerodynamics enrichment pipeline. It covers lawful-basis configuration,
transparency notifications, audit exports, and the automated re-validation
cadence introduced in the compliance review module.

## Configuration

Compliance behaviour is defined in the active refinement profile. The default
profile (`profiles/za_flight_schools.yaml`) now exposes:

- `compliance.lawful_basis` and `default_lawful_basis` to declare the permitted
  legal bases for processing and set the default applied when no override is
  present.
- `compliance.contact_purposes` and `default_contact_purpose` describing why a
  contact may be reached.
- `compliance.notification_templates` to point at tenant-specific transparency
  templates (for example `templates/transparency_notice.md`).
- `compliance.revalidation_days` which controls the age threshold before a
  contact must be re-verified.
- `compliance.audit_exports` enumerating the supported export formats generated
  by downstream automation (`csv` and `jsonl` are bundled by default).

The configuration is surfaced in `firecrawl_demo.core.config` as:

- `COMPLIANCE_LAWFUL_BASES`
- `COMPLIANCE_CONTACT_PURPOSES`
- `COMPLIANCE_NOTIFICATION_TEMPLATES`
- `COMPLIANCE_REVALIDATION_DAYS`

These values are consumed by `firecrawl_demo.application.compliance_review`
whenever a row is processed.

## Compliance Review

`firecrawl_demo/application/compliance_review.py` introduces a
`ComplianceReview` that executes for every row processed by the enrichment
pipeline. It:

1. Annotates evidence records with the active lawful basis and contact purpose.
2. Tracks consecutive MX validation failures. When an email fails MX lookups
   twice the record is downgraded to `Do Not Contact (Compliance)` and a
   follow-up task is emitted.
3. Records `last_verified_at` timestamps when a row reaches the `Verified`
   status without outstanding phone/email issues.
4. Issues recommended follow-up tasks (for example sending the configured
   transparency notice) which are appended to the evidence log as
   zero-confidence entries.
5. Captures re-validation metadata (next review due date, lawful basis, contact
   purpose, MX failure count) inside a `ComplianceScheduleEntry` that becomes
   part of the pipeline report.

## Automation Hooks

The new module `apps/automation/qa_tasks.py` provides helpers to operationalise
compliance metadata:

- `due_for_revalidation` returns entries whose next review date has passed.
- `build_revalidation_tasks` emits actionable tasks that QA automation can use
  to re-queue rows whose evidence is stale or whose MX checks have failed
  repeatedly.
- `suppressed_contacts` extracts the IDs of all rows currently in the
  `Do Not Contact (Compliance)` state, making it trivial to keep suppression
  lists aligned with the latest evidence.

The automation CLI can import these helpers to schedule nightly verification
jobs or to notify tenants when outreach is blocked by MX failures.

## Evidence and Audit Trail

Every call to `ComplianceReview` emits required disclosures into the evidence
notes so that analysts and auditors can see which lawful basis applied, why a
contact will be approached, and whether any privacy restrictions (opt-outs or
ToS blocks) were encountered.

Follow-up tasks are appended to the evidence log alongside the primary change
record. This means the CSV/JSONL exports driven by the evidence sink already
contain the “send transparency notice” directive and similar compliance
checkpoints. Audit exports listed under `compliance.audit_exports` should be
updated to include these additional rows so that downstream systems can import
and track completion of mandated communications.

## Robots.txt and Terms of Service

The deterministic research connectors now enforce the politeness policy
(`firecrawl_demo.integrations.crawl_policy.CrawlPolicyManager`). Sources that
violate robots.txt rules or present explicit Terms-of-Service prohibitions are
skipped and logged. The compliance review supplements these notes with alternate
query suggestions sourced from `config.EVIDENCE_QUERIES` so analysts have a
fallback channel when primary sources are blocked.

## Tenant Overrides

White-label deployments can override any of the compliance settings by
supplying a custom profile. Typical changes include:

- Setting `default_lawful_basis` to `consent` for tenants that capture explicit
  consent outside the enrichment pipeline.
- Pointing `notification_templates.transparency_notice` at a
  tenant-specific email/SMS template.
- Extending `audit_exports` with storage destinations recognised by the tenant’s
  GRC tooling.

Whenever the profile changes, rerun the pipeline to refresh the compliance
schedule and regenerate evidence records with the new disclosures.
