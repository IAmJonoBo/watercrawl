# Phase 2 — Lineage & Lakehouse Implementation Plan

## Objectives

- Achieve complete lineage coverage for curated datasets using OpenLineage events and W3C PROV-O fact metadata.
- Promote reproducible, versioned storage for enriched tables via Delta Lake or Apache Iceberg.
- Attach each published dataset to an immutable run artefact (DVC or lakeFS) with rollback and reproduce playbooks.
- Update analyst and automation workflows so lineage and lakehouse controls are observable, auditable, and enforced in CI/CD.
- Maintain clear separation between `dev/`, `tools/`, `app/`, and `dist/` so development experiments never bypass hardened
  distribution policies.

## Delivery timeline

| Week | Focus | Key Deliverables | Quality Gates |
|------|-------|------------------|---------------|
| 1 | **OpenLineage emitter** | Instrument `PipelineReport` generation with OpenLineage job/run events; add configuration for namespace, job name, and transport (HTTP/Kafka). | Events emitted for every CLI and MCP run in staging; schema validated with `openlineage-python`. |
| 2 | **PROV-O/DCAT modelling** | Define canonical PROV entities and activities (dataset version, evidence log, enrichment steps); generate DCAT JSON-LD catalog entries. | 100% of curated rows reference a PROV entity; catalogue builds without schema warnings. |
| 3 | **Delta/Iceberg adoption** | Stand up a storage abstraction for writing curated outputs to Delta Lake or Iceberg, backed by DuckDB/Spark runner in CI. | Time-travel restore demonstrated in automated test; ACID invariants validated via dbt tests. |
| 4 | **Versioning automation** | Integrate DVC or lakeFS to capture dataset snapshots; embed commit hashes in lineage payloads and evidence log. | `dvc repro` (or `lakefs fs diff`) recreates the last run end-to-end; commit IDs visible in OpenLineage. |
| 5 | **Operational hardening** | Document rollback, retention, and access policies; extend MkDocs with lineage dashboards and lakehouse runbooks. | Runbooks approved by Platform/Security; CI blocks merge when lineage or versioning artefacts are missing. |

## Workstreams

### 1. OpenLineage integration

- Build a `lineage` module that serialises OpenLineage events from pipeline context (input dataset, run parameters, evidence sink configuration).
- Provide environment-driven configuration: `OPENLINEAGE_URL`, `OPENLINEAGE_NAMESPACE`, `OPENLINEAGE_API_KEY`.
- Capture evidence log paths and DVC/lakeFS commit IDs as OpenLineage `inputs`/`outputs` facets.
- Add pytest coverage to assert that events are produced and schema-valid for the sample dataset.
- ✅ **2025-10-17 update**: `firecrawl_demo.integrations.lineage` now emits OpenLineage start/complete events alongside PROV-O and DCAT artefacts and persists them under `artifacts/lineage/<run_id>/` with regression coverage in `tests/test_lineage.py`.

### 2. PROV-O and DCAT

- Define PROV templates for `Entity` (dataset version, evidence log, source documents) and `Activity` (validation, enrichment, contract enforcement).
- Emit PROV serialisations (JSON-LD) alongside pipeline reports; store them under `artifacts/prov/<run_id>.jsonld`.
- Publish DCAT dataset/page metadata under `docs/catalogue/` and wire MkDocs navigation.
- Create regression tests that parse the JSON-LD and ensure required properties (title, description, temporal coverage, distribution URL) are present.

### 3. Lakehouse foundation

- Choose a default table format (Delta Lake preferred) with Iceberg as a configurable alternative.
- Abstract write operations in the pipeline so curated tables pass through a `LakehouseWriter` interface.
- Implement local CI support using DuckDB with the `delta-rs` bindings; document production expectations for Spark or Trino deployments.
- Add dbt models to read from the Delta/Iceberg tables, ensuring contract suites continue to run against lakehouse-backed storage.
- ✅ **2025-10-17 update**: Introduced `LocalLakehouseWriter` and manifest metadata scaffold writing Parquet snapshots to a configurable lakehouse root while capturing versioned manifests for future DVC/lakeFS integration.

### 4. Versioning and reproducibility

- Evaluate DVC vs lakeFS based on hosting constraints; prototype both if time allows.
- Automate snapshot creation after each successful pipeline run, attaching metadata (input hash, expectation suite version, OpenLineage run ID).
- Extend CLI with `pipeline reproduce --run-id <id>` to fetch the correct snapshot and rerun enrichment deterministically.
- Capture reproduction success metrics in `Next_Steps.md` quality gates.
- ✅ **2025-10-17 update**: Added `VersioningManager` and deterministic dataframe fingerprinting so every run records a
  `version.json` manifest containing input/output hashes, reproduction commands, and links to the lakehouse manifest. Dev and dist
  environments consume the same metadata structure but dist disables Codex integrations to honour crawler guardrails.

### 5. Governance & documentation

- Update `docs/operations.md` with lineage/lakehouse runbooks, including access controls and retention policies.
- Provide troubleshooting guides for missing lineage events, failed ACID commits, or versioning drift.
- Record decision trade-offs (Delta vs Iceberg, DVC vs lakeFS) in future ADRs.
- Align security reviews with POPIA compliance, ensuring provenance artefacts do not leak personal data.
- ✅ **2025-10-17 update**: CLI enrichment output now surfaces lineage artefact directories, enabling operators to verify provenance bundles during runbooks.
- ✅ **2025-10-17 update**: Created top-level `dev/`, `tools/`, `app/`, and `dist/` directories with role-specific README files
  to guide analysts, developers, and operators through the appropriate workflows and QA gates.

## Risks & mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| OpenLineage event schema drift | CI failures and broken observability | Lock event schema tests against pinned `openlineage-python` and add contract tests in CI. |
| Delta/Iceberg operational overhead | Increased infrastructure complexity | Start with Delta via `delta-rs` for local runs; document migration path to managed lakehouse services. |
| Versioning storage costs | Higher object storage spend | Configure retention policies and pruning jobs; tag critical snapshots for long-term retention. |
| Sensitive data in provenance artefacts | POPIA compliance breach | Redact PII from PROV/DCAT outputs; include compliance review in release checklist. |

## Next actions

1. Finalise technology selections (Delta vs Iceberg, DVC vs lakeFS) with Platform by end of Week 1.
2. Implement OpenLineage emitter prototype and capture sample events in CI artefacts.
3. Draft MkDocs updates and runbook outlines for lineage/lakehouse operations.
4. Schedule security review once provenance and versioning artefacts are generated in staging.
