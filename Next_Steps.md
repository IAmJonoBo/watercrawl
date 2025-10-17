# Next Steps

## Tasks

- [x] Baseline remediation plan — Owner: AI — Due: Complete
- [x] Develop enhanced enrichment architecture & pipeline hardening — Owner: AI — Due: Complete
- [x] Implement CLI + MCP bridge for task orchestration — Owner: AI — Due: Complete
- [x] Stand up MkDocs documentation portal — Owner: AI — Due: Complete
- [x] Integrate secrets manager for production credentials — Owner: AI — Due: Complete
- [x] Introduce research adapter registry with config-driven sequencing — Owner: AI — Due: 2025-10-16
- [x] Package exemplar regulator/press/ML adapters for registry adoption — Owner: Platform Team — Due: 2025-10-16
- [x] Introduce pluggable evidence sinks (CSV + streaming stub) — Owner: AI — Due: 2025-10-16
- [x] Add official secrets-manager dependencies (boto3, azure identity/key vault) to unblock AWS/Azure backends — Owner: Platform Team — Due: 2025-10-30
- [x] Enforce evidence-log remediation notes when <2 sources or no official URL are present — Owner: AI — Due: 2025-10-23
- [x] Ship a runnable sample dataset or adjust README quickstart instructions — Owner: Docs — Due: 2025-10-23
- [x] High-risk coverage uplift (analyst_ui.py, compliance.py, cli.py, presets.py, secrets.py) — Owner: QA — Due: 2025-10-30
- [ ] Phase 1 — Data contracts + evidence enforcement (AT-24, AT-29) — Owner: Data — Due: 2025-11-15
  - [x] Phase 1.1 — Great Expectations + dbt alignment and operationalisation (AT-24) — Owner: Data — Completed 2025-10-17
  - [x] Phase 1.2 — Pint + Hypothesis contract tests for spreadsheet ingest (AT-29) — Owner: Data — Due: 2025-11-15 (Pint enforcement + Hypothesis suite landed; CI telemetry/dashboard wiring pending follow-up)
- [ ] Phase 2 — Lineage, catalogue, and versioning rollout (AT-25, AT-26, AT-27) — Owner: Platform — Due: 2025-12-06
- [ ] Phase 3 — Graph semantics + drift observability (AT-28, AT-30) — Owner: Data/Platform — Due: 2026-01-10
- [ ] Phase 4 — LLM safety, evaluation, and MCP plan→commit gating (AT-31, AT-32, AT-33) — Owner: Platform/Security — Due: 2026-01-31
- [x] Import order remediation (tests/test_mcp.py, firecrawl_demo/secrets.py, firecrawl_demo/research/exemplars.py) — Owner: Platform — Due: 2025-10-23
- [x] Async pipeline entrypoints + Firecrawl adapter centralisation — Owner: Platform — Due: 2025-10-24
- [x] CI summary artefacts for dashboard ingestion — Owner: Platform — Due: 2025-10-24
- [x] Document dotenv-linter invocation in ops runbook — Owner: Docs — Due: 2025-10-16
- [x] Install quality gate + rollback instrumentation for crawler hallucinations — Owner: AI — Due: 2025-10-17
- [x] Codex DX integration — Owner: Platform — Due: 2025-10-17
  - [x] Promptfoo smoke tests aligned to pipeline quality gates — Owner: Platform — Due: 2025-10-17
  - [x] Extend Promptfoo coverage to evidence-log remediation narratives — Owner: Platform — Due: 2025-11-07 (evidence guidance assertions now live under `codex/evals/tests/evidence_log.yaml`).
- [x] Segment runtime packages into core/integrations/governance/interfaces — Owner: Architecture — Completed 2025-10-17
- [ ] Validate Poetry exclude list in release pipeline — Owner: Platform — Due: 2025-10-31

## Steps

