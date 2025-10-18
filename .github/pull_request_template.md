## Summary

- [ ] What changed and why?
- [ ] Linked issues / ADRs

## Testing

- [ ] `poetry run pytest --maxfail=1 --disable-warnings --cov=firecrawl_demo --cov-report=term-missing`
- [ ] `poetry run ruff check .`
- [ ] `poetry run mypy .`
- [ ] `poetry run bandit -r firecrawl_demo`
- [ ] `poetry run pre-commit run --all-files`
- [ ] `poetry build`
- [ ] `poetry run dbt build --project-dir analytics --profiles-dir analytics --target ci --select tag:contracts --vars '{"curated_source_path": "data/sample.csv"}'`

## Quality Gates

- [ ] Coverage ≥ baseline
- [ ] No open TODOs / FIXMEs introduced
- [ ] `Next_Steps.md` updated with progress and risks
- [ ] Required CODEOWNERS requested

## Rollback Plan

- [ ] Describe how to revert if issues arise
