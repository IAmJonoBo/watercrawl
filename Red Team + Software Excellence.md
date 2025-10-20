# Frontier Software Excellence & Red-Team Copilot Playbook

_Last updated: 2025-10-17_

## 0. Mission & Operating Mode

- Elevate the ACES Aerodynamics Enrichment Stack to frontier delivery, safety, and DX maturity while keeping evidence-led research guardrails intact.
- Operate as an ensemble spanning Platform/DevEx, Security/Supply-chain, SRE/Observability, Architecture, Product/UX, and QA/Testing. Each recommendation records rationale, alternatives, and impact across maintainability, performance, compliance, and cost.
- Prioritise mitigation by **Risk = Likelihood × Impact** and **Delivery Leverage**. Default to feature-flagged, reversible changes that can be rolled back with existing CLI/MCP tooling.
- Treat this playbook as living documentation—link to artefacts, CI runs, and ADRs. Flag unknowns with owners and validation steps before promotion to "ready".
- Reference governing standards for every guardrail (NIST SSDF v1.1, OWASP SAMM/ASVS L2, OWASP LLM Top-10, SLSA, ISO/IEC 25010 & 5055, POPIA/POPIA s69).

## 1. Project Context Inputs

| Dimension                        | Value                                                                                                                                                                                                                                                          |
| -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Project                          | ACES Aerodynamics Enrichment Stack                                                                                                                                                                                                                             |
| Repo or paths to scan            | [ACES Aerodynamics firecrawl-demo](https://github.com/ACES-Aerodynamics/firecrawl-demo) (mirror at `/workspace/watercrawl`)                                                                                                                                    |
| Stack                            | Python 3.13 • Firecrawl SDK (flagged) • Pandas/DuckDB • Great Expectations • dbt-duckdb • Poetry packaging • MkDocs • Streamlit analyst UI                                                                                                                     |
| Runtime/Infrastructure           | Local CLI/MCP runners; future deployment targets Docker/Kubernetes with evidence sinks (CSV/stream) and optional lakehouse writers                                                                                                                             |
| CI/CD                            | GitHub Actions (`ci.yml`) running lint, test, contracts, CI summary upload                                                                                                                                                                                     |
| Package manager                  | Poetry (lock enforced)                                                                                                                                                                                                                                         |
| Ranked non-functional priorities | Security & compliance → Data quality & evidence → Reliability & provenance → Maintainability → Developer Experience → Performance → Accessibility                                                                                                              |
| Compliance / targets             | NIST SSDF v1.1, OWASP SAMM (target L2 maturity), OWASP ASVS L2 (CLI/API surfaces), OWASP LLM Top-10, SLSA Level 2 (aspirational), OpenSSF Scorecard ≥7, ISO/IEC 25010 quality model, ISO/IEC 5055 structural quality, POPIA (South Africa)                     |
| Constraints                      | Offline-first deterministic research adapters; POPIA s69 limits; Firecrawl SDK gated behind `FEATURE_ENABLE_FIRECRAWL_SDK`; evidence log requires ≥2 sources (≥1 official); province taxonomy locked to ZA list; analysts rely on reproducible CLI + MCP flows |

## 2. Discovery → Objectives → Measures

- **Objectives**: maintain verifiable enrichment outputs, harden supply-chain posture, guarantee deterministic offline behaviour, and scale Copilot automation safely.
- **Constraints**: no regression in evidence logging, maintain current CLI contract, keep docs/MkDocs current, and respect Codeowners guardrails.
- **Measures of success**:
  - DORA Four Keys baseline from CI + deployment logs (initial targets: weekly deploy frequency, <24h lead time, <15% change failure rate, MTTR <4h).
  - SPACE/DevEx metrics: CLI completion time, test cycle duration, pre-commit friction reports, MCP usage telemetry.
  - Security KPIs: Scorecard >7, dependency freshness <14 days, zero high Bandit findings, signed artefacts coverage.
  - Data quality: GX/dbt contract pass rate 100%, drift monitors triggered ≤5% of runs, evidence log completeness ≥98%.

## 3. Scope (Complete All Sections)

### 3.1 Rapid System Model

- **Architecture**: layered Python packages—`core` (validation, pipeline, compliance), `integrations` (research adapters, lakehouse, lineage, drift), `governance` (safety, secrets, RAG evaluation), `interfaces` (CLI, MCP, analyst UI).【F:docs/architecture.md†L5-L49】
- **Data flow**: CSV/XLSX → validation → enrichment via adapter registry → compliance normalisation → evidence sink → lineage/versioning artefacts.【F:docs/architecture.md†L51-L74】
- **Trust boundaries**: local analyst workstation ↔ evidence sink storage, optional Firecrawl SDK (external network), secrets providers (ENV/AWS/Azure), GitHub Actions CI environment, prospective lakehouse/graph backends.
- **Critical assets**: `data/` curated datasets, `evidence_log.csv`, secrets backends, lineage manifests, policy configs (`firecrawl_demo.infrastructure.planning`).
- **AuthZ**: CLI/MCP rely on environment-level secrets; future MCP expansions must enforce plan→commit gating with audit logs.

### 3.2 Red-Team Analysis (Design → Code → Build → Deploy → Run)

| Phase  | Threat surface                               | Current controls                                                                   | Gaps / actions                                                                                                |
| ------ | -------------------------------------------- | ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Design | Agent overreach, missing threat models       | LLM safety guards, OWASP LLM Top-10 mitigations scaffolded in `governance.safety`  | Formal STRIDE model absent; add threat-model ADR + tabletop review                                            |
| Code   | Adapter sandboxing, secrets hygiene          | Feature flags, secrets backend abstraction, Ruff/Bandit/mypy gating                | Add Semgrep/CodeQL job; enforce secret scanning & commit signing                                              |
| Build  | Dependency tampering, provenance             | Poetry lock pinned; CI builds wheel/sdist                                          | Generate CycloneDX SBOM + in-toto provenance; adopt `poetry export --without-hashes` audit stage              |
| Deploy | Evidence sink exfiltration, Firecrawl misuse | Feature flags default to offline; evidence sink CSV stored locally                 | Implement policy-as-code check to block network operations unless allowlisted; add streaming sink authN story |
| Run    | Drift in research results, LLM hallucination | whylogs baseline (pending dashboards), RAG scorer gating, evidence log enforcement | Automate drift alert routing, add chaos/penetration tests for MCP plan→commit paths                           |

**Immediate mitigations**:

1. Add STRIDE + MITRE mapping for pipeline & MCP interfaces (documented in section 3.13).
2. Extend CI with Scorecard/SBOM/provenance to progress toward SLSA Level 2. ✅ CI now generates CycloneDX SBOMs, Sigstore signatures, and emits OpenSSF Scorecard reports.
3. Harden MCP diff/commit controls with allowlisted tools and auditing. ✅ Plan→commit guard now enforces commit artefacts, `If-Match`, RAG thresholds, and JSONL audit logs for CLI/MCP flows.

### 3.3 Framework Gap Analysis

| Framework             | Current                                                                                                        | Target                                         | Key blockers                                                                                |
| --------------------- | -------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- | ------------------------------------------------------------------------------------------- |
| **NIST SSDF v1.1**    | PS.2/3, PW.4, RV.1 achieved through tests, lint, security scan; PO partially covered via Next_Steps and MkDocs | Full PS/PW/RV/PO coverage                      | Missing secure design records, SBOM/provenance, incident response drills                    |
| **OWASP SAMM**        | Governance/Implementation L1.5, Verification L1.5, Operations L1                                               | Governance & Verification L2                   | Need continuous threat modeling, SBOM policy, runtime monitoring                            |
| **OWASP ASVS L2**     | CLI uses typed inputs; limited authentication/authorisation coverage                                           | Documented control list & verification mapping | MCP/CLI require access control matrix & fuzzing                                             |
| **SLSA**              | Level 1 (scripted build, provenance missing)                                                                   | Level 2                                        | Need isolated CI builders, signed attestations, dependency verification                     |
| **OpenSSF Scorecard** | Estimated 5.5 (branch protection, CI, dependencies)                                                            | ≥7                                             | Add dependency update automation, scorecard workflow, secret scanning                       |
| **ISO/IEC 25010**     | Strength in reliability/maintainability; gaps in usability/accessibility metrics                               | Balanced measurement across characteristics    | Add UX heuristics, accessibility review, performance SLIs                                   |
| **ISO/IEC 5055**      | Emerging coverage via lint/tests; no structural quality reporting                                              | Establish scanning and tracking backlog        | Integrate Sonar-like structural metrics (e.g., Semgrep Code Quality, maintainability index) |

### 3.4 Developer Experience (DX) & Delivery Flow

- **Baseline**: Poetry + pre-commit reduce drift; CLI flows well documented; Next_Steps acts as programme board.
- **Friction**: heavy local setup (dbt/duckdb), missing Backstage/IDP, limited telemetry on CLI run duration.
- **Experiments**:
  1. Instrument CLI to emit run timings & adapter metrics to Prometheus stub.
  2. Provide `justfile` or `Makefile` wrappers for baseline QA commands.
  3. Publish Streamlit UI quickstart & include accessibility tests.
  4. Introduce Backstage TechDocs referencing MkDocs build.
  5. Run quarterly DevEx surveys capturing SPACE metrics (flow efficiency, satisfaction, cognitive load).

### 3.5 UX/UI & Accessibility

- Analyst UI (Streamlit) requires heuristic review; no automated WCAG tests yet.
- Actions: add axe-core CI scan for Streamlit components, create component checklist referencing ISO 9241-210, embed accessibility acceptance criteria into PR template.

### 3.6 Supply-Chain Posture

- Tasks:
  - Generate CycloneDX SBOM during CI and store as artefact.
  - Emit in-toto provenance for wheels/sdists; sign via Sigstore/Gitsign.
  - Enforce dependency freshness using Renovate (already configured) with policy gating.
  - Validate third-party SBOM/VEX before ingestion; integrate GUAC or equivalent aggregator for evidence sink.
  - Adopt SPIFFE/SPIRE or workload identity plan for streaming sink targets before production rollout.

### 3.7 Quality Gates & Code Quality

- Current gates: pytest (coverage 88%), Ruff, mypy, Bandit, pre-commit, dbt/GX contracts, dotenv-linter, poetry build (per README/CI).【F:README.md†L52-L78】【F:docs/operations.md†L5-L43】
- Enhancements: add mutation testing (mutmut or cosmic-ray) with 40% pilot coverage; integrate Semgrep security suite; enforce coverage ratchet (88% → 90%); add OWASP ZAP baseline for future web surface; extend PR template with coverage delta capture.

### 3.8 Future-Proofing & Architecture

- Implement automated fitness functions: coupling checks via `pytest --fixtures`, cycle detection in module graph, pipeline SLA monitors.
- Maintain ADR cadence (threat modeling, SBOM/provenance) and extend C4 diagrams in docs.
- Expand observability: instrument OpenTelemetry traces for CLI pipeline run, export metrics to sample dashboard, define error budget policy.
- Plan chaos experiments around adapter failures and secrets backend outages.

### 3.9 Automation, Orchestration & Autoremediation

- Introduce GitOps model for evidence sink configuration; adopt OPA/Gatekeeper for infrastructure policy.
- Add progressive delivery strategy for Streamlit app (blue-green) once deployed.
- Configure dependency update bots (Renovate) to auto-open PRs with contract + QA gating and autop-run pre-commit.

### 3.10 Tool-Chain & Tech-Stack Evaluation

- Draft Tech Radar with categories: Adopt (Poetry, Ruff, mypy, dbt, DuckDB), Trial (whylogs, Ragas, Sigstore), Assess (Backstage, Semgrep), Hold (direct network scraping without Firecrawl SDK).
- Require pilot runs and rollback plan before promoting to Adopt.

### 3.11 Concrete Improvements (Codify & Automate)

- Workflow additions: GitHub Actions for Scorecard, Semgrep, CycloneDX SBOM, Sigstore attestations, dependency review.
- Repository artefacts: `SECURITY.md` referencing threat model; update `CODEOWNERS` if additional teams join; ensure PR template includes new gates.
- MCP tooling: expose read-only audit + diff commands before enabling `commit_patch` autop-run.
- Backstage scaffolding: create `catalog-info.yaml`, template definitions, TechDocs referencing MkDocs output.

### 3.12 Roadmap & Measurement

| Horizon | Item                                                    | Owner Role            | Effort | Risk Reduction | Dependencies                        | Verification                               |
| ------- | ------------------------------------------------------- | --------------------- | ------ | -------------- | ----------------------------------- | ------------------------------------------ |
| 30 days | Threat model ADR & STRIDE/MITRE mapping                 | Security/Architecture | M      | High           | docs/architecture.md, MCP design    | ADR merged, tabletop session notes         |
| 30 days | CI supply-chain hardening (Scorecard, SBOM, provenance) | Platform/Security     | M      | High           | GitHub Actions secrets              | CI artifacts, attestations signed          |
| 30 days | Accessibility + UX baseline for Streamlit UI            | Product/UX            | S      | Medium         | Streamlit app, axe tooling          | Heuristic report, axe CI job               |
| 60 days | MCP plan→commit audit logging + policy enforcement      | Platform/Security     | M      | High           | Threat model ADR, OPA policies      | Automated tests blocking unsafe commits    |
| 60 days | Drift dashboards + alert routing (whylogs → Prometheus) | Platform/Data         | M      | Medium         | analytics pipeline                  | Dashboard screenshot, alert runbook        |
| 60 days | Mutation testing pilot (core pipeline modules)          | QA/Platform           | M      | Medium         | pytest integration                  | Mutation score report ≥40%                 |
| 90 days | Backstage TechDocs + golden-path template               | Platform/DevEx        | L      | Medium         | MkDocs output, IDP infra            | Catalog entry published, template scaffold |
| 90 days | Signed artefact promotion with policy-as-code gate      | Platform/Security     | L      | High           | Sigstore integration, SBOM pipeline | Verification logs, rollback drill          |
| 90 days | Chaos & FMEA exercises for pipeline & MCP               | SRE/Security          | M      | High           | Observability stack                 | Game-day report, FMEA register             |

### 3.13 Critical-Reasoning Checks

- **Pre-mortem**: failure drivers include unsigned artefacts allowing tampering, MCP agent overreach, drift alerts ignored, or evidence sink exfiltration. Mitigation: implement signing, enforce MCP plan→commit gating, automate drift notifications, restrict sink credentials.
- **FMEA focus**: pipeline enrichment failure, secrets backend outage, adapter returning stale data, MCP misconfiguration, SBOM attestation failure. Score severity/occurrence/detection and log in Next_Steps.
- **Devil’s advocate**: consider attacker leveraging Firecrawl SDK to bypass offline guardrails; plan to sandbox network calls and log usage.
- **Unknowns**: confirm production deployment target, establish data residency requirements, validate compatibility of Sigstore in air-gapped contexts. Track in Next_Steps with owners.

## 4. Output Format (Use Exactly)

### 4.1 Executive Summary

1. Supply-chain provenance (SBOM + signing) missing → blocks SLSA progress → quick win: add CycloneDX & Sigstore workflow.
2. MCP plan→commit auditing incomplete → risk of agent overreach → quick win: enforce read-only defaults, add audit log stub.
3. Threat modeling documentation absent → risk of blind spots across adapters/secrets → quick win: create ADR + tabletop.
4. Accessibility baseline lacking → risk to UX/ISO 9241 alignment → quick win: axe CI check + heuristic report.
5. Drift monitoring dashboards incomplete → risk of silent data regressions → quick win: wire whylogs metrics to Prometheus stub.

_Maturity snapshot_: `{SSDF: PS/PW/RV ~1.5 → target 3; SAMM: ~1.5 → 2; ASVS: L1 → L2; SLSA: 1 → 2; Scorecard: ~5.5 → 7; 25010: Reliability strong, Usability weak → balance; 5055: Emerging → target managed backlog}`.

### 4.2 Findings

Use the format below for each tracked issue (examples appended in this revision):

1. **Missing supply-chain attestations • High • Confidence: Medium • Evidence: `.github/workflows/ci.yml` lacks SBOM/provenance steps • Assets: build artefacts** — `{SSDF:PW.6 | SLSA:L2.Build.1 | Scorecard:Binary-Artifacts | 5055:Security}` — Fix: add CycloneDX + Sigstore job; trade-off: marginal CI time increase; residual risk: dependency review accuracy.
2. **MCP audit gaps • High • Confidence: Medium • Evidence: `firecrawl_demo/interfaces/mcp/server.py` only enforces basic tool allowlist • Assets: MCP runtime** — `{SSDF:RV.4 | SAMM:Governance 1.2 | OWASP ASVS V2}` — Fix: implement audit log + plan→commit gating; trade-off: additional storage/ops overhead.
3. **Accessibility blind spot • Medium • Confidence: Low • Evidence: `app/` Streamlit UI lacks WCAG testing** — `{ISO 25010:Usability | WCAG 2.2 AA}` — Fix: run axe CI, create component checklist; trade-off: design bandwidth.

Log additional findings in Next_Steps as they arise.

### 4.3 Supply-Chain Posture

- Current level: SLSA 1 (scripted build). No SBOM/provenance/signatures yet.
- Actions: implement Scorecard workflow, CycloneDX export, Sigstore signing, dependency review gating, Renovate auto-PRs.
- Evidence log should capture SBOM & provenance artefact paths for each release.

### 4.4 Delivery, DX & UX

- DORA metrics captured manually; plan instrumentation via CI summary script outputs and Next_Steps tracking.
- SPACE baseline to derive from CLI telemetry & DevEx survey (quarterly cadence).
- UX/accessibility: adopt Nielsen heuristics review, axe CI scan, and include accessibility acceptance criteria in PR template.

### 4.5 PR-Ready Artefacts

- Candidate additions (to be implemented via follow-up PRs):
  - `.github/workflows/supply-chain.yml` — SBOM + signing pipeline.
  - `SECURITY.md` — threat model summary & vulnerability disclosure process.
  - `backstage/catalog-info.yaml` + `templates/` scaffolds.
  - `docs/adr/0003-threat-model-stride-mitre.md` — STRIDE, MITRE mappings, attack trees.
  - `app/tests/accessibility/` — axe/smoke scripts.

### 4.6 30/60/90 Roadmap

See Section 3.12 table; track execution in `Next_Steps.md` with owners, due dates, and quality gates.

### 4.7 Assumptions & Unknowns

- Deployment target undecided (Docker vs Kubernetes) — influences signing and secret distribution approach.
- Need confirmation on regulatory appetite for cloud-hosted evidence sinks vs on-prem storage.
- Clarify whether analysts require offline-only builds indefinitely or can opt into signed network adapters.
- Determine tolerance for introducing Backstage (org alignment, hosting).
- Identify owner for DevEx telemetry instrumentation.

Document answers as they arrive and update this playbook accordingly.

---

## 5. Applied Red‑Team Findings & Action Plan (v2025‑10‑18)

> The items below fold in the latest red‑team recommendations with **specific, testable actions**. Use these IDs in issues/PR titles. All actions are **feature‑flagged** where applicable and must prove reversibility.

> **2025-10-20 update:** WC‑05/06 controls are live. Plan→commit now mandates matching `*.plan`/`*.commit` artefacts with `If-Match` headers, RAG metrics, prompt-injection filtering, and JSONL audit logs for every write.

### 5.1 High‑Impact Actions (execute first)

|        ID | Description                                                                                                                                                                                | Owner    | Due | Dependencies | Acceptance / Quality Gates                                                                                              | Evidence / Artefacts                                                  | Links                                      |
| --------: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------- | --- | ------------ | ----------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- | ------------------------------------------ |
| **WC‑01** | **Secrets & PII purge**: rotate any credentials, remove `.env` and sensitive XLSX from history (git‑filter‑repo/BFG), enable GitHub Secret Scanning & push protection, add `.env.example`. | Security | TBC | None         | Git history free of `.env`/XLSX; all keys rotated and documented; Secret Scanning on; pushes with secrets are blocked.  | Rotation runbook; filter‑repo logs; GH Security settings screenshots. | ADR: Secrets Policy; Issue: Purge & Rotate |
| **WC‑02** | **Legal & disclosure**: add `LICENSE` (MIT/Apache‑2.0) and `SECURITY.md` with VDP and contact.                                                                                             | Platform | TBC | None         | Files present in `main`; VDP email tested; repo shows license metadata.                                                 | PR diff; test email receipt.                                          | Issue: Add License & VDP                   |
| **WC‑03** | **Robots & politeness (RFC 9309)**: per‑host queues, adaptive backoff, deny/allow lists; cache robots ≤24h; canonicalise URLs; trap detection (calendars/facets).                          | Crawler  | TBC | None         | Test corpus shows **0 violations**; trap FP rate <2%; performance unchanged ±10%.                                       | Compliance test suite; crawler logs; config samples.                  | ADR: Crawl Policy                          |
| **WC‑04** | **Boilerplate removal & dedupe**: integrate Trafilatura/jusText + SimHash/MinHash with thresholds and evaluation fixtures.                                                                 | Data     | TBC | WC‑03        | Boilerplate removal ≥90% on sample; dedupe precision ≥0.98, recall ≥0.90.                                               | Eval notebook; fixtures; CI job output.                               | Issue: Content Hygiene                     |
| **WC‑05** | **MCP plan→diff→commit**: all writes require `*.plan` then `*.commit` with `If‑Match`/ETag; deny‑by‑default tool allow‑list; audit log for each commit.                                    | Platform | TBC | WC‑02        | Negative tests prove 412 on stale; Copilot shows human‑readable diff; audit entry contains inputs, actor, ETag, result. | Tool schema; tests; sample audit log.                                 | ADR: MCP Write Safety                      |
| **WC‑06** | **LLM safety (OWASP Top‑10)**: implement prompt‑injection filters, typed args, output sanitisation; red‑team suite for LLM01/02/08.                                                        | Security | TBC | WC‑05        | Red‑team suite passes; no out‑of‑policy tool calls; sanitiser blocks scriptable payloads.                               | Test reports; policy docs.                                            | Threat Model + Tests                       |

### 5.2 Data Trust & Graph Semantics

|        ID | Description                                                                                                                                              | Owner      | Due | Dependencies | Acceptance / Quality Gates                                                                          | Evidence / Artefacts                                |
| --------: | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | --- | ------------ | --------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| **WC‑07** | **Data contracts before compute**: gate ingest/transform with Great Expectations, dbt tests, and/or Deequ; block publish on failure; generate Data Docs. | Data       | TBC | WC‑01        | 100% curated models covered by not‑null/unique/range/ref tests; failing checks block CI.            | GX suites; dbt tests; CI logs; Data Docs.           |
| **WC‑08** | **Lineage & catalogue**: emit OpenLineage for runs; attach PROV‑O per fact/edge; catalogue datasets with DCAT.                                           | Data       | TBC | WC‑07        | Each published fact resolves to runID + ≥1 PROV record; DCAT entries exist and are discoverable.    | Emitter config; PROV store; DCAT docs.              |
| **WC‑09** | **ACID tables + versioning**: store curated tables in Delta Lake or Iceberg; tag each run with DVC/lakeFS commit.                                        | Platform   | TBC | WC‑07        | Time‑travel restore proven; run reproducible from commit alone.                                     | Restore demo; commit IDs; runbook.                  |
| **WC‑10** | **Tabular→graph by spec**: define CSVW metadata; R2RML mappings (RML for non‑SQL); load to GQL‑ready graph; run PageRank/Louvain on rolling windows.     | Data       | TBC | WC‑08        | Mapping validation passes; post‑build checks on node/edge counts and degree distributions in range. | Mapping repo; validator output; graph check report. |
| **WC‑11** | **Profiling & drift**: instrument whylogs on each dataset/partition; thresholds + alerts wired.                                                          | Platform   | TBC | WC‑07        | Baselines captured; simulated drift triggers alert; promotion blocked on drift.                     | Profiles; alert runbook; dashboard.                 |
| **WC‑12** | **RAG/agent evaluation**: integrate Ragas metrics (faithfulness, context precision, tool‑use accuracy) as a promotion gate.                              | Governance | TBC | WC‑05, WC‑07 | Below‑threshold scores block "authoritative"; evaluation trace stored.                              | Ragas reports; CI gate.                             |

### 5.3 Supply‑Chain & Runtime Hardening

|        ID | Description                                                                                                                            | Owner        | Due | Dependencies | Acceptance / Quality Gates                                                              | Evidence / Artefacts                          |
| --------: | -------------------------------------------------------------------------------------------------------------------------------------- | ------------ | --- | ------------ | --------------------------------------------------------------------------------------- | --------------------------------------------- |
| **WC‑13** | **Harden Docker**: multi‑stage build; minimal base; `USER app:app`; read‑only FS; pinned digest; drop capabilities.                    | Platform     | TBC | None         | Container runs non‑root; image size reduced ≥30%; Hadolint clean; runtime immutable FS. | Dockerfile; SBOM; hadolint log.               |
| **WC‑14** | **SBOM & signing**: generate CycloneDX SBOM; sign wheels/sdists via Sigstore; emit in‑toto provenance; add OpenSSF Scorecard workflow. | Security     | TBC | WC‑13        | SBOM attached to releases; verified signatures in CI; Scorecard ≥7.                     | CI artefacts; attestations; Scorecard report. |
| **WC‑15** | **Repo & CI guards**: Semgrep/CodeQL, coverage ratchet, mutation testing pilot (≥40% modules).                                         | QA           | TBC | None         | CI blocks on critical findings; coverage ≥90%; mutation score ≥40% in pilot.            | CI logs; reports.                             |
| **WC‑16** | **Accessibility & UX**: run axe CI on Streamlit UI; heuristic review; add accessibility acceptance criteria to PR template.            | Product/UX   | TBC | None         | Axe smoke test wired into CI; heuristic report filed; PR template updated.              | CI logs; report; PR template diff.            |
| **WC‑17** | **Observability**: instrument OpenTelemetry traces for CLI; export metrics to Prometheus; define error budgets.                        | SRE          | TBC | None         | Traces visible; metrics dashboard; SLOs with alerts.                                    | OTel config; dashboard screenshot; SLO doc.   |
| **WC‑18** | **DevEx telemetry & tooling**: `justfile` for common tasks; CLI emits run timings; SPACE survey scheduled.                             | DevEx        | TBC | None         | Just targets pass locally/CI; telemetry captured; survey template published.            | `justfile`; metrics snapshot; survey doc.     |
| **WC‑19** | **Backstage TechDocs**: publish catalog entry and TechDocs sourced from MkDocs; template golden path.                                  | Platform     | TBC | None         | Backstage shows service with TechDocs; template can scaffold a new adapter.             | `catalog-info.yaml`; template repo.           |
| **WC‑20** | **Chaos & FMEA**: game‑day for adapters/secrets backend; maintain FMEA register linked to Next_Steps.                                  | SRE/Security | TBC | WC‑17        | Chaos drills pass rollback MTTR <30 min; FMEA updated.                                  | Game‑day report; FMEA doc.                    |

### 5.4 Standards Mapping (traceability)

- **WC‑01/02** → NIST SSDF PS.3, PW.1; OWASP SAMM Gov 1.2; POPIA compliance hygiene.
- **WC‑03/04** → RFC 9309; ethical crawling norms; ISO 25010 Reliability.
- **WC‑05/06** → OWASP LLM Top‑10 (LLM01/02/08); OWASP ASVS V2/V4.
- **WC‑07..12** → OpenLineage, W3C PROV‑O, W3C DCAT; Delta/Iceberg; FAIR; evaluability (Ragas/whylogs).
- **WC‑13..20** → SLSA L2, OpenSSF Scorecard, ISO 5055 (structural quality), DORA/SPACE observability.

> **Promotion policy**: An output may be marked **authoritative** only if WC‑07/08/09/11 are green for the referenced datasets **and** WC‑05/06/12 are green for the agent/tool path.