- [x] Document current-state architecture and gaps
- [x] Design target-state modules (data ingestion, validation, enrichment, evidence logging)
- [x] Implement incremental code/test updates per module
- [x] Integrate QA gates (lint, type, security, tests) into workflow
- [x] Add registry module + builder integration with fallback safety
- [x] Extend research tests for ordering, deduplication, and feature-flag coverage
- [x] Document adapter authoring workflow in architecture guide
- [x] Backfill tests for CSV sink + MCP injection path
- [x] Scaffold infrastructure plan for crawler/observability/policy guardrails (AT-07, AT-15–AT-18)
- [x] Package exemplar regulator/press/ML adapters and add registry defaults (2025-10-16)
- [x] Baseline infrastructure plan snapshot + drift regression tests (2025-10-16)
- [x] Harden CLI progress telemetry and adapter failure tracking (2025-10-16)
- [x] Close the secrets manager dependency gap and re-run QA (2025-10-30)
- [x] Implement evidence shortfall messaging in pipeline + tests (2025-10-23)
- [x] Publish onboarding-ready sample dataset guidance (2025-10-23)
- [x] Document dotenv-linter invocation in operations guide (2025-10-16)
- [x] Backfill targeted coverage for analyst UI, compliance, CLI, presets, and secrets modules (2025-10-16)
- [x] Asynchronous pipeline entrypoint validated via new pytest suites (2025-10-24)
- [x] CI summary generator publishes Markdown + JSON artefacts for dashboards (2025-10-24)
- [x] Extend high-risk coverage edge cases for analyst UI, compliance, CLI, presets, and secrets modules (2025-10-17)
- [x] Wire quality gate metrics, rollback plan emission, and documentation updates (2025-10-17)
- [x] Enforce fresh evidence gating for high-risk updates and update docs (2025-10-18)
- [x] Phase 1.1 — Great Expectations + dbt suite covering validation + enrichment outputs (AT-24) — CLI now runs GE + dbt, analytics/ dbt project published, artefacts stored under data/contracts/, and evidence log entries capture suite metadata.
- [x] Regression coverage for persisted contract artefacts — JSON copies from Great Expectations + dbt runs verified via CLI integration test (2025-10-17)
- [x] Phase 1.2 — Embed Pint + Hypothesis contract tests for spreadsheet ingest (AT-29) — Pint-backed ingest normalization and Hypothesis contracts merged; surface suite telemetry in CLI/observability dashboards next.
- [x] Phase 1.2 hardening — Fix Excel dataset reader for XLSX inputs and extend regression tests for unsupported unit payloads (2025-10-17)
- [x] Harden compliance MX lookup fallback for offline/NoNameservers scenarios and verify async pipeline enrichments (2025-10-17)
- [x] Segment package boundaries and update docs/tests (2025-10-17)
- [x] Phase 2.1 — Emit OpenLineage + PROV-O metadata from pipeline runs (AT-25) — Pipeline now records OpenLineage, PROV-O, and DCAT artefacts via `LineageManager`; CLI surfaces artefact paths.
- [x] Phase 2.2 hardening — Versioning manager records fingerprinted manifests with reproduce commands (2025-10-17).
- [ ] Phase 2.2 — Migrate curated outputs to Delta Lake/Iceberg + wire DVC/lakeFS snapshots (AT-26, AT-27) — Lakehouse roadmap captured in docs/lineage-lakehouse.md; local manifests now expose fingerprints and environment metadata to unblock remote wiring.
- [ ] Phase 2.3 — Automate lakehouse snapshot versioning and reproduction (AT-26/27 follow-up) — Local Parquet-backed writer scaffolded; deterministic version manifests with reproduce commands landed; DVC/lakeFS integration pending.
- [x] Phase 3.1 — Finalise CSVW/R2RML mappings + regression tests for graph build (AT-28) — `graph_semantics` module emits CSVW metadata and R2RML templates with coverage.
- [x] Phase 3.2 — Instrument whylogs drift monitors + alert routing (AT-30) — Baseline drift monitor implemented in `drift.py`; alert integration next.
- [x] Phase 4.1 — Integrate Ragas scoring + release gating thresholds (AT-31) — Lexical RAG evaluator added with threshold gating support.
- [x] Phase 4.2 — Implement OWASP LLM Top-10 mitigations + MCP diff/commit controls (AT-32, AT-33) — Safety policy module enforces blocked domains, diff size, and RAG score gating; MCP wiring follow-up required.
- [x] Integrate Codex developer experience scaffold (2025-10-17)
- [x] Default research adapter sequence excludes Firecrawl until SDK rollout opt-in (2025-10-17)
- [x] Expand Promptfoo scenarios to cover evidence-log remediation guidance (2025-10-17)
- [ ] Phase 3.1 follow-up — Publish CSVW/R2RML documentation + integration examples (AT-28)
- [ ] Phase 3.2 follow-up — Wire drift alerts into observability dashboards (AT-30)
- [ ] Phase 4.1 follow-up — Calibrate RAG benchmarks against production corpora (AT-31)
- [ ] Phase 4.2 follow-up — Integrate MCP audit logging + OWASP control dashboards (AT-32, AT-33)

