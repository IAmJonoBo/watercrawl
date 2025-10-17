# Data Quality & Research Methodology

## Validation Rules

- **Provinces**: Must match ACES canonical list (`config.PROVINCES`). Unknown or blank values are normalised to `Unknown` and flagged.
- **Status**: One of `Verified`, `Candidate`, `Needs Review`, `Duplicate`, or `Do Not Contact (Compliance)`. Empty or unrecognised statuses trigger actionable validation issues.
- **Phones**: Converted to `+27XXXXXXXXX`. Numbers that cannot be normalised generate issues recorded against the row.
- **Emails**: Must match the organisation domain. MX checks are performed when DNS tooling is available; otherwise a soft warning is recorded.

## Enrichment Heuristics

1. **Website discovery**: Prefer research adapter findings; fall back to existing row data.
2. **Contact inference**: Named contacts supplied by adapters override blanks. Role inboxes downgrade status to `Candidate`.
3. **Triangulation**: The default adapter cross-references Firecrawl (when enabled), regulator registries, press coverage, and professional directories. Offline runs log follow-up instructions instead of performing live lookups.
4. **Evidence sourcing**: Merge the organisation website with adapter-provided URLs. If fewer than two *unique* sources are available or no fresh evidence accompanies a change, the pipeline now blocks the update and records remediation guidance for analysts.
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
- Add new adapters under `firecrawl_demo.research` or compose them within the pipeline factory.

## Phase 1.1 — Great Expectations + dbt quality suites

Phase 1.1 introduces automated contracts that gate curated outputs before they
leave the enrichment pipeline. The delivery slices are:

- ✅ **Suite scaffolding (Week 1) complete**: the repository now includes a
  `great_expectations/` project with a `curated_dataset` expectation suite
  covering schema, province/status taxonomies, HTTPS websites, and contact
  hygiene checks. Run it locally via
  `poetry run python -m firecrawl_demo.cli contracts data/output.csv` to produce
  analyst-friendly failure reports and CI-friendly exit codes.
- **Suite scaffolding (Week 1)**
  - Stand up a `great_expectations/` project rooted in the repo to co-locate
    batch checkpoints with sample data extracts.
  - Mirror core validation logic (province list, status taxonomy, contact
    requirements) as *Expectations* and register them with a `curated_dataset`
    expectation suite.
  - Generate `data_docs` artefacts and publish them via MkDocs so analysts can
    audit the rule catalogue.
- **dbt contract alignment (Week 2)**
  - Introduce a lightweight dbt project under `analytics/` with staging models
    for the canonical flight school dataset.
  - Encode column types, accepted values, and referential checks using dbt
    schema tests; add custom tests for evidence source counts and enriched
    contact completeness.
  - Configure CI to run `dbt test` alongside the Great Expectations checkpoint
    so both suites must pass before merge.
- **Operationalisation (Week 3)**
  - Wire the CLI and MCP paths to execute the `great_expectations` checkpoint
    when `ALLOW_NETWORK_RESEARCH=0` to preserve determinism.
  - Persist expectation suite snapshots to the evidence log to prove which
    contracts ran for each dataset revision.
  - Track coverage with a target of ≥95% of curated columns having at least one
    expectation or dbt test before promoting Phase 1 exit criteria.

Deliverables include the expectation suite, dbt project, CI wiring, and MkDocs
documentation summarising rule coverage and remediation playbooks.

## Phase 1.2 — Pint + Hypothesis contract tests

Phase 1.2 extends contract coverage to spreadsheet ingest and computed fields.

- **Unit-aware schema enforcement**
  - Add Pint unit registries for every numeric column (e.g., fleet counts,
    runway lengths) and assert conversions during ingest so inconsistent units
    surface immediately.
  - Provide deterministic fixtures representing edge-case spreadsheets (mixed
    units, missing dimensions) to validate the enforcement path.
- **Property-based regression suite**
  - Use Hypothesis strategies to fuzz spreadsheet ingestion, targeting
    `firecrawl_demo.excel` and downstream transformation helpers.
  - Model invariants such as "province is normalised", "status taxonomy remains
    within the allowed set", and "evidence source count never drops below two".
  - Emit shrinking artefacts into the evidence log when Hypothesis finds a
    counterexample so analysts can reproduce locally.
- **CI + observability**
  - Gate merges on the property-based suite (`pytest -k contract`) and surface
    failure summaries in the CLI telemetry.
  - Add dashboard panels that track contract runtime, pass rate, and the top
    failing invariants to expedite triage.

Exit criteria for Phase 1.2 are a green property-based suite, Pint-enforced
ingest paths, and documentation that walks analysts through responding to
contract failures.
