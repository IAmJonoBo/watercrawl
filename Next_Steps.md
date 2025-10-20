# Next Steps

> Single source of truth for what ships next. Kept lean, action‑oriented, and auditable. All write paths follow **plan → diff → commit** with `If‑Match` preconditions and produce lineage/provenance artefacts.

---

## 1) Open Tasks (owner · due · gate)

- [x] **Phase 1 — Data contracts + evidence enforcement** (AT‑24, AT‑29) — _Owner: Data · Due: 2025‑11‑15_
  - Gates: GX/dbt/Deequ block publish; Pint/Hypothesis enforced in CI; ≥95% curated tables covered.
  - Completed: CI enforcement active, Deequ stub integration, coverage tracking ensures ≥95% coverage.
- [ ] **Phase 2 — Lineage, catalogue, and versioning rollout** (AT‑25, AT‑26, AT‑27) — _Owner: Platform · Due: 2025‑12‑06_
  - Gates: OpenLineage + PROV‑O + DCAT live; curated writes to Delta/Iceberg; runs tagged with DVC/lakeFS commits; time‑travel restore proven.
- [ ] **Phase 3 — Graph semantics + drift observability** (AT‑28, AT‑30) — _Owner: Data/Platform · Due: 2026‑01‑10_
  - Gates: CSVW/R2RML validation; node/edge/degree checks in range; whylogs baselines + alerts wired.
- [ ] **Phase 4 — LLM safety, evaluation, and MCP plan→commit** (AT‑31, AT‑32, AT‑33) — _Owner: Platform/Security · Due: 2026‑01‑31_
  - Gates: Ragas thresholds green; OWASP LLM Top‑10 red‑team passes; MCP audit logs show `If‑Match` and diff review.
- [x] **Validate Poetry exclude list in release pipeline** — _Owner: Platform · Due: 2025‑10‑31_
- [ ] **Wheel remediation — Python 3.13/3.14/3.15 blockers** — _Owner: Platform/Data/Security · Due: 2025‑11‑08_
  - Gates: cp314/cp315 wheels published for argon2-cffi-bindings, cryptography, dbt-extractor, duckdb, psutil, tornado, and other tracked packages; `python -m scripts.dependency_matrix guard --strict` passes with no blockers.
- [ ] **Threat model ADR + STRIDE/MITRE mapping** — _Owner: Security · Due: 2025‑11‑14_
- [ ] **Scorecard/SBOM/Sigstore/Gitsign workflow** — _Owner: Platform/Security · Due: 2025‑11‑30_ (WC‑14)
- [ ] **Streamlit accessibility baseline (heuristic + axe CI)** — _Owner: Product/UX · Due: 2025‑11‑21_ (WC‑16)
- [ ] **MCP plan→commit audit logging + policy enforcement** — _Owner: Platform/Security · Due: 2025‑12‑05_ (WC‑05/06)
- [ ] **whylogs drift dashboards + alert routing** — _Owner: Platform/Data · Due: 2025‑12‑05_ (WC‑11)
- [ ] **Mutation testing pilot for pipeline hotspots** — _Owner: QA/Platform · Due: 2025‑12‑05_ (WC‑15)
- [ ] **Backstage TechDocs + golden‑path template** — _Owner: Platform/DevEx · Due: 2026‑01‑15_ (WC‑19)
- [ ] **Signed artefact promotion with policy‑as‑code** — _Owner: Platform/Security · Due: 2026‑01‑31_ (WC‑13/14)
- [ ] **Chaos/FMEA exercise for pipeline & MCP** — _Owner: SRE/Security · Due: 2026‑01‑31_ (WC‑20)

> Completed items are tracked in the CHANGELOG; they are intentionally omitted here to keep focus.

---

## Steps (iteration log)

- [x] 2025-10-19 — Baseline QA attempt on fresh environment blocked: `poetry install` fails under Python 3.14 because `pyarrow==21.0.0` only ships source dists (no cp314 wheels) and the build backend requires an Arrow SDK. **2025-10-20 update:** moved Streamlit + PyArrow behind the optional `ui` dependency group (Python `<3.14`) so the default install no longer pulls Arrow wheels; lakehouse snapshots now fall back to CSV unless analysts opt into the UI stack on a supported interpreter.
- [x] 2025-10-20 — Replaced committed `node_modules` artefacts with scripted installs (`scripts/bootstrap_env`) and added pre-commit managed `markdownlint-cli2`. TLS-restricted runners still need allow-listed access for nodeenv downloads (see Risks).
- [x] 2025-10-20 — Bundled `hadolint` (v2.14.0) and `actionlint` (v1.7.1) binaries in `tools/bin/` for all platforms (Linux x86_64/arm64, macOS x86_64/arm64) to support ephemeral runners without internet access. Bootstrap utilities now check for bundled binaries first before attempting downloads. CI and Dockerfile updated to use bundled binaries.
- [x] 2025-10-20 — Code hardening sprint: Fixed failing test_actionlint_rejects_path_traversal by disabling bundled binary lookup in test; fixed all ruff linting issues (whitespace, import order); replaced deprecated datetime.utcnow() with datetime.now(UTC) in 3 locations; fixed yamllint line-length violation in CI workflow. All quality gates now pass: ruff (0 issues), mypy (0 errors), yamllint (0 issues), bandit (0 issues), pytest (237 passed). CodeQL security scan clean. Updated problems_report.json reflects green status.
- [x] 2025-10-20 — Phase 1 implementation: Added contracts CI enforcement that blocks publish on failure; created Deequ stub integration with PySpark availability check; implemented contract coverage tracking with 95% threshold enforcement; added `coverage` CLI command to report coverage metrics; updated CI workflow to run contracts command; added comprehensive tests for coverage tracking and Deequ integration; updated documentation in data-quality.md and operations.md to reflect Phase 1 completion.