## Deliverables

- [x] Updated enrichment pipeline with validated + auto-enriched CSV/XLSX processing
- [x] CLI entrypoints for batch runs, validation, and reporting
- [x] Minimal MCP server contract for Copilot orchestration
- [x] MkDocs site with methodology, API, and operations docs
- [x] Registry-enabled research pipeline supporting Firecrawl+Null defaults and config overrides
- [x] Adapter authoring guidance in docs/architecture.md
- [x] Exemplar regulator/press/ML adapters packaged with deterministic dataset
- [x] Infrastructure plan drift snapshot + regression coverage
- [x] Codex developer experience bundle (Promptfoo smoke tests + MCP integration notes)
- [x] Optional Firecrawl integration deferred until SDK opt-in; registry default sequence updated (2025-10-17)
- [x] CODEOWNERS, PR template, and ADR baseline documenting package boundaries (2025-10-17)
- [ ] Great Expectations/dbt/Deequ suites published with CI integration (AT-24)
- [x] Lineage artefact bundle (OpenLineage + PROV + DCAT) persisted for every CLI enrichment run (AT-25)
- [x] Lakehouse snapshot scaffolding (local Parquet-backed writer with manifest metadata) available for curated outputs (AT-26/27 foundation)
- [x] Graph semantics helper package (CSVW/R2RML) with tests (AT-28)
- [x] Drift monitoring baseline (distribution comparison utilities + tests) (AT-30)
- [x] RAG evaluation report + safety gating primitives (AT-31/32)
- [ ] Lineage + provenance catalogue (OpenLineage, PROV-O, DCAT) live with reproducible run book (AT-25, AT-27)
- [ ] ACID data lake baseline (Delta Lake/Iceberg) + DVC/lakeFS automation scripts (AT-26, AT-27)
- [ ] CSVW/R2RML mapping package + graph validation report (AT-28)
- [ ] whylogs drift dashboards + alert runbook (AT-30)
- [ ] Ragas evaluation report + policy gating checklist (AT-31)
- [ ] LLM safety/plan→commit MCP policy pack + red-team evidence (AT-32, AT-33)

## Quality Gates

