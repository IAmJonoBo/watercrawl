---
title: Gap Analysis
---

## Current-State Findings

- **Tests**: Baseline pytest run failed because the legacy pipeline imported the `firecrawl` SDK directly, which is unavailable in the local environment.
- **Tooling**: `poetry run pre-commit` failed (`pre-commit` not installed); type checking raised missing stub errors; `bandit` highlighted blanket `except/pass` blocks and insecure RNG usage.
- **Architecture**: Core modules were monolithic, mixed sync/async concerns, and tightly coupled to Firecrawl specifics, complicating offline QA before the Crawlkit migration.
- **Data Quality**: Validation rules were implicit, with little test coverage around South African provincial constraints or evidence logging.
- **Automation**: No CLI or MCP layer existed, making orchestration manual.
- **Documentation**: README only described Firecrawl demos; no architectural or operations guidance existed.

## Target-State Objectives

1. **Modular pipeline** with injectable research adapters to support deterministic tests and future OSINT integrations.
2. **Strict validation** of provincial and status fields, with detailed issue reporting for analysts.
3. **Evidence-first enrichment** ensuring ≥2 sources (including an official/regulatory URL) and confidence scoring.
4. **Automation surface** exposing validation/enrichment as CLI commands and JSON-RPC (MCP) tasks.
5. **Documentation canon** capturing architecture, QA gates, and operational SOPs in MkDocs.
6. **Security & compliance hardening**: eliminate silent exception swallowing, normalise phones/emails, maintain audit logs.

## Remediation Status

- ✅ New validator, pipeline, CLI, and MCP server implemented with deterministic tests.
- ✅ MkDocs site scaffolded with architecture, data-quality, and operations content.
- ✅ Crawlkit fetch/distill/extract/orchestrate modules now replace the demo stack behind `FEATURE_ENABLE_CRAWLKIT`, with the optional Firecrawl SDK still gated by `FEATURE_ENABLE_FIRECRAWL_SDK`. Offline defaults remain the same.
- 🔄 Follow-up: replace placeholder `.env` credentials with secrets manager integration.
- ✅ Infrastructure planning module added to codify crawler, observability, and policy guardrails with environment-driven overrides.

## 2025-10-16 Audit Findings

- ❗ **Secrets manager dependencies missing** — `watercrawl.governance.secrets` expects `boto3` and Azure Key Vault libraries, but they are not declared in `pyproject.toml`, so the documented AWS/Azure backends cannot be activated without manual installs.
- ❗ **Evidence log guidance unenforced** — `docs/data-quality.md` promises remediation notes when evidence has fewer than two sources, yet `Pipeline._merge_sources`/`_compose_evidence_notes` never add those warnings, so analysts receive silent shortfalls.
- ❗ **Quickstart dataset absent** — README instructs running the CLI against `data/sample.csv`, but no sample file ships in `data/`, leaving newcomers without a runnable example.

## 2025-10-17 Hallucination & Rollback Audit

- ❗ **Crawler hallucination exposure** — enrichment accepted single-source findings with adapter confidence as low as 20%, allowing speculative directory entries to overwrite the spreadsheet with fabricated websites and contacts.
- ❗ **No structured rollback** — once low-quality values landed in the sheet there was no machine-readable rollback plan, leaving analysts to diff and revert rows manually.
- ❗ **Invisible quarantine state** — pipeline metrics did not expose how many rows were quarantined or rejected by analysts, obscuring pipeline health trends.

### Mitigations implemented

- ✅ Introduced a `QualityGate` that blocks updates lacking an official or second source, rejects low-confidence contact/website changes, and forces suspect rows back to `Needs Review` with detailed remediation notes.
- ✅ Surfaced `quality_rejections` and `quality_issues` metrics alongside a structured `RollbackPlan` so downstream automations and analysts can revert attempted updates deterministically.
- ✅ Extended CLI, MCP, and docs to broadcast the quality gate verdict, making hallucination rejections visible in both human and machine channels.

## 2025-10-18 Fresh Evidence Enforcement Audit

- ❗ **Legacy evidence loophole** — Rows with an existing official website could accept new contact details sourced from the same domain, letting speculative updates ride on stale corroboration.
- ✅ **Fresh-evidence enforcement** — The pipeline now separates legacy vs new evidence, blocks high-risk changes without fresh official corroboration, and records "fresh evidence" remediation guidance in rollback plans and evidence notes.
- ✅ **Documentation alignment** — Data-quality guidance now calls out the fresh-source requirement so analysts understand why stale evidence is rejected.

## 2025-10-17 Codex DX integration & QA verification

- ✅ **Baseline QA rerun** — `pytest`, `ruff`, `black`, `isort`, `mypy`, `bandit`, `dotenv-linter`, `dbt build`, and `poetry build` all pass against the current HEAD, confirming test, lint, type, security, contract, and packaging coverage remain intact after template consolidation.
- ✅ **Codex smoke tests scaffolded** — Promptfoo scenarios under `codex/evals/` target pipeline quality gates and compliance validators so Codex agents receive immediate feedback when proposals drift from policy.
- ✅ **MCP alignment** — Codex documentation now points to the in-repo MCP server, reinforcing reuse of the audited automation surface instead of bespoke tooling.
- 🔄 **Next step** — Extend Promptfoo coverage to include evidence-log remediation narratives once upcoming lineage tasks (AT-25/AT-27) land.
