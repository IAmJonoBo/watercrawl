# Contributing to Watercrawl

Welcome! Watercrawl is a frontier-standard toolkit for validating and enriching South African flight-school datasets with evidence-backed research and POPIA-compliant contact handling. We emphasize automation for analysts, GitHub Copilot integration via MCP, and rigorous quality gates to ensure compliance and reliability.

This guide outlines our conventions and standards. By contributing, you agree to uphold these frontier practices that prioritize evidence, compliance, and extensibility.

## Getting Started

### Prerequisites

- Python >=3.13,<3.15 (required for compatibility with our async and typing standards)
- The [`uv`](https://github.com/astral-sh/uv) toolchain manager
- Poetry for dependency management
- Git for version control

### Setup

1. Fork and clone the repository:

   ```bash
   git clone https://github.com/IAmJonoBo/watercrawl.git
   cd watercrawl
   ```

2. Provision the toolchain and install dependencies:

   ```bash
   python -m scripts.bootstrap_python --install-uv --poetry
   poetry install --no-root
   ```

3. Set up pre-commit hooks:

   ```bash
   poetry run pre-commit install
   ```

4. Run initial QA to verify your environment:

   ```bash
   poetry run python -m apps.automation.cli qa all
   ```

## Development Workflow

### Branching

- Use feature branches: `git checkout -b feature/your-feature-name`
- Follow semantic naming: `fix/`, `feat/`, `docs/`, `refactor/`, `test/`

### Commit Standards

- Use conventional commits: `type(scope): description`
- Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`
- Keep commits atomic and evidence-backed
- Reference issues: `fix(validation): handle edge case in province normalization (#123)`

### Pull Requests

- Open PRs against `main`
- Include evidence of testing and compliance checks
- Provide evidence log entries for data changes
- Ensure CI passes all quality gates
- Request review from domain experts for compliance-sensitive changes

## Code Standards

### Architecture Principles

We adhere to a layered, hexagonal architecture that separates concerns and enables extensibility:

- **Core** (`firecrawl_demo.core`): Configuration, utilities, constants
- **Domain** (`firecrawl_demo.domain`): Models, validation, compliance logic
- **Application** (`firecrawl_demo.application`): Orchestration, pipelines, interfaces
- **Integrations** (`firecrawl_demo.integrations`): Adapters, plugins, external systems
- **Infrastructure** (`firecrawl_demo.infrastructure`): Persistence, deployment concerns
- **Interfaces** (`firecrawl_demo.interfaces`): CLI, UI, MCP surfaces

### Coding Conventions

- **Python Version**: >=3.13,<3.15
- **Imports**: Use absolute imports; group by standard library, third-party, local
- **Naming**: snake_case for variables/functions, PascalCase for classes, UPPER_CASE for constants
- **Docstrings**: Use Google-style docstrings for all public APIs
- **Type Hints**: Mandatory for all new code; use `typing` module extensively
- **Async/Await**: Prefer async patterns for I/O operations

### Formatting & Linting

```toml
# pyproject.toml configuration
[tool.black]
line-length = 88
target-version = ["py311"]

[tool.ruff]
line-length = 88
target-version = "py311"
select = ["E", "F", "W"]
ignore = ["E203", "E501"]
```

- **Black**: Code formatting (88 char line length)
- **isort**: Import sorting with Black profile
- **Ruff**: Linting (E, F, W rules; ignore E203, E501)
- **Mypy**: Static type checking (strict mode)
- **Bandit**: Security linting (Python <3.14 until upstream restores support)
- **Yamllint**: YAML validation
- **SQLFluff**: SQL linting for dbt models (run under Python 3.13; see note below)
- **Pylint**: Optional advanced linting (`ENABLE_PYLINT=1` when using the problems collector)
- **Markdownlint**: Markdown style enforcement

> SQLFluff's dbt templater currently fails on Python 3.14 because of a transitively bundled `mashumaro` release. When linting SQL, install Python 3.13 (for example `uv python install 3.13.0`), switch the Poetry environment with `poetry env use 3.13`, run the SQLFluff command, and then return to the default interpreter via `poetry env use 3.14`.

> Streamlit and PyArrow ship in the optional Poetry dependency group `ui`. Default installs skip that group to keep Python 3.14 environments green; run `poetry install --with ui` from Python 3.12/3.13 when you need the analyst UI or Parquet exports.

> Delta Lake support is packaged in the optional `lakehouse` group. Combine it with the UI extras (`poetry install --with ui --with lakehouse`) when you need native Delta commits or time-travel restores; otherwise the writer falls back to filesystem snapshots.

Run all linters: `poetry run pre-commit run --all-files`

### Testing Standards

- **Framework**: pytest with coverage
- **Coverage**: 100% target for core modules
- **Types**: Unit, integration, property-based (Hypothesis)
- **Mocks**: Use pytest-mock for external dependencies
- **Async**: pytest-asyncio for async tests

```bash
# Run tests with coverage
poetry run pytest --cov=firecrawl_demo --cov-report=term-missing

# Run specific test categories
poetry run pytest -k "test_validation"
```

## Data Quality & Compliance

### Validation Rules

- **Provinces**: Must match canonical ACES list; unknown → "Unknown"
- **Status**: "Verified", "Candidate", "Needs Review", "Duplicate", "Do Not Contact (Compliance)"
- **Phones**: E.164 format (+27XXXXXXXXX)
- **Emails**: Must match organization domain; MX records required

### Enrichment Standards

- **Evidence Requirements**: ≥2 unique sources, ≥1 official/regulatory
- **Confidence Thresholds**: ≥70 for contact/website changes
- **Triangulation**: Cross-reference multiple adapters (Firecrawl, regulators, press, directories)
- **Status Promotion**: Website + named contact + valid phone/email → "Verified"

### Evidence Logging

All changes must be logged to `data/interim/evidence_log.csv`:

- RowID | Organisation | What changed | Sources | Notes | Timestamp | Confidence

```python
# Example evidence logging
from firecrawl_demo.infrastructure.evidence import EvidenceSink

sink = EvidenceSink()
await sink.log_evidence(
    row_id="123",
    organisation="Example Aero",
    change="Updated contact email",
    sources=["https://example.aero/contact", "https://regulator.gov.za"],
    notes="Verified via official website",
    confidence=85
)
```

### POPIA Compliance

- **Direct Marketing**: s69 restrictions apply; no unsolicited contact without consent
- **Data Minimization**: Collect only necessary data
- **Purpose Limitation**: Use data only for enrichment/validation
- **Accuracy**: Validate all contact data
- **Storage Security**: Encrypt sensitive data; use secrets provider
- **Retention**: Delete data when no longer needed

## Extensibility & Plugins

### Research Adapters

Implement `ResearchAdapter` protocol for new data sources:

```python
from firecrawl_demo.integrations.adapters.research import ResearchAdapter, ResearchFinding

class MyAdapter(ResearchAdapter):
    async def lookup(self, organisation: str, province: str) -> ResearchFinding | None:
        # Implementation with evidence-backed research
        return ResearchFinding(
            website="https://example.aero",
            contact_person="John Doe",
            contact_email="john@example.aero",
            sources=["https://official.source", "https://secondary.source"],
            confidence=90
        )

# Register in registry
from firecrawl_demo.integrations.adapters.research.registry import register_adapter
register_adapter("my-adapter", lambda ctx: MyAdapter())
```

### Integration Plugins

Use the plugin registry for adapters, telemetry, storage, contracts:

```python
from firecrawl_demo.integrations.integration_plugins import register_plugin

register_plugin("adapters", "my-adapter", {
    "factory": lambda: MyAdapter(),
    "feature_flag": "ENABLE_MY_ADAPTER",
    "health_probe": lambda: True
})
```

## Quality Gates & CI

### Automated Checks

- **Tests**: pytest with coverage
- **Linting**: Ruff, Black, isort, mypy, bandit
- **Security**: Bandit, safety
- **Contracts**: Great Expectations + dbt
- **Lineage**: OpenLineage, PROV-O, DCAT
- **Problems Report**: Aggregated QA findings in `problems_report.json`

### CI Pipeline

- Runs on push/PR to main
- Mirrors local QA: `poetry run python -m apps.automation.cli qa all`
- Generates artifacts: coverage.xml, problems_report.json, ci-summary.md
- Gates merges on all checks passing

### Local QA

```bash
# Full QA suite
poetry run python -m apps.automation.cli qa all

# Individual checks
poetry run python -m apps.automation.cli qa tests
poetry run python -m apps.automation.cli qa lint
poetry run python -m apps.automation.cli qa typecheck

# Problems report
poetry run python scripts/collect_problems.py
```

## Documentation Standards

### MkDocs

- Use `docs/` for all documentation
- Follow ADR pattern for architectural decisions
- Include code examples and CLI usage
- Update docs for any behavioral changes

### Code Documentation

- Docstrings for all public functions/classes
- Type hints for parameters/returns
- Comments for complex logic
- Update docstrings when changing behavior

## Security & Secrets

### Secrets Management

Use the secrets provider for secure configuration:

```python
from firecrawl_demo.governance.secrets import SecretsProvider

provider = SecretsProvider(backend="azure")  # or "env", "aws"
api_key = provider.get_secret("FIRECRAWL_API_KEY")
```

### Security Practices

- No hardcoded secrets
- Use environment variables or secure vaults
- Encrypt sensitive data at rest
- Validate inputs to prevent injection
- Run security scans: `poetry run bandit -r firecrawl_demo`

## Frontier Standards

Watercrawl embodies frontier standards in data enrichment:

- **Evidence-Backed**: Every change requires ≥2 sources, ≥1 official
- **Compliance-First**: POPIA s69, E.164, MX validation
- **Automated QA**: 100+ quality gates, aggregated reporting
- **Extensible Architecture**: Plugin registry, adapter protocols
- **Provenance Tracking**: OpenLineage, PROV-O, DCAT lineage
- **Lakehouse Ready**: Parquet snapshots with manifests
- **MCP Integration**: GitHub Copilot workflows
- **Infrastructure as Code**: Plan→commit contracts
- **Property-Based Testing**: Hypothesis for edge cases
- **Unit-Aware Data**: Pint for dimensional analysis

These standards ensure Watercrawl remains a gold standard for compliant, automated data enrichment in regulated industries.

## Getting Help

- **Issues**: Use GitHub issues for bugs/features
- **Discussions**: For questions and design discussions
- **Code of Conduct**: Be respectful and collaborative
- **Reviews**: All PRs require review; focus on evidence and compliance

Thank you for contributing to Watercrawl's frontier standards!
