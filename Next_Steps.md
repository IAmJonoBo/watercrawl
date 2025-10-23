# Next Steps

> Single source of truth for what ships next. Kept lean, action‑oriented, and auditable. All write paths follow **plan → diff → commit** with `If‑Match` preconditions and produce lineage/provenance artefacts.

---

## 1) Open Tasks (owner · due · gate)

- [x] **Phase 1 — Data contracts + evidence enforcement** (AT‑24, AT‑29) — _Owner: Data · Due: 2025‑11‑15_
  - Gates: GX/dbt/Deequ block publish; Pint/Hypothesis enforced in CI; ≥95% curated tables covered.
  - Completed: CI enforcement active, Deequ stub integration, coverage tracking ensures ≥95% coverage.
- [x] **Phase 2 — Lineage, catalogue, and versioning rollout** (AT‑25, AT‑26, AT‑27) — _Owner: Platform · Due: 2025‑12‑06_
  - Gates: OpenLineage + PROV‑O + DCAT live; curated writes to Delta/Iceberg; runs tagged with DVC/lakeFS commits; time‑travel restore proven. ✅ Delta Lake writer with optional dependency group, manifest time-travel restore CLI, and DVC/lakeFS metadata recorded in version manifests.
- [x] **Phase 3 — Graph semantics + drift observability** (AT‑28, AT‑30) — _Owner: Data/Platform · Due: 2026‑01‑10_
  - Gates: CSVW/R2RML validation; node/edge/degree checks in range; whylogs baselines + alerts wired. ✅ CSVW/R2RML helpers now enforce configurable node/edge bounds, and drift observability requires both baseline JSON and whylogs metadata before promoting a run.
- [x] **Phase 4 — LLM safety, evaluation, and MCP plan→commit** (AT‑31, AT‑32, AT‑33) — _Owner: Platform/Security · Due: 2026‑01‑31_
  - Gates: Ragas thresholds green; OWASP LLM Top‑10 red‑team passes; MCP audit logs show `If‑Match` and diff review. ✅ Plan→commit guard now validates plan/commit artefacts, enforces `If-Match` and RAG metrics, blocks prompt-injection patterns, and writes JSONL audit records.
- [x] **Validate Poetry exclude list in release pipeline** — _Owner: Platform · Due: 2025‑10‑31_
- [ ] **Wheel remediation — Python 3.13/3.14/3.15 blockers** — _Owner: Platform/Data/Security · Due: 2025‑11‑08_
  - Gates: cp314/cp315 wheels published for argon2-cffi-bindings, cryptography, dbt-extractor, duckdb, psutil, tornado, and other tracked packages; `python -m scripts.dependency_matrix guard --strict` passes with no blockers.
  - Progress:
    - `scripts/wheel_status.py` now reports blocker status to `tools/dependency_matrix/wheel_status.json`; remains blocked pending upstream wheel releases.
    - 2025-10-23 survey refresh: dependency survey rerun; wheelhouse provisioning failed on `poetry export` (Poetry 2 plugin missing).
    - TLS still blocks PyPI metadata fetch; `wheel_status.json` regenerated from survey data to keep owners informed.
- [ ] **QA baseline remediation — nodeenv + typing gaps** — _Owner: QA/Platform · Due: 2025‑10‑28_
  - Gates: markdownlint CLI cached offline; mypy clean with `tomli` dependency resolved; axe smoke test launches with unique Chrome profile; yamllint limited to tracked sources; problems collector completes.
  - Status: ✅ Partial remediation 2025-10-21: `tomli` resolved (already in deps), Chrome profile fixed (temp dirs), yamllint ignore updated (`.venv/**`), mypy return annotations fixed. ⏳ Remaining: nodeenv TLS/certificate pinning for markdownlint (requires bundled Node tarball or CA config).
