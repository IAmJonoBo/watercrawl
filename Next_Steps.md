# Next Steps

## Tasks

- [x] Baseline remediation plan — Owner: AI — Due: Complete
- [x] Develop enhanced enrichment architecture & pipeline hardening — Owner: AI — Due: Complete
- [x] Implement CLI + MCP bridge for task orchestration — Owner: AI — Due: Complete
- [x] Stand up MkDocs documentation portal — Owner: AI — Due: Complete
- [x] Integrate secrets manager for production credentials — Owner: AI — Due: Complete
- [x] Introduce research adapter registry with config-driven sequencing — Owner: AI — Due: 2025-10-16
- [ ] Package exemplar regulator/press/ML adapters for registry adoption — Owner: Platform Team — Due: Backlog

## Steps

- [x] Document current-state architecture and gaps
- [x] Design target-state modules (data ingestion, validation, enrichment, evidence logging)
- [x] Implement incremental code/test updates per module
- [x] Integrate QA gates (lint, type, security, tests) into workflow
- [x] Add registry module + builder integration with fallback safety
- [x] Extend research tests for ordering, deduplication, and feature-flag coverage
- [x] Document adapter authoring workflow in architecture guide

## Deliverables

- [x] Updated enrichment pipeline with validated + auto-enriched CSV/XLSX processing
- [x] CLI entrypoints for batch runs, validation, and reporting
- [x] Minimal MCP server contract for Copilot orchestration
- [x] MkDocs site with methodology, API, and operations docs
- [x] Registry-enabled research pipeline supporting Firecrawl+Null defaults and config overrides
- [x] Adapter authoring guidance in docs/architecture.md

## Quality Gates

- [x] Tests: pytest with coverage >= existing baseline (TBD after remediation)
- [x] Lint: Ruff/Black/Isort clean
- [x] Type: mypy clean with strict config (to be defined)
- [x] Security: bandit critical findings resolved
- [x] Build: poetry build succeeds
- [x] Tests (2025-10-16): pytest --maxfail=1 --disable-warnings --cov=firecrawl_demo --cov-report=term-missing
- [x] Lint (2025-10-16): ruff check .
- [x] Format (2025-10-16): black --check . & isort --profile black --check-only .
- [x] Types (2025-10-16): mypy .
- [x] Security (2025-10-16): bandit -r firecrawl_demo
- [x] Build (2025-10-16): poetry build

## Links

- [x] Baseline test failure log — see docs/gap-analysis.md
- [x] Coverage trend — pytest coverage report captured in CI logs
- [x] Architecture docs — docs/architecture.md
- [x] Adapter registry documentation — docs/architecture.md#research-adapter-registry
- [x] Registry tests — tests/test_research_logic.py

## Risks/Notes
- [ ] Firecrawl SDK now feature-flagged; production rollout still blocked on credential management and ALLOW_NETWORK_RESEARCH policy.
- [ ] Secrets governance follow-up: validate AWS/Azure vault access in staging and document production rotation approvals.
- [x] Secrets rotation: Primary vault determined by `SECRETS_BACKEND` (AWS or Azure) with local overrides via chained `.env` provider; document rotation/override in ops runbook.
- [ ] Monitor pre-commit hook runtimes once CI enables them to avoid exceeding build minutes.
- [ ] Enforced pandas/requests type stubs—watch for downstream mypy regressions without `type: ignore` escapes.

- [ ] Optional Firecrawl integration pending real SDK availability; CLI/pipeline operate with research adapters for now.
- [ ] Align isort configuration (project vs CLI flags) to avoid manual --profile overrides.
- [ ] Capture adapter contribution guide (with examples) once regulator/press adapters land.
- [ ] Type stubs handled via `type: ignore`; consider adding official stubs to dependencies.
      Pre-commit tooling still absent; evaluate adding packaged entrypoint or doc instructions in future iteration.

- [ ] Architecture: Keep a classic crawl stack (frontier → fetch → parse → normalise → extract → store) but make the policy loop learning-based (bandits/RL for what to crawl next) and the knowledge loop graph-first (entities/relations landing in a streaming graph DB). ￼
- [ ]MCP first: Expose crawler controls and graph queries as MCP tools; surface pages, logs and datasets as MCP resources; include research/playbook prompts. Copilot Studio/Windows/Agents SDK speak MCP, so Copilot can plan → call → verify across your stack. ￼
- [ ]Real-time graphs: Use Kafka→Neo4j/Memgraph ingestion, then run online algorithms (PageRank, Louvain) and render with Cytoscape.js or GPU visual analytics for live relationship maps. ￼
- [ ]Hygiene: Respect RFC 9309 robots, do boilerplate removal, dedupe with SimHash/MinHash, and track provenance with W3C PROV-O. These raise precision and trust. ￼