- [x] Tests: pytest with coverage >= existing baseline (TBD after remediation)
- [x] CI summary artefacts available for dashboards (coverage + JUnit exported each run)
- [x] Lint: Ruff/Black/Isort clean
- [x] Type: mypy clean with strict config (to be defined)
- [x] Security: bandit critical findings resolved
- [x] Build: poetry build succeeds
- [x] Tests (2025-10-16 17:00 UTC): pytest --maxfail=1 --disable-warnings --cov=firecrawl_demo --cov-report=term-missing (77% coverage; flagged analyst_ui/compliance/cli/presets/secrets as hotspots)
- [x] Lint (2025-10-16): ruff check .
- [x] Format (2025-10-16 17:24 UTC): black --check . & isort --profile black --check-only . — import order corrected and checks now pass.
- [x] Types (2025-10-16): mypy .
- [x] Security (2025-10-16): bandit -r firecrawl_demo
- [x] Build (2025-10-16): poetry build
- [x] Env lint (2025-10-16 17:11 UTC): dotenv-linter lint .env.example
- [x] Infrastructure drift (2025-10-16): pytest tests/test_infrastructure_planning.py::test_infrastructure_plan_matches_baseline_snapshot
- [x] Adapter failure monitoring (2025-10-16): pipeline metrics expose `adapter_failures`; CLI surfaces warnings
- [x] Quality gate enforcement (2025-10-17): `quality_rejections` metric >0 halts publish; rollback plan generated for every blocked row
- [x] Fresh evidence gating (2025-10-18): high-risk updates require ≥2 unique sources including fresh official corroboration; rejection notes call out missing fresh evidence.
- [x] Restore PipelineReport quality metadata models so CLI/MCP responses include quality issues + rollback plans post-regression (2025-10-16)
- [x] Data contracts enforced: Great Expectations + dbt build (tag:contracts) block publishes; Deequ pending (AT-24)
- [ ] Provenance completeness: 100% of publishable facts have OpenLineage + PROV-O/DCAT metadata (AT-25)
- [ ] ACID + versioning: curated tables written via Delta/Iceberg with reproducible DVC/lakeFS commits (AT-26, AT-27)
- [ ] Graph validation + drift monitoring: CSVW/R2RML checks + whylogs alerts wired (AT-28, AT-30)
- [ ] Evaluation + safety: Ragas thresholds + OWASP LLM Top-10 suite green before release (AT-31, AT-32)
- [ ] MCP plan→commit enforcement: diff/If-Match + schema/test gating observed in audit logs (AT-33)
- [x] Tests (2025-10-17 12:02 UTC): poetry run pytest --maxfail=1 --disable-warnings --cov=firecrawl_demo --cov-report=term-missing.
- [x] Lint (2025-10-17 12:04 UTC): poetry run ruff check .
- [x] Format (2025-10-17 12:04 UTC): poetry run black --check . & poetry run isort --profile black --check-only .
- [x] Types (2025-10-17 12:05 UTC): poetry run mypy .
- [x] Security (2025-10-17 12:05 UTC): poetry run bandit -r firecrawl_demo.
- [x] Pre-commit sweep (2025-10-17 12:07 UTC): poetry run pre-commit run --all-files.
- [x] Env lint (2025-10-17 12:08 UTC): poetry run dotenv-linter lint .env.example.
- [x] Build (2025-10-17 12:09 UTC): poetry build.
- [ ] Codex smoke tests (2025-11-07 target): promptfoo eval codex/evals/promptfooconfig.yaml executed before enabling agent sessions.
- [x] Lineage emission QA: pytest tests/test_lineage.py::test_lineage_manager_persists_artifacts ensures OpenLineage/PROV/DCAT artefacts are produced.
- [x] Lakehouse snapshot QA: pytest tests/test_lakehouse.py::test_local_lakehouse_writer_persists_snapshot validates manifest and Parquet output.
- [x] Version manifest QA (2025-10-17): pytest tests/test_versioning.py::test_versioning_manager_records_snapshot ensures fingerprints and reproduce commands are captured.
- [x] Graph semantics QA: pytest tests/test_graph_semantics.py::* covers CSVW metadata and R2RML mapping outputs.
- [x] Drift QA: pytest tests/test_drift.py::test_compare_to_baseline_flags_large_shift monitors threshold behaviour.
- [x] RAG + Safety QA: pytest tests/test_rag_evaluation.py::test_evaluate_responses_returns_threshold_gate and tests/test_safety.py::* enforce gating policies.

## Phase Plan (2025 Q4 → 2026 Q1)

| Phase                                       | Scope                                                                                                             | Dependencies                                                   | Exit Criteria                                                                                                   |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| **1. Data Contracts & Evidence Discipline** | Ship GX/dbt/Deequ suites, Pint unit enforcement, Hypothesis fuzzing, and evidence shortfall automation.           | Existing validation/enrichment modules; pandas/requests stubs. | CI fails on contract breach, evidence log auto-remediates, coverage ≥95% of curated tables.                     |
| **2. Lineage & Versioned Lakehouse**        | Emit OpenLineage/PROV-O/DCAT, adopt Delta/Iceberg, store DVC/lakeFS run commits, update docs/CLI outputs.         | Phase 1 gating; infrastructure plan.                           | Reproduce run from commit only; 100% lineage coverage; documented rollback paths.                               |
| **3. Graph Semantics & Observability**      | Finalise CSVW/R2RML, integrate graph build smoke tests, instrument whylogs drift dashboards + alerting.           | Phase 2 dataset guarantees.                                    | Graph validation thresholds pass; drift alerts tested in CI & staging; observability runbook published.         |
| **4. LLM Safety & MCP Governance**          | Integrate Ragas evaluation, OWASP LLM mitigations, MCP diff/commit with schema/test enforcement, update policies. | Phases 1–3 analytics & metadata.                               | Ragas scores above thresholds, red-team suite green, MCP audit logs show plan→commit gating and If-Match usage. |

