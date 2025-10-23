---
title: Data Quality & Research Methodology
---

## Validation Rules

- **Provinces**: Must match ACES canonical list (`config.PROVINCES`). Unknown or blank values are normalised to `Unknown` and flagged.
- **Status**: One of `Verified`, `Candidate`, `Needs Review`, `Duplicate`, or `Do Not Contact (Compliance)`. Empty or unrecognised statuses trigger actionable validation issues.
- **Phones**: Converted to `+27XXXXXXXXX`. Numbers that cannot be normalised generate issues recorded against the row.
- **Emails**: Must match the organisation domain. MX checks are performed when DNS tooling is available; otherwise a soft warning is recorded.
- **Confidence**: Evidence confidence scores must be integers between 0 and 100 and remain at or above 70 for publishable records.

## Enrichment Heuristics

1. **Website discovery**: Prefer research adapter findings; fall back to existing row data.
2. **Contact inference**: Named contacts supplied by adapters override blanks. Role inboxes downgrade status to `Candidate`.
3. **Triangulation**: Crawlkit provides the deterministic fetch/distill/entity backbone while optional adapters cross-reference regulator registries, press coverage, professional directories, and Firecrawl (when `FEATURE_ENABLE_FIRECRAWL_SDK=1`). Offline runs log follow-up instructions instead of performing live lookups.
4. **Evidence sourcing**: Merge the organisation website with adapter-provided URLs. If fewer than two _unique_ sources are available or no fresh evidence accompanies a change, the pipeline now blocks the update and records remediation guidance for analysts.
5. **Status promotion**: Rows with website, named contact, valid phone, and domain-aligned email become `Verified`; otherwise `Candidate` or `Needs Review` based on defect severity.
6. **Rename detection**: When a new website domain or alias is discovered, the pipeline logs an investigation note encouraging analysts to confirm potential ownership changes.

## Quality Gate & Rollback Safeguards

- **Quality gate enforcement**: Adapter output only lands when it carries at least two independent sources (one official/regulatory) **and** fresh corroboration beyond the legacy dataset. Adapter confidence for contact/website changes must be ≥70, and phone/email validation failures still force a block.
- **Automatic quarantine**: Blocked rows revert to `Needs Review`, emit a detailed `QualityIssue`, and capture remediation guidance in the evidence log so analysts know what to fix.
- **Metrics & reporting**: `quality_rejections` and `quality_issues` now sit beside enrichment metrics. CLI/MCP/JSON responses surface these counts alongside a structured `RollbackPlan`, with explicit "fresh evidence" notes when the gate fires.
- **Rollback actions**: Every rejection lists the affected columns and previous values so analysts (or downstream automation) can restore the dataset without manual diffing.
- **Operational visibility**: When the quality gate fires, the CLI prints a rollback summary, while automation surfaces the same context via JSON for observability pipelines.

## Research Adapter Guidance

- Build adapters that return `ResearchFinding` objects with:
  - `sources`: ≥2 URLs, one official/regulatory where possible.
  - `notes`: Concise justification of the enrichment decision.
  - `confidence`: Integer 0–100 reflecting evidence strength.
- Keep adapters stateless; persist caching or rate limiting externally.
- Add new adapters under `watercrawl.integrations.research` or compose them within the pipeline factory.

## Phase 1.1 — Great Expectations + dbt quality suites

Phase 1.1 introduces automated contracts that gate curated outputs before they
leave the enrichment pipeline. The delivery slices are:

- ✅ **Suite scaffolding (Week 1) complete**: the repository now includes a
  `data_contracts/great_expectations/` project with a `curated_dataset`
  covering schema, province/status taxonomies, HTTPS websites, and contact
  hygiene checks. Run it locally via the `contracts` CLI command to produce
  analyst-friendly failure reports and CI-friendly exit codes.
- ✅ **dbt contract alignment (Week 2) complete**: a lightweight dbt project now
  lives under `data_contracts/analytics/` with a `stg_curated_dataset` model that reads CSV
  exports via DuckDB. Column typing, accepted values, and custom tests for HTTPS
  websites, email → domain alignment, and +27 phone formats keep dbt coverage in
  lock-step with the Great Expectations suite. CI runs `dbt build --select
  tag:contracts` alongside the checkpoint so both suites gate merges.
- ✅ **Operationalisation (Week 3) complete**: the CLI `contracts` command now
  executes Great Expectations and dbt in the same run, persists run artefacts to
  `data/contracts/<timestamp>/`, and appends an evidence-log entry referencing
  the suite snapshot. MCP orchestration inherits the same behaviour, keeping
  offline runs deterministic while preserving audit trails.

The contract suite now centralises canonical taxonomies and evidence thresholds
via `CONTRACTS_CANONICAL_JSON`, ensuring dbt macros and Great Expectations share
the same province/status lists and a confidence minimum of 70. The curated model
exposes a numeric `confidence` column which both toolchains validate against the
shared threshold.

Deliverables include the expectation suite, dbt project, CI wiring, and MkDocs
documentation summarising rule coverage and remediation playbooks.

## Phase 1.2 — Pint + Hypothesis contract tests

Phase 1.2 extends contract coverage to spreadsheet ingest and computed fields.

- ✅ **Unit-aware schema enforcement**
  - `watercrawl.core.excel.normalize_numeric_units` now uses Pint to coerce
    spreadsheet-provided fleet counts and runway lengths into canonical units,
    rejecting incompatible unit strings before they enter the pipeline.
  - Numeric enforcement applies to both CSV and Excel ingest with consistent
    handling of blank and missing values.
- ✅ **Property-based regression suite**
  - Hypothesis-driven tests in `tests/test_excel.py` fuzz spreadsheet inputs,
    asserting province/status normalisation and unit conversions across mixed
    representations.
  - Edge cases (dimensionless counts, mixed case provinces, empty cells) are
    automatically explored and shrunk to reproducible counter-examples if they
    regress.
- 🚧 **CI + observability**
  - Local runs are wired into `pytest -k normalizes` today; wiring Hypothesis
    contract telemetry into the CLI and dashboards remains on the backlog.

Exit criteria for Phase 1.2 now focus on surfacing the contract suite via CI
telemetry and observability dashboards, building on the Pint + Hypothesis
foundation shipped in this iteration.
