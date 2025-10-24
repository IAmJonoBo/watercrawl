# Data Normalisation Framework

The enrichment pipeline now routes all inbound datasets through a declarative
normalisation registry. Column intents are described in the tenant refinement
profile (`profiles/<tenant>.yaml`) under `dataset.columns`. Each column entry
specifies the semantic type, whether the field is required, optional format
hints, and (for enumerations) the allowed values.

## Declaring column intents

```yaml
# profiles/example_tenant.yaml
id: example-tenant
name: Example Tenant
# …
dataset:
  expected_columns:
    - Organisation Name
    - Website URL
    - Contact Email
  columns:
    - name: Organisation Name
      type: text
      format_hints:
        case: title
        collapse_whitespace: true
    - name: Website URL
      type: url
      format_hints:
        ensure_https: true
        strip_query: true
    - name: Contact Email
      type: email
      required: true
      format_hints:
        case: lower
    - name: Province
      type: enum
      allowed_values: [Eastern Cape, Western Cape, Gauteng]
      format_hints:
        default: Unknown
    - name: Fleet Size
      type: numeric_with_units
```

Supported semantic types:

| Type                 | Behaviour                                                                |
| -------------------- | ------------------------------------------------------------------------- |
| `text`               | Trims whitespace, applies optional casing hints (title/upper/lower).      |
| `address`            | Title-cases and collapses whitespace, keeping punctuation.                |
| `phone`              | Uses the profile’s phone rules and `normalize_phone` for E.164 output.    |
| `email`              | Validates format, lower-cases, and reuses `validate_email` for MX checks. |
| `url`                | Normalises scheme/host casing, strips query/fragment if configured.       |
| `enum`               | Coerces to the canonical value; invalid entries fall back to defaults.    |
| `numeric`            | Casts to `float` (or `int` when `format_hints.cast: int`).                 |
| `numeric_with_units` | Parses unit expressions and converts to the configured canonical unit.    |
| `date`               | Parses according to `input_formats` hints and emits ISO strings.          |

Every column that requires units must also declare a `numeric_units` rule with
its canonical unit and allowed synonyms. The registry automatically keeps those
in sync and raises when unsupported units appear.

## Customising format hints

Each column can provide additional hints:

* `case`: `title`, `upper`, or `lower`
* `collapse_whitespace`: collapse multiple spaces into a single space (default `true`)
* `default`: fallback value for enums when input data is missing/invalid
* `ensure_https`: upgrade URL schemes to `https`
* `strip_query` / `strip_fragment` / `strip_trailing_slash`
* `input_formats`: array of `datetime.strptime` patterns for dates
* `output_format`: target format string for dates (default ISO-8601)

## Diagnostics

The loader writes per-column statistics to
`data/interim/normalization_report.json` when declarative columns are
configured. Each entry captures:

* `null_rate` and `null_count`
* `unique_count`
* `issue_count` and frequency per issue message
* `format_issue_rate` — share of non-null rows that required correction

These diagnostics give auditors a fast way to spot regressions or sources that
no longer match the expected schema.

## Recommended canonical schemas

For new tenants, start with the following guidelines:

* **Phones** — mark contact numbers as `phone` and keep `required: true` when
the enrichment workflow treats missing phones as blockers.
* **Emails** — add `format_hints.case: lower` to guarantee consistent casing.
* **URLs** — enable `ensure_https` and `strip_query` to remove tracking
parameters before evidence logging.
* **Enumerations** — capture the canonical values under
`dataset.columns[].allowed_values` and mirror them in the profile’s
`statuses.allowed` or `geography.provinces` sections. Use `format_hints.default`
for “Unknown” style fallbacks.
* **Numeric metrics** — declare a `numeric_with_units` column and add a matching
entry under `numeric_units` with the canonical unit (`meter`, `count`, etc.).

When a white-label deployment introduces extra metrics, extend
`dataset.columns` with the new column name, pick the appropriate semantic type,
and provide any custom hints. The registry will automatically pick up the new
intent without modifying code in `watercrawl/core/excel.py`.
