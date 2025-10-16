# Operations & Quality Gates

## Baseline Checks

Run these before changes (already automated in CI):

```bash
poetry run pytest --maxfail=1 --disable-warnings --cov=firecrawl_demo --cov-report=term-missing
poetry run ruff check .
poetry run mypy .
poetry run bandit -r firecrawl_demo
poetry run poetry build
```

## Acceptance Criteria

| Gate            | Threshold/Expectation                                   |
|-----------------|----------------------------------------------------------|
| Tests           | 100% pass, coverage tracked via `pytest --cov`.          |
| Lint            | No Ruff violations; Black/Isort formatting clean.        |
| Types           | `mypy` success, including third-party stubs.             |
| Security        | No `bandit` High/Medium findings without mitigation.     |
| Evidence        | Every enriched row logged with ≥2 sources.               |
| Documentation   | MkDocs updated for any behavioural change.               |

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