⸻

1. System blueprint (MCP-first)

Crawl & learn

- [ ]Frontier & scheduler: Start with Scrapy/Frontera/StormCrawler/Nutch; they give you robust queueing, politeness and retries. Plug in your own scoring function. ￼
- [ ]Learning policy: Prioritise URLs with multi-armed bandits or RL to maximise harvest rate on a topic; this consistently beats static heuristics in focused crawling studies. ￼

Parse & normalise

- [ ]Boilerplate removal: Trafilatura/jusText or neural variants to isolate the main content before NLP. ￼
- [ ]Near-duplicate detection: SimHash/LSH to collapse repeats across mirrors/syndication. ￼

Extract & resolve

- [ ]Entities/relations: spaCy for fast NER; add a relation-extraction model (e.g., REBEL class) via Transformers. ￼
- [ ]Entity resolution: Use Splink to merge near-matches across sources (names, organisations, products). ￼

Index & graph

- [ ]Hybrid search: Keep both lexical (BM25) and vector (pgvector/OpenSearch/Elastic kNN) for recall + semantic pivots. ￼
- [ ]Streaming graph store: Stream facts to Neo4j (Kafka Connector) or Memgraph (Kafka/Redpanda/Pulsar) and compute online metrics (PageRank, Louvain, similarity) for “what matters now”. ￼
- [ ]Query standard: Aim toward GQL (ISO/IEC 39075) so you aren’t locked to a single vendor. ￼

Visualise

- [ ]Real-time graphs: Cytoscape.js for in-browser interactivity; consider GPU-accelerated Graphistry for large graphs and analyst workflows. ￼

⸻

2. “Next-gen intelligence” modules to add

- [ ]Self-critiquing research loops: Use Self-RAG or similar: retrieve → generate → critique → refine. Make this a callable stage so Copilot can request another pass with stricter filters. ￼
- [ ]Reason-act planning: Adopt a ReAct-style tool-use pattern for the agent controlling your crawler: think → call a tool (search/crawl/verify) → observe → refine. ￼
- [ ]Source triangulation & dissent tracking: Store each claim with ≥2 independent sources and a “disagrees_with” edge in the graph; score results by provenance density (count of independent confirmations). Ground this in W3C PROV-O entities/activities/agents. ￼
- [ ]Freshness policy: Frontier scoring boosts URLs/domains with recent change; combine sitemap/Last-Modified and discovered delta rates. (Integrates cleanly with bandits/RL.) ￼
- [ ]Compliance & safety: Enforce RFC 9309 robots, per-site rate limiting, and legal holdouts; maintain a denial/allow list at the frontier level. ￼
- [ ]Quality filters: Language detection → readability thresholds → boilerplate removal → dedupe → NER/RE. This reduces garbage-in for the LLM. ￼
- [ ]Streaming analytics: Run PageRank/centrality/community detection continuously to surface emerging hubs and clusters in the live graph. ￼
- [ ]Hybrid retrieval API: Expose BM25 + ANN side-by-side (OpenSearch/Elastic or Postgres+pgvector) for both crisp keyword and semantic hops. ￼

⸻

3. How Copilot best leverages the MCP server

Expose three MCP surfaces and let Copilot orchestrate them:

A) Tools (actions)

- [ ]crawl.plan(topic, constraints) → returns candidate seeds, scope, robots risks.
- [ ]crawl.enqueue(urls, priority) / crawl.pause(job_id) / crawl.status(job_id) for operational control.
- [ ]extract.entities(doc_id|url) and extract.relations(doc_id|url, schema) for targeted NLP passes.
- [ ]graph.query(query, lang="GQL|Cypher") and graph.subgraph(seed, radius, filters) for analysis.
- [ ]verify.triangulate(claim, k=2) to enforce multi-source confirmation before publishing.
  Copilot Studio and Windows agents discover tools/resources/prompts directly from MCP and can chain them inside conversations. ￼

B) Resources (read-only artefacts)

- [ ]resources://logs/crawl/<date>.jsonl, resources://snapshots/<hash>.html, resources://datasets/entities.parquet for transparent inspection and audit by the LLM. (Both Copilot Studio and OpenAI Agents SDK understand MCP resources.) ￼

