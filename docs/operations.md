# Operations & Quality Gates

## Baseline Checks

Run these before changes (already automated in CI):

```bash
poetry run pytest --maxfail=1 --disable-warnings --cov=firecrawl_demo --cov-report=term-missing
poetry run ruff check .
poetry run mypy .
poetry run bandit -r firecrawl_demo
poetry run pre-commit run --all-files
poetry run poetry build
```

## Secrets Provisioning

The stack now resolves credentials and feature flags through `firecrawl_demo.secrets`.

1. Choose a backend by setting `SECRETS_BACKEND` to `env`, `aws`, or `azure`.
2. For local development (`env`), populate `.env` or OS environment variables as before.
3. For AWS Secrets Manager, provide `AWS_REGION`/`AWS_DEFAULT_REGION` and an optional `AWS_SECRETS_PREFIX` (for example `prod/firecrawl/`). Credentials follow the active AWS profile or IAM role.
4. For Azure Key Vault, set `AZURE_KEY_VAULT_URL` and optionally `AZURE_SECRETS_PREFIX`; authentication flows through `DefaultAzureCredential`, so ensure managed identity or service principal access.
5. Rotation is handled centrally; override any individual secret locally by exporting the variable in your shell or `.env`.

The toolchain includes first-party type stubs for `pandas` and `requests`, so remove per-file `type: ignore` directives instead
of silencing mypy regressions.

## Acceptance Criteria

| Gate            | Threshold/Expectation                                   |
|-----------------|----------------------------------------------------------|
| Tests           | 100% pass, coverage tracked via `pytest --cov`.          |
| Lint            | No Ruff violations; Black/Isort formatting clean.        |
| Types           | `mypy` success, including third-party stubs.             |
| Security        | No `bandit` High/Medium findings without mitigation.     |
| Evidence        | Every enriched row logged with ≥2 sources.               |
| Documentation   | MkDocs updated for any behavioural change.               |

## Evidence Sink Configuration

- `EVIDENCE_SINK_BACKEND`: choose `csv`, `stream`, or `csv+stream` to fan out.
- `EVIDENCE_STREAM_ENABLED`: toggle Kafka/REST emission when using the streaming stub.
- `EVIDENCE_STREAM_TRANSPORT`: `rest` (default) or `kafka` to switch log context.
- `EVIDENCE_STREAM_REST_ENDPOINT` / `EVIDENCE_STREAM_KAFKA_TOPIC`: document targets for future graph ingestion pipelines.

During enrichment the pipeline calls the configured `EvidenceSink`, so MCP tasks and CLI runs share the same audit trail plumbing. Use a mock sink in tests or dry runs to prevent filesystem writes.

## Incident Response

1. Re-run CLI `validate` to reproduce issue locally.
2. Capture context (input rows, evidence log snippets).
3. File `Risks/Notes` entry in `Next_Steps.md` and update MkDocs if the workflow changes.
4. Implement fix with tests-first discipline.

## Release Playbook

1. Run full QA suite.
2. Update `CHANGELOG.md` (to be introduced) with highlights.
3. Regenerate MkDocs (`mkdocs build`) and publish artefacts.
4. Tag release following SemVer once automation surfaces confirm green status.
