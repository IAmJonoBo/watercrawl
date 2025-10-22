# Relationship Mapping Layer

The relationship intelligence graph turns enriched tabular outputs into a
multi-tenant knowledge graph that analysts can traverse. It ingests
research findings, evidence connectors, and provenance-rich audit trails to
surface organisation, contact, regulator, and partner relationships.

## Graph artefacts

The enrichment pipeline now emits the following artefacts on every run:

| Artefact | Path | Purpose |
| --- | --- | --- |
| GraphML snapshot | `data/processed/relationships.graphml` | NetworkX/Neo4j-ready graph export with provenance metadata. |
| Node summary | `data/processed/relationships.csv` | CSV summary of organisations, contacts, and sources for analysts and dashboards. |
| Edge summary | `data/processed/relationships_edges.csv` | CSV of relationship edges, including provenance tags and connector hints. |

Pipeline metrics expose node/edge counts and anomaly totals. The graph is
available via the automation plugin surface (`graph_semantics`) and can be
queried locally with `python -m apps.analyst.graph_cli`.

## Tenancy-aware configuration

Relationship exports honour the active refinement profile and its
tenant-specific settings:

* **Connector routing** – each connector (regulator, press, corporate
  filings, social) maps to a tenant-specific publisher label so that
  downstream CRMs can filter evidence sources. Update
  `_CONNECTOR_PUBLISHERS` in `firecrawl_demo/application/pipeline.py` when
  introducing new connectors.
* **Storage directories** – the graph uses the same per-tenant
  `data/processed/` tree as the rest of the pipeline, keeping artefacts
  segregated by deployment target.
* **Feature flags** – the relationship builder only runs when the
  `graph_semantics` integration plugin is enabled, mirroring other
  telemetry surfaces.

To override output paths or disable specific connectors, update the active
profile under `profiles/` and re-run the pipeline. All defaults respect the
South African flight-school deployment baseline.

## POPIA guidance for person nodes

Person nodes are intentionally minimal:

* Stored attributes are limited to **name**, **role**, **phones**, and
  **emails** gathered from public sources.
* Phone numbers are normalised to the South African `+27` E.164 format and
  emails must align with organisation domains.
* Provenance tags record the evidence source, connector, and retrieval
  timestamp so analysts can justify inclusion or trigger removals.
* Contacts inherit the tenant-wide data retention policy; they should be
  reviewed regularly, especially when POPIA opt-outs are received.

No sensitive categories (race, biometric, special personal information) are
stored in the graph. Downstream systems must continue to enforce POPIA
Section 11 lawful processing requirements when reusing these nodes.

## Opt-out workflow

1. **Receipt** – log opt-out requests in the evidence log with supporting
   documents.
2. **Purge** – remove the contact from the source dataset and rerun the
   pipeline; the relationship graph will drop the associated nodes on the
   next export.
3. **Verify** – use `python -m apps.analyst.graph_cli sources-for-phone` or
   `contacts-by-regulator` to confirm the contact no longer appears and that
   no edges reference the phone/email.
4. **Record** – update the evidence log and POPIA audit register with the
   removal details.

Maintaining this workflow ensures compliance with POPIA Section 24 access
and rectification rights while keeping provenance intact for future audits.