C) Prompts (task playbooks)

- [ ]Ship reusable “research playbooks” that encode ReAct/Self-RAG steps (e.g., Scoping → Search → Sample → Critique → Triangulate → Summarise with citations). Copilot can select these prompts from your MCP server. ￼

Why MCP here? It standardises how Copilot calls your stack, and it’s natively supported across Copilot Studio and Windows—so one thin MCP server serves multiple agents. ￼

⸻

4. Real-time relationship graph: reference pipeline

- [ ]Ingest: Kafka topics pages, entities, relations.
- [ ]Store/compute: Neo4j (Kafka Connector) or Memgraph (Kafka/Redpanda/Pulsar) for streaming writes; run PageRank/Louvain on rolling windows. ￼
- [ ]Query: Support GQL (future-proof) and Cypher; expose via MCP graph.query. ￼
- [ ]Visualise: Cytoscape.js embedded in your app; optionally pipe large selections to Graphistry for GPU layouts. ￼

⸻

1. Governance, security, and audit (non-negotiables)

- [ ]Robots & terms: Implement RFC 9309 faithfully; log effective directives per fetch. ￼
- [ ]Identity & least privilege: MCP adoption on Windows introduces consent/allow-listing; pair that with ephemeral credentials and centralised identity to avoid the “identity fragmentation” class of failures. ￼
- [ ]Provenance: Emit PROV-O records for every extracted fact (entity, relation, claim), linking back to page hashes and timestamps. ￼

⸻

1. Metrics to keep you honest

- [ ]Harvest rate / topical precision (for the RL/bandits crawler). ￼
- [ ]Extraction F1 on NER/RE test sets; dedupe rate (SimHash collisions avoided). ￼
- [ ]Graph quality: coverage of key entities, modularity of discovered communities, stability of top-k central nodes. ￼
- [ ]Provenance density: average independent sources per claim (target ≥2).

⸻

1. Recommended first tranche (pragmatic)

- [ ]MCP server exposing crawl._, extract._, graph.\*, verify.triangulate, plus resources for logs/snapshots. ￼
- [ ]Scheduler (Frontera/StormCrawler) with bandit scoring; boilerplate (Trafilatura) and dedupe (SimHash). ￼
- [ ]NER/RE (spaCy + REBEL) feeding Kafka→Neo4j/Memgraph; surface Cytoscape.js dashboard. ￼
- [ ]Hybrid search (OpenSearch/pgvector) for retrieval-augmented analysis. ￼

## Actionable Tasks & Quality Gates

> Each task has: **ID · Description · Owner · Due · Dependencies · Quality Gates (acceptance criteria) · Evidence/Artefacts · Rollback/Remediation**. Treat all writes as _plan → commit_ with preconditions and audit. Owners and due dates are placeholders—update as you staff the work.

### Global Definition of Done (applies to all tasks)

- Unit/integration tests updated; CI green (lint, type, security, tests).
- Docs updated (MkDocs) including runbook and API reference.
- Observability added (metrics + alerts) if the task changes runtime behaviour.
- Rollback procedure documented and tested in pre‑prod.

---

### Core Guardrails & Write Safety

