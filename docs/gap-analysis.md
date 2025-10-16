# Gap Analysis

## Current-State Findings

- **Tests**: Baseline pytest run failed because the legacy pipeline imported the `firecrawl` SDK directly, which is unavailable in the local environment.
- **Tooling**: `poetry run pre-commit` failed (`pre-commit` not installed); type checking raised missing stub errors; `bandit` highlighted blanket `except/pass` blocks and insecure RNG usage.
- **Architecture**: Core modules were monolithic, mixed sync/async concerns, and tightly coupled to Firecrawl specifics, complicating offline QA.
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
- ✅ Firecrawl SDK integration available behind feature toggles with offline-safe defaults and type stubs for pandas/requests.
- 🔄 Follow-up: replace placeholder `.env` credentials with secrets manager integration.
- ✅ Infrastructure planning module added to codify crawler, observability, and policy guardrails with environment-driven overrides.

## 2025-10-16 Audit Findings

- ❗ **Secrets manager dependencies missing** — `firecrawl_demo.secrets` expects `boto3` and Azure Key Vault libraries, but they are not declared in `pyproject.toml`, so the documented AWS/Azure backends cannot be activated without manual installs.
- ❗ **Evidence log guidance unenforced** — `docs/data-quality.md` promises remediation notes when evidence has fewer than two sources, yet `Pipeline._merge_sources`/`_compose_evidence_notes` never add those warnings, so analysts receive silent shortfalls.
- ❗ **Quickstart dataset absent** — README instructs running the CLI against `data/sample.csv`, but no sample file ships in `data/`, leaving newcomers without a runnable example.