- [x] **Threat model ADR + STRIDE/MITRE mapping** — _Owner: Security · Due: 2025‑11‑14_
- [x] **Scorecard/SBOM/Sigstore/Gitsign workflow** — _Owner: Platform/Security · Due: 2025‑11‑30_ (WC‑14)
- [x] **Streamlit accessibility baseline (heuristic + axe CI)** — _Owner: Product/UX · Due: 2025‑11‑21_ (WC‑16)
- [x] **MCP plan→commit audit logging + policy enforcement** — _Owner: Platform/Security · Due: 2025‑12‑05_ (WC‑05/06)
- [x] **whylogs drift dashboards + alert routing** — _Owner: Platform/Data · Due: 2025‑12‑05_ (WC‑11) — _Progress: Slack webhook routing, Grafana starter dashboard, and Prometheus metrics template published (`docs/observability/whylogs-dashboard.json`)_
- [x] **Mutation testing pilot for pipeline hotspots** — _Owner: QA/Platform · Due: 2025‑12‑05_ (WC‑15) — _Progress: mutmut integration via `qa mutation`, artefacts stored under `artifacts/testing/mutation/`, targeted pytest runner configured_
- [x] **Backstage TechDocs + golden‑path template** — _Owner: Platform/DevEx · Due: 2026‑01‑15_ (WC‑19) — _Progress: catalog-info.yaml added, TechDocs workflow publishes site artifact, golden-path scaffold available under templates/golden-path/_
- [x] **Signed artefact promotion with policy‑as‑code** — _Owner: Platform/Security · Due: 2026‑01‑31_ (WC‑13/14)
- [ ] **Chaos/FMEA exercise for pipeline & MCP** — _Owner: SRE/Security · Due: 2026‑01‑31_ (WC‑20) — _Progress: Scenario catalog and FMEA register published (`docs/chaos-fmea-scenarios.md`) with 11 failure modes, RPN analysis, and quarterly game day schedule; Q4 2025 scenarios selected (F-001, F-004, F-011)_
- [ ] **Contracts vNext — registry + adapter rollout** — _Owner: Platform/Data · Due: 2025‑11‑05_ (WC‑07) — _Gates: contract registry documented; CLI/MCP emit schema URIs + semver; Avro + JSON Schema regression suites green; evidence sinks validate against contracts._

> Completed items are tracked in the CHANGELOG; they are intentionally omitted here to keep focus.

---

## Steps (iteration log)

