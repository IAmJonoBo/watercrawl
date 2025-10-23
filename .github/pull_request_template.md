## Summary

- [ ] What changed and why?
- [ ] Linked issues / ADRs

## Testing

- [ ] `poetry run pytest --maxfail=1 --disable-warnings --cov=watercrawl --cov-report=term-missing`
- [ ] `poetry run ruff check .`
- [ ] `poetry run mypy .`
- [ ] `poetry run bandit -r watercrawl`
- [ ] `poetry run pre-commit run --all-files`
- [ ] `poetry build`
- [ ] `poetry run dbt build --project-dir analytics --profiles-dir analytics --target ci --select tag:contracts --vars '{"curated_source_path": "data/sample.csv"}'`
- [ ] `poetry run python apps/analyst/accessibility/axe_smoke.py`

## Quality Gates

- [ ] Coverage ≥ baseline
- [ ] No open TODOs / FIXMEs introduced
- [ ] `Next_Steps.md` updated with progress and risks
- [ ] Required CODEOWNERS requested

## Rollback Plan

- [ ] Describe how to revert if issues arise