> Maintain sequential sign-off: do not start a downstream phase until upstream exit criteria have been met and recorded in `Links`.

## Links

- [x] Baseline test failure log — see docs/gap-analysis.md
- [x] Coverage trend — pytest coverage report captured in CI logs
- [x] Architecture docs — docs/architecture.md
- [x] Adapter registry documentation — docs/architecture.md#research-adapter-registry
- [x] Registry tests — tests/test_research_logic.py
- [x] Infrastructure plan scaffolding — firecrawl_demo/infrastructure/planning.py
- [x] Exemplar adapter implementations — firecrawl_demo/research/exemplars.py
- [x] Infrastructure drift regression tests — tests/test_infrastructure_planning.py
- [x] GX/dbt/Deequ suites (Phase 1) — docs/data-quality.md (Phase 1.1 & 1.2 sections)
- [x] dbt contracts project — analytics/dbt_project.yml; analytics/models/staging/stg_curated_dataset.sql; analytics/tests/generic
- [x] Lineage + lakehouse configuration docs (Phase 2) — docs/lineage-lakehouse.md
- [x] Codex DX bundle — codex/README.md; codex/evals/promptfooconfig.yaml
- [x] Environment separation guidance — dev/README.md; dist/README.md; tools/README.md; app/README.md
- [ ] Graph semantics mapping repo + drift dashboards (Phase 3) — TBC
- [ ] LLM safety + MCP governance pack (Phase 4) — TBC

## Risks/Notes

- [ ] Firecrawl SDK now feature-flagged; production rollout still blocked on credential management and ALLOW_NETWORK_RESEARCH policy.
- [ ] Secrets governance follow-up: validate AWS/Azure vault access in staging and document production rotation approvals.
- [x] Secrets rotation: Primary vault determined by `SECRETS_BACKEND` (AWS or Azure) with local overrides via chained `.env` provider; document rotation/override in ops runbook.
- [ ] Monitor pre-commit hook runtimes once CI enables them to avoid exceeding build minutes.
- [ ] Enforced pandas/requests type stubs—watch for downstream mypy regressions without `type: ignore` escapes.
- [ ] Validate streaming evidence sink against real Kafka/REST endpoints once roadmap work begins; document throughput targets.
- [ ] Promptfoo smoke tests currently only cover pipeline/compliance happy paths; extend to evidence-log narratives after lineage instrumentation lands (AT-25/AT-27 dependency).
- [ ] Dist deployments must keep Codex disabled; add automated guard that blocks MCP/agent sessions unless `promptfoo eval codex/evals/promptfooconfig.yaml` has passed in the active branch.
- [ ] Communicate new `firecrawl_demo.core/*` module paths to downstream automation before deployment windows.
- [x] Secrets manager paths blocked until boto3 / Azure SDK packages are bundled with the project dependencies.
- [x] Evidence log remediation warnings now trigger for sparse or unofficial sourcing; schedule analyst refresher to interpret the new notes.
- [ ] Monitor fresh-evidence blocks for legitimate analyst updates; capture false-positive patterns for adapter tuning (2025-10-18).
- [x] Quickstart references `data/sample.csv` but the repo ships no sample input yet.

- [x] Optional Firecrawl integration pending real SDK availability; CLI/pipeline operate with research adapters for now. — Owner: Platform — Completed 2025-10-17 (default adapter sequence now omits Firecrawl until feature flag + SDK opt-in)
- [ ] Track Python <3.14 pin introduced for Great Expectations compatibility; review Great Expectations release notes weekly and schedule pin removal once 3.14 wheels land (2025-10-17 check blocked by SSL trust issues in build environment; retry when CA bundle updated).
- [ ] Communicate new Python >=3.11 floor across tooling/CI and verify downstream environments upgrade paths.
- [ ] Align isort configuration (project vs CLI flags) to avoid manual --profile overrides.
- [ ] Capture adapter contribution guide (with examples) once regulator/press adapters land.
- [ ] Type stubs handled via `type: ignore`; consider adding official stubs to dependencies.
      Pre-commit tooling still absent; evaluate adding packaged entrypoint or doc instructions in future iteration.
