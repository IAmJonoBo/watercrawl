---
title: Data Contracts Reference
description: Schema specifications, validation rules, and quality contracts for Watercrawl datasets
---

# Data Contracts Reference

Watercrawl enforces data quality through dual validation layers using **Great Expectations** and **dbt** to ensure schema compliance, data integrity, and business rule enforcement.

## Overview

Data contracts define:

1. **Input/Output Schemas** - Column names, types, and order
2. **Validation Rules** - Not-null, format, and domain constraints
3. **Business Logic** - Cross-field validation and custom tests
4. **Quality Metrics** - Confidence scoring and completeness thresholds

## Schema Specification

### Curated Dataset Schema

The canonical output schema for enriched flight school datasets:

| Column                    | Type   | Required | Description                                    |
|---------------------------|--------|----------|------------------------------------------------|
| `Name of Organisation`    | String | Yes      | Canonical organisation name                    |
| `Province`                | String | Yes      | South African province (see allowed values)    |
| `Status`                  | String | Yes      | Lifecycle status (Active, Suspended, etc.)     |
| `Website URL`             | String | Yes      | Primary website (HTTPS required)               |
| `Contact Person`          | String | Yes      | Named contact person                           |
| `Contact Number`          | String | Yes      | E.164 format phone number (+27...)             |
| `Contact Email Address`   | String | Yes      | Contact email aligned with website domain      |
| `Confidence`              | Float  | Yes      | Confidence score (0.0-1.0) based on evidence   |

## Great Expectations Suite

Located at: `data_contracts/great_expectations/expectations/curated_dataset.json`

### Column Order Validation

```json
{
  "expectation_type": "expect_table_columns_to_match_ordered_list",
  "kwargs": {
    "column_list": [
      "Name of Organisation",
      "Province",
      "Status",
      "Website URL",
      "Contact Person",
      "Contact Number",
      "Contact Email Address",
      "Confidence"
    ]
  }
}
```

### Province Validation

Allowed values for the `Province` column:

- Eastern Cape
- Free State
- Gauteng
- KwaZulu-Natal
- Limpopo
- Mpumalanga
- Northern Cape
- North West
- Western Cape
- Unknown (when indeterminate)

```json
{
  "expectation_type": "expect_column_values_to_be_in_set",
  "kwargs": {
    "column": "Province",
    "value_set": ["Eastern Cape", "Free State", "Gauteng", "KwaZulu-Natal", "Limpopo", "Mpumalanga", "Northern Cape", "North West", "Western Cape", "Unknown"]
  }
}
```

### Not-Null Constraints

All columns are mandatory and must not contain null values:

```json
{
  "expectation_type": "expect_column_values_to_not_be_null",
  "kwargs": {
    "column": "Name of Organisation"
  }
}
```

## dbt Tests

Located at: `data_contracts/analytics/models/staging/stg_curated_dataset.yml`

### Generic Tests

#### HTTPS Prefix Validation

```sql
-- tests/generic/https_prefix.sql
-- Ensures website URLs use HTTPS protocol
{% test https_prefix(model, column_name) %}
    SELECT {{ column_name }}
    FROM {{ model }}
    WHERE {{ column_name }} IS NOT NULL
    AND LOWER({{ column_name }}) NOT LIKE 'https://%'
{% endtest %}
```

Usage:
```yaml
- name: website_url
  tests:
    - https_prefix
```

#### South African Phone Validation

```sql
-- tests/generic/south_african_phone.sql
-- Validates E.164 format for South African numbers
{% test south_african_phone(model, column_name) %}
    SELECT {{ column_name }}
    FROM {{ model }}
    WHERE {{ column_name }} IS NOT NULL
    AND NOT REGEXP_MATCHES({{ column_name }}, '^\+27[0-9]{9}$')
{% endtest %}
```

Usage:
```yaml
- name: contact_number
  tests:
    - south_african_phone
```

#### Email Domain Validation

```sql
-- tests/generic/email_domain_matches_website.sql
-- Ensures email domain aligns with organisation website
{% test email_domain_matches_website(model, column_name, website_column) %}
    SELECT 
        {{ column_name }} AS email,
        {{ website_column }} AS website
    FROM {{ model }}
    WHERE {{ column_name }} IS NOT NULL
    AND {{ website_column }} IS NOT NULL
    AND LOWER(SPLIT_PART({{ column_name }}, '@', 2)) 
        != LOWER(REGEXP_REPLACE({{ website_column }}, '^https?://(www\.)?', ''))
{% endtest %}
```

