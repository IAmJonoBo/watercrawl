---
applyTo: "**/tests/**"
---

# Python tests instructions

## Python tests (project-specific guidance)

When creating or updating tests under `tests/`:

- Run tests locally using Poetry: `poetry run pytest -q`
- Keep tests isolated and deterministic. Prefer fixtures and temporary filesystem (`tmp_path`) rather than touching global state.
- Use descriptive test names and include assertions that check both behavior and side effects (e.g., evidence logs, persisted files).
- Prefer parametrized tests for similar cases rather than duplicate test functions.
- If adding integration tests that require extra services (dbt/duckdb), include a minimal fixture or mark the test with pytest markers so CI can opt-in.

Acceptance criteria for test changes:
- Tests should run successfully under `poetry run pytest`.
- New tests should not rely on external network calls or secrets. If network calls are required, mock them.