- [ ] Monitor new `sanity_issues` metric surfaced via CLI/MCP; triage non-zero counts before publishing datasets.
- [ ] Add regression tests for MCP summarize/list tasks returning empty results (tests/test_mcp.py).
- [x] Coverage hotspots: analyst_ui.py, compliance.py, cli.py, presets.py, and secrets.py below 60% test coverage — target uplift by 2025-10-30 (see Tasks). Coverage now ≥82% for each module after new unit suites landed (2025-10-16).
- [ ] Explore CI gating on the `sanity_issues` metric once monitoring data stabilises.
- [x] Import ordering drift flagged by `isort` (tests/test_mcp.py, firecrawl_demo/secrets.py, firecrawl_demo/research/exemplars.py) — remediation completed and checks green (2025-10-16).
- [ ] Monitor new MX lookup "unavailable" fallback so legitimate DNS misconfigurations are still surfaced once networked environments return.
- [x] `.env` hygiene tooling (`dotenv-linter`) requires explicit target files — invocation documented in docs/operations.md (2025-10-16); evaluate stub env templates separately.

- [ ] Architecture: Keep a classic crawl stack (frontier → fetch → parse → normalise → extract → store) but make the policy loop learning-based (bandits/RL for what to crawl next) and the knowledge loop graph-first (entities/relations landing in a streaming graph DB). ￼
- [ ] MCP first: Expose crawler controls and graph queries as MCP tools; surface pages, logs and datasets as MCP resources; include research/playbook prompts. Copilot Studio/Windows/Agents SDK speak MCP, so Copilot can plan → call → verify across your stack. ￼
- [x] Keep infrastructure plan aligned with deployed probe endpoints, OPA bundles, and automation workflows; add regression tests that fail when plan drift occurs. (2025-10-16)
- [ ] Refresh infrastructure baseline snapshot + docs whenever probe endpoints, policy bundles, or automation topics change in production.
- [ ] Real-time graphs: Use Kafka→Neo4j/Memgraph ingestion, then run online algorithms (PageRank, Louvain) and render with Cytoscape.js or GPU visual analytics for live relationship maps. ￼
- [ ] Hygiene: Respect RFC 9309 robots, do boilerplate removal, dedupe with SimHash/MinHash, and track provenance with W3C PROV-O. These raise precision and trust. ￼

⸻

1. System blueprint (MCP-first)

Crawl & learn

- [ ] Frontier & scheduler: Start with Scrapy/Frontera/StormCrawler/Nutch; they give you robust queueing, politeness and retries. Plug in your own scoring function. ￼
- [ ] Learning policy: Prioritise URLs with multi-armed bandits or RL to maximise harvest rate on a topic; this consistently beats static heuristics in focused crawling studies. ￼

Parse & normalise

- [ ] Boilerplate removal: Trafilatura/jusText or neural variants to isolate the main content before NLP. ￼
- [ ] Near-duplicate detection: SimHash/LSH to collapse repeats across mirrors/syndication. ￼

Extract & resolve

- [ ] Entities/relations: spaCy for fast NER; add a relation-extraction model (e.g., REBEL class) via Transformers. ￼
- [ ] Entity resolution: Use Splink to merge near-matches across sources (names, organisations, products). ￼

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

1. How Copilot best leverages the MCP server

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

---

## Frontier Enhancements — Data Trust, Graph Semantics, and Safety

> This section integrates best‑in‑class data quality, lineage, ACID/versioning, tabular→graph semantics, guard‑railed calculations, observability/evaluation, and LLM safety into the programme. It adds aims, process notes, and **new AT‑tasks** with explicit quality gates.

### Aims → outcomes (what “great” looks like)

- **Authoritative results:** every published fact shows run lineage, fact‑level provenance, passed quality checks, and a time‑travelable dataset version.
- **Intelligent tabular analysis:** spreadsheets/DBs are typed, constraint‑checked and unit‑aware; graphs mirror entities/relations from those tables in near‑real time.
- **Self‑healing:** failing inputs/outputs are quarantined automatically; lineage/profiles pinpoint faulty steps; rollbacks are routine.