| ID    | Description                                                                                                                             | Owner    | Due | Dependencies | Quality Gates (acceptance criteria)                                                                                                     | Evidence/Artefacts                                               | Rollback/Remediation                                                           |
| ----- | --------------------------------------------------------------------------------------------------------------------------------------- | -------- | --- | ------------ | --------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| AT-01 | **Preconditioned PATCH API**: enforce `If-Match`/ETag (or version) on all writes; reject with 412 on mismatch; require idempotency key. | Platform | TBC | None         | 100% write endpoints require `If-Match`; golden tests prove 412 on stale version; retries do not double-apply; negative tests included. | API contract; pytest suite; demo capturing 412; OpenAPI updated. | Feature flag to disable writes; revert to previous API image.                  |
| AT-02 | **JSON Schema validation** (2020-12) for core resources.                                                                                | Platform | TBC | AT-01        | CI blocks on invalid schema; server rejects malformed payloads; contract tests cover all required fields and enums.                     | Schema files; contract tests; CI logs.                           | Rollback to prior schema set; toggle validation to warn-only in pre‑prod only. |
| AT-03 | **DB/Graph constraints**: uniqueness, existence, type on nodes/edges.                                                                   | Data     | TBC | AT-02        | Attempted dupes/invalid writes fail; constraint coverage ≥95% of entities/edges in core domain.                                         | Cypher/DDL migration scripts; failing negative tests.            | Revert migration; restore snapshot.                                            |
| AT-04 | **Event sourcing + snapshots**: append-only log for patches; scheduled snapshots.                                                       | Platform | TBC | AT-01, AT-02 | Patches emitted to Kafka; snapshot restore proven in pre‑prod; RPO ≤ 15 min, RTO ≤ 30 min.                                              | Kafka topics; restore runbook; snapshot artefacts.               | Restore from last good snapshot; replay patches.                               |
| AT-05 | **Schema Registry** compatibility `FULL` for change-managed topics.                                                                     | Platform | TBC | AT-04        | Incompatible producer rejected in tests; breaking change cannot ship.                                                                   | Registry config; failing producer test captured.                 | Temporarily relax to `BACKWARD` in pre‑prod only; never in prod.               |
| AT-06 | **Merkle drift detection** on critical tables/subgraphs.                                                                                | Platform | TBC | AT-04        | Baseline root computed hourly; injected divergence detected <10 min; alert fires.                                                       | Merkle job code; alert runbook; test report.                     | Auto-quarantine writer; replay from snapshot to convergence.                   |

---

### Crawler Hygiene & Content Quality

| ID    | Description                                                               | Owner   | Due | Dependencies | Quality Gates                                                                               | Evidence/Artefacts                              | Rollback/Remediation                                     |
| ----- | ------------------------------------------------------------------------- | ------- | --- | ------------ | ------------------------------------------------------------------------------------------- | ----------------------------------------------- | -------------------------------------------------------- |
| AT-07 | **RFC 9309 robots + politeness**: per-host queues, adaptive delay.        | Crawler | TBC | None         | Zero robots violations in test corpus; rate-limit respected; deny/allow lists configurable. | Compliance tests; logs; config examples.        | Pause domains via allow/deny lists; backoff multipliers. |
| AT-08 | **Trap detection** (calendars/facets/loops) + canonicalisation.           | Crawler | TBC | AT-07        | Coverage of common trap patterns; false-positive rate <2%; hop/param caps in place.         | Unit tests; crawler metrics dashboard.          | Disable trap rules by domain; manual seed pruning.       |
| AT-09 | **Boilerplate removal** (Trafilatura/jusText) & **dedupe** (SimHash/LSH). | Crawler | TBC | AT-07        | ≥90% boilerplate removed on sample set; dedupe precision ≥0.98, recall ≥0.9.                | Eval notebook; fixtures; thresholds documented. | Lower thresholds; revert to prior model.                 |

---

### Extraction, Resolution, and Graph

| ID    | Description                                                                              | Owner  | Due | Dependencies | Quality Gates                                                                              | Evidence/Artefacts              | Rollback/Remediation                                     |
| ----- | ---------------------------------------------------------------------------------------- | ------ | --- | ------------ | ------------------------------------------------------------------------------------------ | ------------------------------- | -------------------------------------------------------- |
| AT-10 | **NER/RE pipeline**: spaCy + REBEL (or equivalent).                                      | NLP    | TBC | AT-09        | Micro-F1 ≥ baseline on labelled set; throughput ≥ X docs/min; latency p95 ≤ Y ms per doc.  | Test set & report; model cards. | Switch to previous model; feature flag.                  |
| AT-11 | **Entity resolution** with Splink (or equivalent).                                       | NLP    | TBC | AT-10        | Precision ≥0.98, recall ≥0.9 on hold-out; manual QA queue for low-confidence merges.       | Eval report; QA workflow.       | Rollback last merge batch; tighten thresholds.           |
| AT-12 | **Kafka → Graph streaming** (Neo4j/Memgraph) with PageRank & Louvain on rolling windows. | Data   | TBC | AT-10        | End-to-end lag ≤ 60 s; algorithms recompute < 5 min for active window; metrics exposed.    | Connector configs; dashboards.  | Drain connector; replay from offset; revert algo params. |
| AT-13 | **Hybrid search** (BM25 + vector via OpenSearch/pgvector).                               | Search | TBC | AT-10        | Top‑k recall ≥ baseline on eval queries; p95 query latency ≤ 300 ms; fallbacks documented. | Query bench; dashboards.        | Route to lexical-only; disable ANN plugin.               |
| AT-14 | **Real-time visualisation**: Cytoscape.js dashboard; optional GPU path.                  | App    | TBC | AT-12        | Can render ≥50k node/edge subgraphs interactively; export to PNG/JSON; auth enforced.      | UI demo; perf logs.             | Disable large-subgraph mode; server-side sampling.       |