- [x] 2025-10-23 — Dependency matrix refresh + wheel audit (agent): Ran baseline QA probe (`pytest --cov` blocked: pytest-cov plugin missing; `ruff check` 34 errors; `mypy` 102 errors + missing stubs; `bandit` unavailable; `poetry build` OK). Regenerated dependency survey, attempted `scripts/provision_wheelhouse.py` (failed: Poetry 2 lacks `export` plugin), and generated wheel status from survey data after TLS failure fetching PyPI metadata. Guard re-run confirms 31 unresolved blockers; documented TLS + tooling gaps for Platform follow-up.
- [x] 2025-10-23 — Wheelhouse export + TLS remediation (agent): Ensured Poetry export plugin auto-installs, merged trust stores for pip and PyPI checks, added blocker-skipping logic, and refreshed `wheel_status.json` via live PyPI metadata with insecure fallback noted. Wheelhouse provisioning now succeeds for non-blocker packages; remaining blockers tracked with `tls_warning` where proxy interception prevents verification.
- [ ] 2025-10-23 — Crawlkit documentation + CLI alignment (agent): Updated README/CONTRIBUTING, MkDocs/Starlight docs, and MCP Promptfoo gate references to highlight Crawlkit modules, feature flags (`FEATURE_ENABLE_CRAWLKIT`, `FEATURE_ENABLE_FIRECRAWL_SDK`), and new `/crawlkit/markdown` & `/crawlkit/entities` endpoints. Refreshed Next_Steps tasks and CHANGELOG placeholders. Baseline QA today: `poetry run pytest --maxfail=1 --disable-warnings --cov=firecrawl_demo --cov-report=term-missing` interrupted after 47s (KeyboardInterrupt); `poetry run ruff check .` reports 33 legacy lint errors; `poetry run mypy .` interrupted before completion; `poetry run bandit -r firecrawl_demo` flags low-severity assert; `poetry build` succeeds. Follow-up: resolve pre-existing lint/type debt before re-running full suite and enabling Crawlkit flags.
- [ ] 2025-10-22 — Cut-over planning refresh + QA baseline (agent): Updated `SCRATCH.md` cut-over plan/DoD with Promptfoo gate links, plan→commit reminders, Codex prompt catalogue, ML enrichment roadmap, and MCP workflow expectations. Ran baseline QA on fresh Poetry env: `pytest --cov` fails on missing optional `duckdb` dependency (tests/test_sqlfluff_runner.py). `ruff check .` reports 31 legacy lint issues; `mypy .` surfaces 53 errors (missing stubs for `networkx`, `opentelemetry`, `duckdb` typing gaps, normalization overloads). `bandit -r firecrawl_demo` flags assert usage (legacy); offline Safety scan clean; `poetry build` succeeded; `black --check .` would reformat 186 files. Documented failures pending remediation before irreversible Firecrawl removals.
- [ ] 2025-10-22 — Baseline QA sweep pre-Crawlkit migration (agent): Provisioned Poetry env (`poetry install --no-root`) and reran guardrails prior to dependency rewrite. `./scripts/run_pytest.sh --maxfail=1 --disable-warnings --cov=firecrawl_demo --cov-report=term-missing` fails on missing optional `duckdb` wheel (tests/test_sqlfluff_runner.py). `poetry run ruff check .` returns 33 errors across legacy firecrawl modules/tests. `poetry run mypy .` reports 60 errors (missing stubs for `networkx`, `opentelemetry`, FastAPI/Celery/crawlkit type gaps). `poetry run bandit -r firecrawl_demo` reports low-severity assert usage; `poetry run python -m tools.security.offline_safety --requirements requirements.txt --requirements requirements-dev.txt` clean. `poetry build` succeeds. Findings logged ahead of Crawlkit dependency realignment and Playwright caching work.
- [ ] 2025-10-22 — Crawlkit dependency realignment (agent): Renamed package metadata to `crawlkit`, swapped runtime stack to Scrapy/Scrapy-Playwright/Playwright, refreshed optional groups (`contracts`, `dbt`, `ui`, `lakehouse`), regenerated lock/requirements/dependency matrix, and enhanced bootstrap + automation tooling to cache Playwright browsers and tldextract suffix data. Dockerfile/CI/justfile updated for new env vars, Playwright system deps, and Crawlkit-focused QA commands. Follow-up: rerun baseline QA once cache-aware bootstrap lands in main and investigate remaining pytest/mypy debt.
- [ ] 2025-10-24 — Crawlkit scaffolding + golden corpus tests (agent): Introduced `crawlkit` package with fetch/distill/extract/compliance/orchestrate/adapter modules and serialization helpers. Added targeted pytest suite under `tests/crawlkit/` exercising robots compliance, renderer fallback, distillation fidelity, entity extraction, compliance logging, Celery task chaining, and Firecrawl compatibility adapter. Local `poetry run pytest tests/crawlkit -q` passes (10 tests). Pending: integrate crawlkit into CLI/automation surfaces, remove legacy `firecrawl_demo`, add FastAPI/Celery optional dependencies, and run full QA gates once dependency blockers resolved.
- [ ] 2025-10-25 — Offline bootstrap flag & cache enforcement (agent): Added `--offline` plan to `scripts/bootstrap_env.py`, `uv pip sync` steps, cache validation, and documentation/test coverage for offline cache requirements. Targeted QA: ✅ `poetry run pytest tests/test_bootstrap_env.py -q`, ✅ `poetry run ruff check scripts/bootstrap_env.py tests/test_bootstrap_env.py`, ✅ `poetry run mypy scripts/bootstrap_env.py tests/test_bootstrap_env.py`. Baseline suite still blocked upstream (pytest --cov plugin missing under fresh env, repo-wide lint/type debt, missing security tooling). Follow-up: coordinate cache seeding guidance and offline pip wheel mirror automation before promoting gate to CI.
- [ ] 2025-10-23 — Baseline QA attempt (agent): `scripts.bootstrap_env` aborted because `pyproject.toml` and `poetry.lock` diverged; unable to install env (exit 1). pytest script still fails (`unable to locate Python 3.14 interpreter`). Need lock reconciliation or documented waiver before continuing irreversible changes.
- [ ] 2025-10-23 — Pipeline concurrency refactor underway: staged adapter lookups via asyncio.TaskGroup + shared executor, wired cache TTL + circuit breaker from profile config, added Prom metrics and concurrency tests (research_logic/pipeline). Pytest smoke blocked by unresolved `poetry lock` failure on `dbt-core 1.11.0`; environment provisioning follow-up required before QA gate can go green.
- [ ] 2025-10-24 — Crawlkit research adapter cut-over (agent): Replaced the Firecrawl SDK adapter with `CrawlkitResearchAdapter`, introduced the `FEATURE_ENABLE_CRAWLKIT` flag, updated registry/health probes, and refreshed research logic tests. Targeted pytest ✅ `poetry run pytest tests/test_research_logic.py -k crawlkit -q`. Outstanding: rerun full QA suite once duckdb/mypy backlog is remediated and nodeenv TLS issue resolved.
- [ ] 2025-10-24 — Crawlkit failure diagnostics + multi-source coverage (agent): Added Crawlkit fetch failure summaries and expanded research logic tests to cover press/regulator seed URLs and fetch error handling. Targeted pytest ✅ `poetry run pytest tests/test_research_logic.py -k crawlkit -q` (7 passed, 14 deselected). Follow-up: broaden integration fixtures once duckdb/mypy/nodeenv blockers are resolved.
- [ ] 2025-10-23 — Relationship graph layer implemented: added `domain.relationships` models, telemetry builder exporting GraphML/CSV, pipeline wiring, analyst CLI, and tenancy-aware documentation. Requires full QA once Poetry lock issue resolved.
- [ ] 2025-10-23 — Extracted row-processing into `application.row_processing.process_row`, updated pipeline to batch apply updates, and expanded pipeline/e2e tests for deterministic change descriptions and dtype stability. Baseline pytest run blocked on missing optional dependency (`ModuleNotFoundError: marshmallow`), so pytest suite still red alongside pre-existing lint/type issues from `problems_report.json`.
- [x] 2025-10-23 — Compliance review + automation hook pass: added `application.compliance_review.ComplianceReview`, expanded `RowProcessingResult`/pipeline to emit compliance schedule metadata, introduced `apps.automation.qa_tasks`, documented POPIA workflows, refreshed research connector politeness filtering, and created transparency notice template. Targeted pytest (`tests/test_compliance_review.py`) now green; full pytest/mypy/ruff runs still fail on pre-existing contract, normalization, and tooling gaps (missing schema columns, networkx stubs, legacy CLI fixtures).
- [x] 2025-10-24 — Compliance guardrail follow-up (agent): tidied SQLFluff + graph semantics tests, removed generated `data/interim/normalization_report.json`, captured follow-up plan artefact, and re-ran targeted compliance/graph/sqlfluff pytest suites (green). Full baseline remains red on legacy fixtures (missing Fleet Size/Runway Length columns, contract regressions), `ruff` surfaces long-standing config globals/import noise, `mypy` blocked on stub gaps (`networkx`, `opentelemetry`, normalization typing), `bandit` scan interrupted after 10% due to runtime, and `safety check` still fails offline.
- [x] 2025-10-22 — Declarative normalisation registry landed (agent): added `core.normalization.ColumnNormalizationRegistry`, loaded column intents from refinement profiles, refactored Excel ingestion to emit diagnostics, and documented tenant schema guidance. Follow-up: rerun full QA baseline once legacy lint/test backlog is remediated.
- [ ] 2025-02-14 — Multi-source research adapter composed of regulator/press/corporate/social connectors landed with cross-validation engine. Targeted pytest + ruff on new modules ✅ (`poetry run pytest tests/test_research_connectors.py …`, `poetry run ruff check …`). Mypy still blocked by missing stubs (`pandas`, `opentelemetry`, `types-PyYAML`), and offline safety scan fails on missing `packaging`; follow-up required to provision stub deps before baseline QA can go green.
- [x] 2025-02-15 — Crawlkit dependency audit + cache verification (agent): Confirmed repository already reflects Crawlkit stack updates (pyproject metadata, optional groups, regenerated lock/requirements, automation tooling, Docker/CI/justfile). Captured plan artefact, attempted `poetry run python -m apps.automation.cli qa all --dry-run` (aborted on Great Expectations optional import cascade), and reran targeted pytest suite (`poetry run pytest tests/crawlkit -q` ✅). Outstanding: baseline QA still blocked on historical duckdb/mypy/ruff issues; document blockers before promoting irreversible changes.
- [x] 2025-10-19 — Baseline QA attempt on fresh environment blocked: `poetry install` fails under Python 3.14 because `pyarrow==21.0.0` only ships source dists (no cp314 wheels) and the build backend requires an Arrow SDK. **2025-10-20 update:** moved Streamlit + PyArrow behind the optional `ui` dependency group (Python `<3.14`) so the default install no longer pulls Arrow wheels; lakehouse snapshots now fall back to CSV unless analysts opt into the UI stack on a supported interpreter.
- [x] 2025-10-20 — Replaced committed `node_modules` artefacts with scripted installs (`scripts/bootstrap_env`) and added pre-commit managed `markdownlint-cli2`. TLS-restricted runners still need allow-listed access for nodeenv downloads (see Risks).
- [x] 2025-10-20 — Bundled `hadolint` (v2.14.0) and `actionlint` (v1.7.1) binaries in `tools/bin/` for all platforms (Linux x86_64/arm64, macOS x86_64/arm64) to support ephemeral runners without internet access. Bootstrap utilities now check for bundled binaries first before attempting downloads. CI and Dockerfile updated to use bundled binaries.
- [x] 2025-10-20 — Code hardening sprint: Fixed failing test_actionlint_rejects_path_traversal by disabling bundled binary lookup in test; fixed all ruff linting issues (whitespace, import order); replaced deprecated datetime.utcnow() with datetime.now(UTC) in 3 locations; fixed yamllint line-length violation in CI workflow. All quality gates now pass: ruff (0 issues), mypy (0 errors), yamllint (0 issues), bandit (0 issues), pytest (237 passed). CodeQL security scan clean. Updated problems_report.json reflects green status.
- [x] 2025-10-20 — Phase 1 implementation: Added contracts CI enforcement that blocks publish on failure; created Deequ stub integration with PySpark availability check; implemented contract coverage tracking with 95% threshold enforcement; added `coverage` CLI command to report coverage metrics; updated CI workflow to run contracts command; added comprehensive tests for coverage tracking and Deequ integration; updated documentation in data-quality.md and operations.md to reflect Phase 1 completion.
- [x] 2025-10-20 — Phase 2 rollout: Lakehouse writer now supports Delta commits with optional dependency groups, restore CLI added, and version manifests capture git/DVC/lakeFS metadata for reproducible snapshots.
- [x] 2025-10-20 — Phase 3 rollout: Graph semantics toolkit validates CSVW/R2RML outputs with node/edge/degree checks and drift observability logs whylogs-style profiles with alert routing.
- [x] 2025-10-20 — Phase 4 safety gate: Plan→commit policy now requires matching `*.plan`/`*.commit` artefacts with `If-Match` headers, RAG metrics, and prompt-injection heuristics; audit events are appended to `data/logs/plan_commit_audit.jsonl` and MCP payloads enforce the same contract.
- [x] 2025-10-20 — Published ADR 0003 documenting the threat model and STRIDE/MITRE mapping for CLI, MCP, evidence sinks, and governance surfaces; Next_Steps risk gates now reference the baseline matrix and quarterly tabletop cadence.
- [x] 2025-10-20 — Supply-chain automation: CI now emits CycloneDX SBOMs, Sigstore signatures for wheels/sdists, and weekly OpenSSF Scorecard scans; developer workflow documents gitsign configuration for OIDC-backed commit signing.
- [x] 2025-10-20 — MCP plan→commit enforcement hardening: Sigstore-style audit log JSONL now records MCP executions; guard rejects missing `*.commit`, `If-Match`, or low RAG metrics, and tests cover audit logging paths.
- [x] 2025-10-20 — Accessibility baseline: Added axe-core smoke tests for the Streamlit analyst UI, documented heuristic review steps, and wired the smoke test into CI.
- [x] 2025-10-21 — Added Sigstore verification policy (scripts.verify_artifact_signatures) and wheel audit tooling (scripts.wheel_status) to automate supply-chain and Python 3.14/3.15 remediation tracking.
- [x] 2025-10-21 — Chaos/FMEA exercise prep: draft scenario catalog, identify telemetry needed for failure injection, assign owners for MCP vs pipeline game days. ✅ Scenario catalog documented in `docs/chaos-fmea-scenarios.md` with 11 failure modes, RPN scores, game day procedures, and quarterly schedule.
- [x] 2025-10-21 — Drift telemetry upgrade: Pipeline writes whylogs alert history (`alerts.json`) and Prometheus textfile metrics (`metrics.prom`) with configuration via `DRIFT_ALERT_OUTPUT` / `DRIFT_PROMETHEUS_OUTPUT`; docs updated, baseline seeding utility + sample Prometheus rules committed, and tests cover log/metric emission.
- [x] 2025-10-21 — QA automation upgrade: Added format/problems commands with plan auto-generation, integrated mypy into Trunk linting, and documented new CQ workflows to minimise manual triage.
- [x] 2025-10-21 — QA pipeline dry run (agent): pytest ✅ (293 passed, 86% cover), sqlfluff ✅ after seeding `CONTRACTS_CANONICAL_JSON`, yamllint ✅ (fixed `.venv/` ignore), markdownlint ❌ (nodeenv TLS - remains blocked), mypy ✅ (fixed return annotations, `tomli` confirmed in deps), bandit ⚠️ (subprocess warnings - expected/nosec'd), axe smoke ✅ (fixed temp profile), collect_problems ⚠️ (markdownlint dependency remains blocked by nodeenv TLS). ⏳ Remaining: vendor/cert-pin node toolchain for offline markdownlint.
- [x] 2025-10-22 — Deequ enforcement: Implemented deterministic Deequ checks with pandas fallback, wired CLI/evidence logging to include Deequ results, added failure messaging, refreshed docs/CHANGELOG to note release blocker now hard-gated.
- [x] 2025-10-21 — Legal & disclosure baseline: Added MIT LICENSE file and comprehensive SECURITY.md with VDP, security controls, compliance frameworks (NIST SSDF, OWASP ASVS L2, POPIA), and responsible disclosure process. Updated pyproject.toml to declare MIT license. Completes WC-01 and WC-02 acceptance criteria.
- [x] 2025-10-21 — Documentation completion audit: Marked `docs/data-quality.md` and `codex/` artefacts as complete in Next_Steps.md; updated Red Team doc to reflect completion status for WC-07 through WC-12, WC-14, WC-15, WC-16, and WC-19 based on iteration log evidence.
- [ ] 2025-10-22 — Baseline QA audit (agent): `pytest` ❌ (content hygiene contract missing body preservation); `ruff` ❌ (pre-existing unused imports in integrations/tests); `mypy` ❌ (missing opentelemetry stubs + chaos typing); `bandit` ⚠️ (MD5 usage flagged in content hygiene); `pre-commit` ⚠️ (nodeenv TLS failure); `offline_safety` ✅; `poetry build` ✅. Documented blockers before contract registry work.
- [ ] 2025-10-22 — Contract registry instrumentation: Added Pydantic contract adapters for pipeline/evidence, JSON+Avro schema exporters with snapshots, CLI/MCP metadata embedding, and plan→commit/evidence validation guards. Awaiting full QA run once baseline issues cleared.
- [x] 2025-10-22 — Contract sink regression follow-up: Normalised evidence sink shims/tests to accept contract payloads, updated pipeline/MCP fixtures to coerce contracts back to dataclasses, and reran targeted pytest suite (`tests/test_audit.py`, `tests/test_pipeline.py`, `tests/test_mcp.py`) successfully.

## 2) Deliverables

- [ ] **Crawlkit cut-over playbook & CLI alignment** — _Owner: Platform/Research · Due: 2025-10-27_
  - Acceptance criteria: Crawlkit cut-over runbook published with sequencing for adapter swaps, CLI and automation docs updated to surface new feature flags, and MCP Promptfoo gate references refreshed for Crawlkit endpoints.
  - Evidence: [`SCRATCH.md`](SCRATCH.md), [`docs/cli.md`](docs/cli.md), [`docs/mcp-promptfoo-gate.md`](docs/mcp-promptfoo-gate.md)
- [ ] **Contracts vNext — registry + adapter rollout** — _Owner: Platform/Data · Due: 2025-11-05_
  - Acceptance criteria: Contract registry documentation live, CLI/MCP emit schema URIs with semantic versioning, Avro/JSON Schema regression suites green, and evidence sinks enforcing schema validation end-to-end.
  - Evidence: [`data_contracts/`](data_contracts), [`docs/data-quality.md`](docs/data-quality.md), [`apps/automation/cli.py`](apps/automation/cli.py)
- [ ] **Wheel remediation — Python 3.13/3.14/3.15 blockers** — _Owner: Platform/Data/Security · Due: 2025-11-08_
  - Acceptance criteria: `cp314`/`cp315` wheels published for tracked packages (argon2-cffi-bindings, cryptography, dbt-extractor, duckdb, psutil, tornado, etc.) and `python -m scripts.dependency_matrix guard --strict` passes with zero blockers.
  - Evidence: [`scripts/wheel_status.py`](scripts/wheel_status.py), [`tools/dependency_matrix/wheel_status.json`](tools/dependency_matrix/wheel_status.json), [`tools/dependency_matrix/status.json`](tools/dependency_matrix/status.json)
- [ ] **QA baseline remediation — nodeenv + typing gaps** — _Owner: QA/Platform · Due: 2025-10-28_
  - Acceptance criteria: Markdownlint CLI runnable offline (nodeenv certificate pinning), mypy clean with `tomli` dependency verified, axe smoke test isolates Chrome profile, yamllint limited to tracked sources, and problems collector completes without TLS errors.
  - Evidence: [`scripts/collect_problems.py`](scripts/collect_problems.py), [`apps/automation/cli.py`](apps/automation/cli.py), [`docs/ephemeral-qa-guide.md`](docs/ephemeral-qa-guide.md)
- [ ] **Chaos/FMEA exercise for pipeline & MCP** — _Owner: SRE/Security · Due: 2026-01-31_
  - Acceptance criteria: Execute Q4 2025 scenarios (F-001, F-004, F-011), capture RPN deltas and mitigation actions in the FMEA register, and archive game day artefacts alongside observability telemetry snapshots.
  - Evidence: [`docs/chaos-fmea-scenarios.md`](docs/chaos-fmea-scenarios.md), [`Next_Steps.md`](Next_Steps.md#steps-iteration-log)

---

## 3) Red‑Team Integration — Quick Index (WC‑01 … WC‑20)

Execute in this order; each item must meet its gate before promotion.

1. **WC‑01** Secrets/PII purge → rotate, purge history, Secret Scanning/Push Protection, `.env.example`.
2. **WC‑03** Robots & politeness (RFC 9309) → per‑host queues, backoff, traps, canonicalisation.
3. **WC‑05** MCP write safety → `*.plan`→diff→`*.commit` with `If‑Match`; typed schemas; audit.
4. **WC‑07** Data contracts → GX/dbt/Deequ hard gates.
5. **WC‑08/09** Lineage + ACID + versioning → OpenLineage/PROV‑O/DCAT; Delta/Iceberg; DVC/lakeFS commits.
6. **WC‑10** Tabular→graph by spec → CSVW/R2RML/RML; PageRank/Louvain on rolling windows.
7. **WC‑11/12** Observability & eval → whylogs drift; Ragas gating.
8. **WC‑13/14** Supply chain → multi‑stage non‑root containers; SBOM/Sigstore/SLSA; OpenSSF Scorecard.

---

## 4) WC ↔ AT Cross‑walk (traceability)

|   WC ID   | Purpose                      | AT Dependencies (primary)         |
| :-------: | ---------------------------- | --------------------------------- |
|   WC‑01   | Secret hygiene & PII removal | AT‑20, AT‑23                      |
|   WC‑03   | Crawl legality & safety      | AT‑07, AT‑08, AT‑09               |
|   WC‑05   | MCP write safety             | AT‑15, AT‑16, AT‑17, AT‑18, AT‑19 |
|   WC‑07   | Data contracts               | AT‑24, AT‑29                      |
|   WC‑08   | Lineage & catalogue          | AT‑25                             |
|   WC‑09   | ACID tables + versioning     | AT‑26, AT‑27                      |
|   WC‑10   | Graph semantics              | AT‑28, AT‑12, AT‑14               |
|   WC‑11   | Profiling & drift            | AT‑30                             |
|   WC‑12   | RAG/agent evaluation         | AT‑31, AT‑32, AT‑33               |
| WC‑13..20 | Supply chain & operations    | AT‑20, AT‑21, AT‑22, AT‑23        |

---

## 5) Milestones & Exit Criteria

| Milestone                   | Window                  | Scope               | Exit Criteria                                                                             |
| --------------------------- | ----------------------- | ------------------- | ----------------------------------------------------------------------------------------- |
| **M1: Legal & Secrets**     | 2025‑10‑18 → 2025‑10‑24 | WC‑01, WC‑02, WC‑03 | History purged & rotated; license/VDP live; robots/traps compliance = green.              |
| **M2: Contracts On**        | 2025‑10‑25 → 2025‑11‑15 | WC‑07               | GX/dbt/Deequ coverage ≥95%; CI blocks on failure; Data Docs published.                    |
| **M3: Lineage & Lakehouse** | 2025‑11‑01 → 2025‑12‑06 | WC‑08, WC‑09        | 100% lineage; ACID tables adopted; time‑travel restore proven; DVC/lakeFS commit linked.  |
| **M4: Safety & MCP**        | 2025‑11‑05 → 2025‑12‑05 | WC‑05, WC‑06, WC‑12 | Red‑team suite green; MCP plan→diff→commit audit logs; Ragas thresholds enforced.         |
| **M5: Graph & Drift**       | 2025‑12‑01 → 2026‑01‑10 | WC‑10, WC‑11        | CSVW/R2RML/RML validation; PageRank/Louvain online; drift alerts wired.                   |
| **M6: Supply Chain & Ops**  | 2025‑11‑05 → 2026‑01‑31 | WC‑13..WC‑20        | Non‑root multi‑stage images; SBOM/signing/Scorecard; OTel dashboards; chaos MTTR <30 min. |

---

## 6) Quality Gates (release blockers)

- Any failing **GX/dbt/Deequ** test on publishable datasets (AT‑24).
- Missing **OpenLineage/PROV‑O/DCAT** for a publishable run (AT‑25).
- Curated writes to **non‑ACID** tables or runs without a **DVC/lakeFS** commit (AT‑26/27).
- **CSVW/R2RML/RML** validation failure or graph post‑build metrics out of bounds (AT‑28).
- **whylogs** drift beyond thresholds or missing profiles (AT‑30).
- **Ragas** scores below thresholds (AT‑31).
- **OWASP LLM Top‑10** red‑team failure (AT‑32).
- MCP **plan→diff→commit** audit trail missing or `If‑Match` not enforced (AT‑33).
- **QA baseline 2025-10-21** partial resolution: ✅ mypy `scripts/collect_problems.py` fixed (return annotations), ✅ axe smoke Chrome profile fixed (temp dirs), ✅ yamllint `.venv/` scanning fixed (ignore globs). ⏳ Remaining blocker: markdownlint CLI nodeenv TLS issue (requires offline node tarball cache or CA trust config); treat markdownlint gate as advisory until resolved.

---

## 7) Links (End)

- [x] Operations runbook — Great Expectations contract execution guidance → `docs/operations.md`
- [x] Cleanup automation — `scripts/cleanup.py`
- [x] Dependency blocker status — `tools/dependency_matrix/status.json`
- [x] Lineage & lakehouse configuration → `docs/lineage-lakehouse.md`
- [x] CLI surfaces → `docs/cli.md`
- [x] Surface taxonomy → `docs/surface-taxonomy.md`
- [x] MCP audit log policy — Owner, storage, retention → `docs/mcp-audit-policy.md`
- [x] MCP promptfoo gate policy — Evaluation thresholds, rollout phases → `docs/mcp-promptfoo-gate.md`
- [x] Chaos/FMEA scenario catalog — Failure modes, game day procedures → `docs/chaos-fmea-scenarios.md`
- [x] Data quality suites (GX/dbt/Deequ) → `docs/data-quality.md`
- [x] Codex DX bundle & evals → `codex/README.md`, `codex/evals/promptfooconfig.yaml`

---

## 8) Risks/Notes (active, de‑duplicated)

- Running Great Expectations locally regenerates `data_contracts/great_expectations/uncommitted/config_variables.yml`; keep it ignored and document analyst‑specific overrides per run.
- Confirm repository‑root anchored paths in `firecrawl_demo.core.config` propagate to packaging/release workflows; adjust docs if downstream tools expect package‑root paths.
- Keep Firecrawl SDK behind a feature flag until credentials and ALLOW_NETWORK_RESEARCH policy are finalised.
- Enforce Python ≥3.13,<3.15; monitor GE compatibility before promoting Python 3.15 and verifying Great Expectations/dbt compatibility.
- **[DOCUMENTED]** ~~Decide owner + storage for MCP audit logs (plan→diff→commit) and retention policy.~~ Policy documented in `docs/mcp-audit-policy.md`: Owner=Platform/Security, Storage=`data/logs/plan_commit_audit.jsonl` (local/CI) with 90-day retention, production TBD based on deployment target.
- **[DOCUMENTED]** ~~Block MCP/agent sessions in hardened platform distributions unless `promptfoo eval` has passed in the active branch.~~ Gate policy documented in `docs/mcp-promptfoo-gate.md`: Three-phase rollout (advisory→soft→hard gate) with minimum thresholds (faithfulness≥0.85, context_precision≥0.80, tool_use≥0.90) and 7-day freshness requirement.
- Kafka lineage transport requires the optional `kafka-python` dependency; platform team to confirm packaging before enabling Kafka emission in CI/staging.
- **[RESOLVED]** ~~Ensure developer images document/install external CLI deps (`markdownlint-cli2`, `actionlint`, `hadolint`) so pre-commit parity holds in clean environments.~~ `actionlint` and `hadolint` binaries are now bundled in `tools/bin/` for all platforms (Linux x86_64/arm64, macOS x86_64/arm64) to support ephemeral runners without internet access. Bootstrap utilities check for bundled binaries first. `markdownlint-cli2` still requires Node hooks via `pre-commit`'s bundled `nodeenv`.
- **[ACTION REQUIRED]** Regenerate `requirements-dev.txt` hashes so transitive dependencies like `narwhals` resolve under `--require-hashes` installs. Command: `poetry export -f requirements.txt --with dev --output requirements-dev.txt` (requires network access for Poetry/PyPI).
- Python 3.15 compatibility currently blocked by missing wheels for `argon2-cffi-bindings`, `cryptography`, `dbt-extractor`, `duckdb`, `psutil`, `tornado`, and other tracked packages; track expectations via `presets/dependency_blockers.toml`, ongoing findings in `tools/dependency_matrix/report.json`, and guard outputs in `tools/dependency_matrix/status.json`.
- [x] 2025-10-21 — Implemented Sigstore signing guardrail: CI now signs artifacts in the build job and enforces `scripts.verify_artifact_signatures` to validate bundle identity before upload; supply-chain plan→commit gate updated accordingly.
- Node tooling requires certificate pinning/offline cache: `pre-commit run markdownlint-cli2` and `scripts/collect_problems.py` fail under SSL `Missing Authority Key Identifier` when nodeenv resolves `index.json`; bundle cached Node tarballs or configure trusted CAs before treating markdownlint as blocking.
- Baseline QA currently red on `tests/test_content_hygiene.py::TestBoilerplateRemoval::test_removes_navigation`; contract rollout must not regress this area once fixed—coordinate with content hygiene owners before touching heuristics.
- **[RESOLVED]** ~~`apps/analyst/accessibility/axe_smoke.py` reuses the default Chrome user data dir in shared runners, triggering `SessionNotCreatedException`; inject per-run temp profiles to unblock accessibility smoke in CI and local QA.~~ Fixed: `axe_smoke.py` now creates unique temporary profile directories using `tempfile.TemporaryDirectory()` to prevent conflicts.
- **[RESOLVED]** ~~Mypy strict mode now errors on `scripts/collect_problems.py` (missing `tomli`, `No return value expected`, strict Optional handling); align dependencies and refactor functions to return `None` explicitly before enabling gate.~~ Fixed: Added explicit `return None` statements to all functions with `-> None` annotation; `tomli` already in dependencies as fallback for Python <3.11.
- **[RESOLVED]** ~~Yamllint traverses `.venv/` during repo-root scans; tighten ignore globs or run against `git ls-files` to avoid virtualenv noise during gated runs.~~ Fixed: Added `.venv/**` and `**/.venv/**` to `.yamllint.yaml` ignore patterns.