### Principles & frameworks (to adopt)

1. **Data quality & contracts:** automatic checks with **Great Expectations / dbt tests / Deequ** gate all writes before compute/publish.
2. **Lineage, provenance, catalogue:** emit run‑level lineage (**OpenLineage**), fact‑level provenance (**W3C PROV‑O**), and dataset‑level metadata (**W3C DCAT**).
3. **ACID tables + versioning:** write curated data to **Delta Lake** or **Apache Iceberg**; version datasets with **DVC**/**lakeFS**.
4. **Tabular→graph by spec:** map spreadsheets/SQL using **CSVW** / **R2RML** (and **RML** for non‑SQL). Query/compute on **GQL‑ready** engines with PageRank/Louvain.
5. **Guard‑railed calculations:** route spreadsheet math through **DuckDB/SQLite** with `CHECK/NOT NULL/UNIQUE/PK`; add **units** checking (Pint) and **property‑based tests** (Hypothesis).
6. **Observability & eval:** profile data distributions continuously (**whylogs**); score LLM/RAG outputs (**Ragas**) to stop silent regressions.
7. **LLM safety:** apply **OWASP Top‑10 for LLMs** (injection, insecure output handling, excessive agency) to every agent/tool path.

### Actionable Tasks & Quality Gates (new)

|        ID | Description                                                                                                                                        | Owner    | Due | Dependencies | Quality Gates (acceptance criteria)                                                                                  | Evidence/Artefacts                                                        | Rollback/Remediation                                                                 |
| --------: | -------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | --- | ------------ | -------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| **AT-24** | **Data contracts & tests**: enforce Great Expectations / dbt tests / Deequ on every ingest/transform; block writes on failure.                     | Data     | TBC | AT-01..AT-06 | CI job fails if any test fails; coverage of schema/range/uniqueness/ref integrity ≥95% of curated tables.            | dbt `tests/` + GX suites + Deequ checks; CI logs; human‑readable GX docs. | Auto‑quarantine dataset; roll back to last good snapshot; hotfix test definitions.   |
| **AT-25** | **Lineage & catalogue**: emit OpenLineage events; attach PROV‑O to facts; publish DCAT entries for curated datasets.                               | Data     | TBC | AT-04        | 100% publishable runs have lineage events; each fact resolves to ≥1 PROV record; DCAT entries live and discoverable. | OpenLineage emitter configs; PROV store; DCAT catalogue pages.            | Pause publish for items lacking lineage/provenance; backfill events; republish.      |
| **AT-26** | **ACID table format**: adopt Delta Lake or Iceberg for curated tables (time travel + concurrent writers).                                          | Platform | TBC | AT-04, AT-05 | All curated writes land in ACID tables; time‑travel restore proven; concurrent write tests pass.                     | Table configs; restore demo; perf/lock tests.                             | Repoint writers to snapshot; revert table config; replay events.                     |
| **AT-27** | **Dataset versioning**: tag runs with DVC or lakeFS commit; store pointers in lineage/provenance.                                                  | Platform | TBC | AT-26        | Every run references an immutable data commit; `reproduce` rebuild succeeds from commit alone.                       | DVC/lakeFS commit IDs; reproduce log.                                     | Roll back to prior commit; promote hotfix branch.                                    |
| **AT-28** | **Tabular→graph mappings**: define CSVW metadata + R2RML/RML mappings; validate before graph build.                                                | Data     | TBC | AT-12        | Mapping validation passes; post‑build checks confirm node/edge counts + degree distributions in expected ranges.     | Mapping repo; validators; post‑build report.                              | Invalidate graph; fix mapping; rebuild from last good snapshot.                      |
| **AT-29** | **Guard‑railed calculations**: import spreadsheets into DuckDB/SQLite; enforce constraints; verify units with Pint; fuzz with Hypothesis.          | Platform | TBC | AT-02        | Transformations have schema/type checks + unit checks; ≥1 property‑based test per transformation.                    | DDL with constraints; Pint unit tests; Hypothesis tests.                  | Disable failing transform; revert to stable version; correct units/constraints.      |
| **AT-30** | **Data profiling**: instrument whylogs for each dataset/partition; drift alerts wired.                                                             | Platform | TBC | AT-20        | Baselines captured; drift/missingness thresholds defined; alert fires on simulated drift.                            | Profiles; alert runbook; dashboards.                                      | Quarantine partition; roll back to last good version; widen thresholds if justified. |
| **AT-31** | **RAG/agent evaluation**: integrate Ragas; enforce minimum scores (faithfulness/context precision).                                                | Platform | TBC | AT-15..AT-19 | Below‑threshold scores block “authoritative” promotion; evaluation trace stored.                                     | Ragas reports; CI gate.                                                   | Re‑run with improved retrieval/context; hold publish.                                |
| **AT-32** | **LLM safety**: implement OWASP LLM Top‑10 mitigations; red‑team tests for injection, insecure output handling, excessive agency.                  | Security | TBC | AT-15..AT-17 | Red‑team suite passes; tool allow‑list and typed arg validation enforced; no direct write tools without plan→commit. | Test suite; OPA policies; audit logs.                                     | Disable risky tools; tighten policies; rotate secrets.                               |
| **AT-33** | **Copilot MCP × data gates**: expose `table.plan_patch`/`table.commit_patch` tools; require `If‑Match` + schema + (dbt/GX/Deequ) checks in‑flight. | Platform | TBC | AT-24..AT-32 | Copilot shows diff; commits only when all tests/constraints pass; audit links lineage/provenance.                    | MCP manifest; conversation transcript; logs.                              | Block `commit_patch`; manual review path; revert via time travel.                    |

### Additional release blockers (additive)

- Any failing **GX/dbt/Deequ** test on publishable datasets (AT‑24).
- Missing **OpenLineage** events or **PROV‑O/DCAT** for a publishable run (AT‑25).
- Curated writes to **non‑ACID** tables or runs without a **DVC/lakeFS** commit (AT‑26, AT‑27).
- **CSVW/R2RML/RML** validation failure or graph post‑build checks out of bounds (AT‑28).
- **whylogs** drift beyond thresholds or missing profiles for a promoted partition (AT‑30).
- **Ragas** scores below thresholds for publish (AT‑31).
- **OWASP LLM Top‑10** red‑team failure (AT‑32).


## Links

- [x] Operations runbook updated with Great Expectations contract execution guidance — Owner: Docs — Link: [docs/operations.md](docs/operations.md)

## Risks/Notes

- [ ] Running Great Expectations locally regenerates `great_expectations/uncommitted/config_variables.yml`; keep it ignored in VCS and document environment-specific overrides per analyst run.
- [ ] Confirm repository-root anchored paths in `firecrawl_demo.core.config` propagate cleanly to packaging workflows; update release docs if downstream tooling expected package-root locations. (2025-10-17)

## Baseline QA Snapshot — 2025-10-16

- ✅ `poetry run pytest --maxfail=1 --disable-warnings --cov=firecrawl_demo --cov-report=term-missing`
- ✅ `poetry run ruff check .`
- ✅ `poetry run black --check .`
- ❌ `poetry run isort --profile black --check-only .` (import order drift in tests/test_mcp.py, firecrawl_demo/secrets.py, firecrawl_demo/research/exemplars.py)
- ✅ `poetry run mypy .`
- ✅ `poetry run bandit -r firecrawl_demo`
- ⚠️ `poetry run dotenv-linter` (requires explicit target file; no `.env` committed)
- ✅ `poetry run pre-commit run --all-files`
- ✅ `poetry run poetry build`

## Baseline QA Snapshot — 2025-10-17

- ✅ `poetry run pytest --maxfail=1 --disable-warnings --cov=firecrawl_demo --cov-report=term-missing`
- ✅ `poetry run ruff check .`
- ✅ `poetry run black --check .`
- ✅ `poetry run mypy .`
- ✅ `poetry run bandit -r firecrawl_demo`
- ✅ `poetry run pre-commit run --all-files`
- ✅ `poetry build`
- ✅ `poetry run dbt build --project-dir analytics --profiles-dir analytics --target ci --select tag:contracts --vars '{"curated_source_path": "data/sample.csv"}'`
