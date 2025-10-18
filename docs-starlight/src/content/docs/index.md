---
title: ACES Aerodynamics Enrichment Stack
---

Welcome to the consolidated intelligence and enrichment toolkit for ACES Aerodynamics. This stack transforms raw flight-school datasets into fully validated, evidence-backed records aligned with POPIA and SACAA expectations.

## Overview

The ACES Enrichment Stack is a modular, compliance-driven pipeline for B2B data enrichment and OSINT research focused on South African flight schools. Built with Python 3.13, it leverages modern tools like Poetry for dependency management, dbt for data transformation, Great Expectations for data quality, and MCP for AI-assisted workflows.

## Key Features

- **Data Validation & Normalization**: Robust validation for South African provinces, contacts, and status fields with unit conversions using Pint.
- **Enrichment Pipeline**: Deterministic enrichment flows using research adapters, triangulated intelligence from regulators, press, and directories.
- **Data Quality Contracts**: Dual Great Expectations + dbt suite for automated sanity checks and evidence logging.
- **Lineage & Lakehouse**: OpenLineage, PROV-O, and DCAT artifacts for provenance tracking and reproducible datasets.
- **CLI & MCP Integration**: Command-line interface and Model Context Protocol server for analyst workflows and GitHub Copilot automation.
- **Infrastructure Planning**: Codified guardrails for crawler deployment, observability, and policy compliance.

## Quick Start

1. **Prerequisites**: Python >=3.13,<3.14
2. **Install**: `pip install poetry` then `poetry install`
3. **Run**: `poetry run python -m app.cli overview`

See the [CLI documentation](cli.md) for detailed commands.

## Architecture

The stack follows a layered architecture with core business logic, integrations, governance, and interfaces. Key components include:

- `firecrawl_demo/core/`: Validation, pipeline orchestration, and models
- `firecrawl_demo/integrations/`: Research adapters, lineage, and lakehouse
- `analytics/`: dbt project for data contracts
- `great_expectations/`: Data quality suites

For detailed architecture, see [Architecture](architecture.md).

## Documentation Structure

- [Gap Analysis](gap-analysis.md): Current vs. target state
- [Architecture](architecture.md): System design and components
- [CLI](cli.md): Command usage and examples
- [Data Quality](data-quality.md): Validation and contracts
- [Operations](operations.md): Deployment and maintenance
- [MCP](mcp.md): AI integration contract
- [Lineage Lakehouse](lineage-lakehouse.md): Data provenance

Use the navigation sidebar to explore these sections.