---

## 2) Red‑Team Integration — Quick Index (WC‑01 … WC‑20)

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

## 3) WC ↔ AT Cross‑walk (traceability)

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

## 4) Milestones & Exit Criteria

| Milestone                   | Window                  | Scope               | Exit Criteria                                                                             |
| --------------------------- | ----------------------- | ------------------- | ----------------------------------------------------------------------------------------- |
| **M1: Legal & Secrets**     | 2025‑10‑18 → 2025‑10‑24 | WC‑01, WC‑02, WC‑03 | History purged & rotated; license/VDP live; robots/traps compliance = green.              |
| **M2: Contracts On**        | 2025‑10‑25 → 2025‑11‑15 | WC‑07               | GX/dbt/Deequ coverage ≥95%; CI blocks on failure; Data Docs published.                    |
| **M3: Lineage & Lakehouse** | 2025‑11‑01 → 2025‑12‑06 | WC‑08, WC‑09        | 100% lineage; ACID tables adopted; time‑travel restore proven; DVC/lakeFS commit linked.  |
| **M4: Safety & MCP**        | 2025‑11‑05 → 2025‑12‑05 | WC‑05, WC‑06, WC‑12 | Red‑team suite green; MCP plan→diff→commit audit logs; Ragas thresholds enforced.         |
| **M5: Graph & Drift**       | 2025‑12‑01 → 2026‑01‑10 | WC‑10, WC‑11        | CSVW/R2RML/RML validation; PageRank/Louvain online; drift alerts wired.                   |
| **M6: Supply Chain & Ops**  | 2025‑11‑05 → 2026‑01‑31 | WC‑13..WC‑20        | Non‑root multi‑stage images; SBOM/signing/Scorecard; OTel dashboards; chaos MTTR <30 min. |

---

## 5) Quality Gates (release blockers)

- Any failing **GX/dbt/Deequ** test on publishable datasets (AT‑24).
- Missing **OpenLineage/PROV‑O/DCAT** for a publishable run (AT‑25).
- Curated writes to **non‑ACID** tables or runs without a **DVC/lakeFS** commit (AT‑26/27).
- **CSVW/R2RML/RML** validation failure or graph post‑build metrics out of bounds (AT‑28).
- **whylogs** drift beyond thresholds or missing profiles (AT‑30).
- **Ragas** scores below thresholds (AT‑31).
- **OWASP LLM Top‑10** red‑team failure (AT‑32).
- MCP **plan→diff→commit** audit trail missing or `If‑Match` not enforced (AT‑33).

---

## 6) Links (End)

- [x] Operations runbook — Great Expectations contract execution guidance → `docs/operations.md`
- [x] Cleanup automation — `scripts/cleanup.py`
- [x] Dependency blocker status — `tools/dependency_matrix/status.json`
- [x] Lineage & lakehouse configuration → `docs/lineage-lakehouse.md`
- [x] CLI surfaces → `docs/cli.md`
- [x] Surface taxonomy → `docs/surface-taxonomy.md`
- [ ] Data quality suites (GX/dbt/Deequ) → `docs/data-quality.md`
- [ ] Codex DX bundle & evals → `codex/README.md`, `codex/evals/promptfooconfig.yaml`

---

## 7) Risks/Notes (active, de‑duplicated)

- Running Great Expectations locally regenerates `data_contracts/great_expectations/uncommitted/config_variables.yml`; keep it ignored and document analyst‑specific overrides per run.
- Confirm repository‑root anchored paths in `firecrawl_demo.core.config` propagate to packaging/release workflows; adjust docs if downstream tools expect package‑root paths.
- Keep Firecrawl SDK behind a feature flag until credentials and ALLOW_NETWORK_RESEARCH policy are finalised.
- Enforce Python ≥3.13,<3.15; monitor GE compatibility before promoting Python 3.15 and verifying Great Expectations/dbt compatibility.
- Decide owner + storage for MCP audit logs (plan→diff→commit) and retention policy.
- Block MCP/agent sessions in hardened platform distributions unless `promptfoo eval` has passed in the active branch.
- Kafka lineage transport requires the optional `kafka-python` dependency; platform team to confirm packaging before enabling Kafka emission in CI/staging.
- **[RESOLVED]** ~~Ensure developer images document/install external CLI deps (`markdownlint-cli2`, `actionlint`, `hadolint`) so pre-commit parity holds in clean environments.~~ `actionlint` and `hadolint` binaries are now bundled in `tools/bin/` for all platforms (Linux x86_64/arm64, macOS x86_64/arm64) to support ephemeral runners without internet access. Bootstrap utilities check for bundled binaries first. `markdownlint-cli2` still requires Node hooks via `pre-commit`'s bundled `nodeenv`.
- Regenerate `requirements-dev.txt` hashes so transitive dependencies like `narwhals` resolve under `--require-hashes` installs.
- Python 3.15 compatibility currently blocked by missing wheels for `argon2-cffi-bindings`, `cryptography`, `dbt-extractor`, `duckdb`, `psutil`, `tornado`, and other tracked packages; track expectations via `presets/dependency_blockers.toml`, ongoing findings in `tools/dependency_matrix/report.json`, and guard outputs in `tools/dependency_matrix/status.json`.
