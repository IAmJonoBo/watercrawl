1. Introduce `firecrawl_demo/domain/contracts.py` with `pydantic.BaseModel` (or `dataclasses_json`) equivalents for `SchoolRecord`, `EvidenceRecord`, `QualityIssue`, and `PipelineReport`, exposing `.model_dump()` plus JSON Schema/Avro exporters.
2. Add adapter functions in `firecrawl_demo/domain/models.py` to convert between legacy dataclasses and the new contract models so existing callers keep working during the migration.
3. Update orchestration touchpoints (`firecrawl_demo/application/interfaces.py`, `firecrawl_demo/application/pipeline.py`, `firecrawl_demo/integrations/integration_plugins.py`) to emit/accept contract instances and embed a semantic version + schema URI in CLI/MCP responses.
4. Wire contract validation into evidence sinks and plan→commit artefact generation under `apps/analyst/cli.py` / `firecrawl_demo/interfaces`, then document the contract registry in `docs/architecture.md` and `docs/operations.md`.
5. Add regression tests that snapshot the generated JSON Schemas and enforce backward compatibility in `tests/test_contracts.py` (or a new `tests/test_contract_schemas.py`).

6. Refactor `Pipeline.run_dataframe_async` to stage row lookups into an `asyncio.TaskGroup` (or `gather` with a bounded `Semaphore`) so batches of organisations are enriched concurrently while respecting a configurable concurrency limit.
7. Share adapter clients and HTTP sessions by instantiating them once per run and passing through a context object; reuse the global cache in `firecrawl_demo/core/cache.py` to memoise `(normalised_name, province)` lookups with TTL derived from profile settings.
8. Ensure synchronous adapters are wrapped with `asyncio.to_thread` only once, and thread-pool usage is pooled instead of spawning per call; expose metrics for cache hit rate and queue latency through existing Prometheus hooks.
9. Add failure-handling policies (circuit breaker or exponential backoff) so a flakey adapter does not stall the entire run; surface rejection statistics in `metrics`.
10. Extend `tests/test_research_logic.py` and `tests/test_pipeline.py` with concurrency-focused tests plus new stress-style SIT cases that verify throughput improvement and deterministic ordering when concurrency is 1.

11. Extract the row-processing logic (normalisation, sanity checks, quality gate evaluation) from `Pipeline.run_dataframe_async` into a dedicated module (e.g., `firecrawl_demo/application/row_processing.py`) that returns a `SchoolRecord` + side effects without touching the DataFrame.
12. Replace `.iterrows()` with `itertuples()` or build a list of update instructions that can be applied in a vectorised pass, ensuring dtype stability and avoiding repeated `.astype("object")` conversions.
13. Move change-description helpers into reusable utilities so string diffing happens once per row and is easy to unit test; expose deterministic ordering for rollback actions.
14. Update `tests/test_pipeline.py` and `tests/test_e2e_pipeline.py` to cover the new row-processing service, adding fixtures for bulk updates and verifying no implicit dtype changes.
15. Refresh developer guidance in `docs/architecture.md` to mandate using the new transformation service for future enrichment steps.

16. Create a `tests/system/` suite that drives the analyst CLI against the sample dataset, asserts evidence sink writes, and inspects telemetry outputs (Prometheus, whylogs) using the new contract models.
17. Add contract-consumer tests ensuring MCP responses, evidence logs, and plan→commit artefacts validate against the published schemas; integrate these into the CI workflow as blocking jobs.
18. Introduce performance smoke tests (e.g., pytest markers that record wall-clock throughput) with thresholds enforced via CI gating to guard the new concurrency work.
19. Update `.github/workflows/ci.yml`, `docs/operations.md`, and `Next_Steps.md` with the new SIT/contract gate descriptions, and surface coverage deltas in the CI summary.
20. Publish runbooks for regenerating fixtures and diagnosing gate failures in `docs/qa.md`.
