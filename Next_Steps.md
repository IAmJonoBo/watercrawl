# Next Steps

## Tasks

- [x] Baseline remediation plan — Owner: AI — Due: Complete
- [x] Develop enhanced enrichment architecture & pipeline hardening — Owner: AI — Due: Complete
- [x] Implement CLI + MCP bridge for task orchestration — Owner: AI — Due: Complete
- [x] Stand up MkDocs documentation portal — Owner: AI — Due: Complete

## Steps

- [x] Document current-state architecture and gaps
- [x] Design target-state modules (data ingestion, validation, enrichment, evidence logging)
- [x] Implement incremental code/test updates per module
- [x] Integrate QA gates (lint, type, security, tests) into workflow

## Deliverables

- [x] Updated enrichment pipeline with validated + auto-enriched CSV/XLSX processing
- [x] CLI entrypoints for batch runs, validation, and reporting
- [x] Minimal MCP server contract for Copilot orchestration
- [x] MkDocs site with methodology, API, and operations docs

## Quality Gates

- [x] Tests: pytest with coverage >= existing baseline (TBD after remediation)
- [x] Lint: Ruff/Black/Isort clean
- [x] Type: mypy clean with strict config (to be defined)
- [x] Security: bandit critical findings resolved
- [x] Build: poetry build succeeds

## Links

- [x] Baseline test failure log — see docs/gap-analysis.md
- [x] Coverage trend — pytest coverage report captured in CI logs
- [x] Architecture docs — docs/architecture.md

## Risks/Notes

- [ ] Optional Firecrawl integration pending real SDK availability; CLI/pipeline operate with research adapters for now.
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
