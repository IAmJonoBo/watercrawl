# Next Steps (Q4‑2025 → Q1‑2026)

> Single source of truth for what ships next. Kept lean, action‑oriented, and auditable. All write paths follow **plan → diff → commit** with `If‑Match` preconditions and produce lineage/provenance artefacts.

---

## 1) Open Tasks (owner · due · gate)

- [ ] **Phase 1 — Data contracts + evidence enforcement** (AT‑24, AT‑29) — _Owner: Data · Due: 2025‑11‑15_
  - Gates: GX/dbt/Deequ block publish; Pint/Hypothesis enforced in CI; ≥95% curated tables covered.
- [ ] **Phase 2 — Lineage, catalogue, and versioning rollout** (AT‑25, AT‑26, AT‑27) — _Owner: Platform · Due: 2025‑12‑06_
  - Gates: OpenLineage + PROV‑O + DCAT live; curated writes to Delta/Iceberg; runs tagged with DVC/lakeFS commits; time‑travel restore proven.
- [ ] **Phase 3 — Graph semantics + drift observability** (AT‑28, AT‑30) — _Owner: Data/Platform · Due: 2026‑01‑10_
  - Gates: CSVW/R2RML validation; node/edge/degree checks in range; whylogs baselines + alerts wired.
- [ ] **Phase 4 — LLM safety, evaluation, and MCP plan→commit** (AT‑31, AT‑32, AT‑33) — _Owner: Platform/Security · Due: 2026‑01‑31_
  - Gates: Ragas thresholds green; OWASP LLM Top‑10 red‑team passes; MCP audit logs show `If‑Match` and diff review.
- [ ] **Validate Poetry exclude list in release pipeline** — _Owner: Platform · Due: 2025‑10‑31_
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

- [x] 2025-10-18 — Baseline QA suite re-validated; scripted cleanup keeps local artefacts aligned with CI and unblocks failing pushes.
- [x] 2025-10-18 — Phase 2 hygiene: refreshed governance/drift modules via `pyupgrade` and documented the cleanup workflow for analysts.

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
- [ ] Lineage & lakehouse configuration → `docs/lineage-lakehouse.md`
- [ ] Data quality suites (GX/dbt/Deequ) → `docs/data-quality.md`
- [ ] Codex DX bundle & evals → `codex/README.md`, `codex/evals/promptfooconfig.yaml`

---

## 7) Risks/Notes (active, de‑duplicated)

- Running Great Expectations locally regenerates `great_expectations/uncommitted/config_variables.yml`; keep it ignored and document analyst‑specific overrides per run.
- Confirm repository‑root anchored paths in `firecrawl_demo.core.config` propagate to packaging/release workflows; adjust docs if downstream tools expect package‑root paths.
- Keep Firecrawl SDK behind a feature flag until credentials and ALLOW_NETWORK_RESEARCH policy are finalised.
- Enforce Python ≥3.11; monitor GE compatibility before removing `<3.14` pin.
- Decide owner + storage for MCP audit logs (plan→diff→commit) and retention policy.
- Block MCP/agent sessions in `dist` builds unless `promptfoo eval` has passed in the active branch.
