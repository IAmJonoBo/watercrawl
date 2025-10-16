# Data Quality & Research Methodology

## Validation Rules

- **Provinces**: Must match ACES canonical list (`config.PROVINCES`). Unknown or blank values are normalised to `Unknown` and flagged.
- **Status**: One of `Verified`, `Candidate`, `Needs Review`, `Duplicate`, or `Do Not Contact (Compliance)`. Empty or unrecognised statuses trigger actionable validation issues.
- **Phones**: Converted to `+27XXXXXXXXX`. Numbers that cannot be normalised generate issues recorded against the row.
- **Emails**: Must match the organisation domain. MX checks are performed when DNS tooling is available; otherwise a soft warning is recorded.

## Enrichment Heuristics

1. **Website discovery**: Prefer research adapter findings; fall back to existing row data.
2. **Contact inference**: Named contacts supplied by adapters override blanks. Role inboxes downgrade status to `Candidate`.
3. **Triangulation**: The default adapter cross-references Firecrawl (when enabled), regulator registries, press coverage, and professional directories. Offline runs log follow-up instructions instead of performing live lookups.
4. **Evidence sourcing**: Merge the organisation website with adapter-provided URLs. If fewer than two sources are available, evidence notes carry a remediation instruction.
5. **Status promotion**: Rows with website, named contact, valid phone, and domain-aligned email become `Verified`; otherwise `Candidate` or `Needs Review` based on defect severity.
6. **Rename detection**: When a new website domain or alias is discovered, the pipeline logs an investigation note encouraging analysts to confirm potential ownership changes.

## Research Adapter Guidance

- Build adapters that return `ResearchFinding` objects with:
  - `sources`: ≥2 URLs, one official/regulatory where possible.
  - `notes`: Concise justification of the enrichment decision.
  - `confidence`: Integer 0–100 reflecting evidence strength.
- Keep adapters stateless; persist caching or rate limiting externally.
- Add new adapters under `firecrawl_demo.research` or compose them within the pipeline factory.