Usage:
```yaml
- name: contact_email_address
  tests:
    - email_domain_matches_website:
        arguments:
          website_column: website_url
```

### Accepted Values Tests

#### Province Values

```yaml
- name: province
  tests:
    - accepted_values:
        arguments:
          values: "{{contracts_province_values()}}"
```

Macro defined in `macros/contracts_shared.sql`:
```sql
{% macro contracts_province_values() %}
  ['Eastern Cape', 'Free State', 'Gauteng', 'KwaZulu-Natal', 
   'Limpopo', 'Mpumalanga', 'Northern Cape', 'North West', 
   'Western Cape', 'Unknown']
{% endmacro %}
```

#### Status Values

```yaml
- name: status
  tests:
    - accepted_values:
        arguments:
          values: "{{contracts_status_values()}}"
```

Macro defined in `macros/contracts_shared.sql`:
```sql
{% macro contracts_status_values() %}
  ['Active', 'Suspended', 'Closed', 'Unknown']
{% endmacro %}
```

### Minimum Confidence Threshold

```yaml
- name: confidence
  tests:
    - contracts_min_confidence
```

Custom test ensuring confidence scores meet minimum thresholds for data quality.

## Running Contracts

### Great Expectations

```bash
# Run Great Expectations validation
poetry run python -m apps.analyst.cli contracts data/curated.csv
```

### dbt Tests

```bash
# Navigate to dbt project
cd data_contracts/analytics

# Run all dbt tests
dbt test

# Run specific test
dbt test --select stg_curated_dataset

# Run only schema tests
dbt test --select test_type:schema
```

## Contract Coverage

The test suite includes contract coverage validation to ensure all columns are tested:

```python
# tests/test_contract_coverage.py
def test_all_columns_have_contracts():
    """Verify every output column has at least one validation rule."""
    required_columns = [
        "Name of Organisation",
        "Province", 
        "Status",
        "Website URL",
        "Contact Person",
        "Contact Number",
        "Contact Email Address",
        "Confidence"
    ]
    # ... validation logic
```

## CSVW & R2RML Metadata

Watercrawl supports W3C CSV on the Web (CSVW) annotations for semantic metadata:

```json
{
  "@context": "http://www.w3.org/ns/csvw",
  "dc:title": "Curated Flight School Dataset",
  "dc:description": "Validated and enriched flight school records",
  "tableSchema": {
    "columns": [
      {
        "name": "Name of Organisation",
        "titles": "Organisation Name",
        "datatype": "string",
        "required": true
      },
      {
        "name": "Province",
        "datatype": {"base": "string", "format": "Eastern Cape|Free State|..."},
        "required": true
      }
    ]
  }
}
```

### R2RML Mapping

For relational database mapping, Watercrawl provides R2RML templates for exporting to RDF knowledge graphs.

## Best Practices

### 1. Run Contracts Early and Often

```bash
# Before enrichment
poetry run python -m apps.analyst.cli contracts data/input.csv

# After enrichment
poetry run python -m apps.analyst.cli contracts data/enriched.csv
```

### 2. Version Your Expectations

- Store expectation suites in version control
- Use semantic versioning for breaking schema changes
- Document changes in `CHANGELOG.md`

### 3. Monitor Contract Failures

```bash
# Generate contract failure report
dbt test --store-failures

# View failures in database
SELECT * FROM dbt_test_failures;
```

### 4. Extend with Custom Tests

Add custom dbt tests for domain-specific validation:

```sql
-- tests/generic/valid_icao_code.sql
{% test valid_icao_code(model, column_name) %}
    SELECT {{ column_name }}
    FROM {{ model }}
    WHERE {{ column_name }} IS NOT NULL
    AND NOT REGEXP_MATCHES({{ column_name }}, '^[A-Z]{4}$')
{% endtest %}
```

## See Also

- [Configuration Reference](/reference/configuration/) - Environment variables and feature flags
- [Data Quality Guide](/data-quality/) - Research methodologies and validation strategies
- [CLI Commands](/cli/) - Running validation and enrichment pipelines
- [Architecture](/architecture/) - System design and component relationships

---

**Last Updated**: 2025-10-21  
**Contract Version**: 1.0.0