---

### Copilot × MCP Orchestration

| ID    | Description                                                                                                                   | Owner    | Due | Dependencies | Quality Gates                                                                                                  | Evidence/Artefacts                    | Rollback/Remediation                                           |
| ----- | ----------------------------------------------------------------------------------------------------------------------------- | -------- | --- | ------------ | -------------------------------------------------------------------------------------------------------------- | ------------------------------------- | -------------------------------------------------------------- |
| AT-15 | **MCP tools**: `crawl.plan/enqueue/pause/status`, `extract.entities/relations`, `graph.query/subgraph`, `verify.triangulate`. | Platform | TBC | AT-07..AT-14 | Tool schemas validated; permission scopes enforced; negative tests for over-broad arguments.                   | MCP manifest; tool tests.             | Remove offending tool from manifest; scope tokens.             |
| AT-16 | **Plan → Commit pattern** for writes with human‑readable diff.                                                                | Platform | TBC | AT-15        | Copilot must call `*.plan` before `*.commit`; commits require `If-Match`; diffs shown; audit logged.           | Conversation transcript; logs; tests. | Block `*.commit`; manual review path.                          |
| AT-17 | **OPA policy gate** (deny-by-default; field-level).                                                                           | Security | TBC | AT-15        | Rego policies cover sensitive fields; policy tests; change approval required; emergency break-glass procedure. | Policy repo; test outputs.            | Revert to last good policy bundle; break-glass token rotation. |
| AT-18 | **Provenance (PROV‑O)** for every fact/edge.                                                                                  | Data     | TBC | AT-12        | Each emitted fact links to sources + timestamps + tool run; provenance density ≥2 for publish.                 | PROV store; sample queries.           | Flag low-density items; quarantine publish.                    |
| AT-19 | **E2E Copilot scenario**: Plan crawl → enqueue → extract → triangulate → publish.                                             | Platform | TBC | AT-15..AT-18 | Fully automated happy path; failure path exercises policy/rollback; recorded demo.                             | Test plan; video; logs.               | Disable publish step; fall back to manual gating.              |

---

### Self‑healing, Observability, and Operations

| ID    | Description                                                                                         | Owner    | Due | Dependencies | Quality Gates                                                                                       | Evidence/Artefacts                       | Rollback/Remediation                              |
| ----- | --------------------------------------------------------------------------------------------------- | -------- | --- | ------------ | --------------------------------------------------------------------------------------------------- | ---------------------------------------- | ------------------------------------------------- |
| AT-20 | **Health probes** (liveness/readiness/startup) + SLOs.                                              | Platform | TBC | None         | Probes implemented across services; SLOs defined (availability, latency, error rate); alerts wired. | Helm/YAML; dashboards.                   | Scale out/in; restart pods; circuit breakers.     |
| AT-21 | **Canary edits + progressive delivery** (Argo Rollouts).                                            | Platform | TBC | AT-01        | 1–5% canary path; automatic rollback on SLO breach or constraint violations spike.                  | Rollouts config; simulated failure demo. | Pause rollout; revert image.                      |
| AT-22 | **Chaos experiments** (pre‑prod): downstream 500s/latency/data corruption.                          | Platform | TBC | AT-20, AT-21 | All experiments pass; remediation scripts validated; mean time to detect <2 min.                    | Chaos runbook; reports.                  | Disable faulty path; restore from snapshot.       |
| AT-23 | **Security & supply chain**: SBOM (CycloneDX) + SLSA attestations; signature verification in CI/CD. | Security | TBC | None         | SBOMs generated per build; provenance verified; unsigned artefacts blocked.                         | CI logs; SBOM files; policy.             | Allowlist hotfix with exec approval; rotate keys. |

---

### Operational Quality Gates (release blockers)

- Any failing chaos scenario.
- Schema compatibility break on managed topics.
- OPA policy bundle not loading or tests failing.
- MC P `plan→commit` tests failing or missing audit logs.
- Robots/politeness compliance failing on the test corpus.

> Update the checkboxes above to reference the relevant **AT-** IDs as you complete them (e.g., “MCP server … (AT‑15, AT‑16, AT‑19)”).
