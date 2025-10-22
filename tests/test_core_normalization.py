import json
from pathlib import Path

import pandas as pd
import pytest

from firecrawl_demo.core import config
from firecrawl_demo.core.normalization import (
    ColumnNormalizationRegistry,
    build_default_registry,
)
from firecrawl_demo.core.profiles import ColumnDescriptor
from firecrawl_demo.domain.compliance import normalize_phone, validate_email


@pytest.fixture()
def registry() -> ColumnNormalizationRegistry:
    reg = build_default_registry(
        phone_normalizer=normalize_phone,
        email_validator=validate_email,
    )
    return reg


def test_registry_normalizes_contact_fields(registry: ColumnNormalizationRegistry) -> None:
    descriptor_phone = ColumnDescriptor(
        name="Contact Number",
        semantic_type="phone",
        required=True,
    )
    descriptor_email = ColumnDescriptor(
        name="Contact Email Address",
        semantic_type="email",
        required=False,
    )

    phone_series = pd.Series(["011 555 0100", "", None])
    email_series = pd.Series([
        "CONTACT@Example.org",
        "bad-email",
        None,
    ])

    phone_result = registry.normalize_series(descriptor_phone, phone_series)
    email_result = registry.normalize_series(descriptor_email, email_series)

    assert list(phone_result.series) == ["+27115550100", None, None]
    assert phone_result.diagnostics.issue_count == 2
    assert phone_result.diagnostics.format_issue_rate >= 1

    assert list(email_result.series) == ["contact@example.org", None, None]
    assert email_result.diagnostics.issue_count >= 2
    assert "Email format invalid" in email_result.diagnostics.issues


def test_registry_enforces_enum_and_units(registry: ColumnNormalizationRegistry) -> None:
    descriptor_province = ColumnDescriptor(
        name="Province",
        semantic_type="enum",
        allowed_values=("Gauteng", "Western Cape"),
        format_hints={"default": "Unknown"},
    )
    descriptor_metric = ColumnDescriptor(
        name="Runway Length",
        semantic_type="numeric_with_units",
    )

    registry.numeric_rules["Runway Length"] = {
        "canonical_unit": "meter",
        "allowed_units": {"meter", "metre", "m", "foot", "feet", "ft"},
        "cast": float,
    }

    province_series = pd.Series(["gauteng", "Unknown", "wc"])
    metric_series = pd.Series(["1200 m", "3950 ft", "invalid"])

    province_result = registry.normalize_series(descriptor_province, province_series)
    metric_result = registry.normalize_series(descriptor_metric, metric_series)

    assert list(province_result.series) == ["Gauteng", "Unknown", "Unknown"]
    assert province_result.diagnostics.issue_count == 2

    assert metric_result.series.iloc[0] == pytest.approx(1200.0)
    assert metric_result.series.iloc[1] == pytest.approx(1203.72, rel=1e-2)
    assert pd.isna(metric_result.series.iloc[2])
    assert metric_result.diagnostics.issue_count == 1


def test_read_dataset_applies_registry(tmp_path: Path, registry: ColumnNormalizationRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    dataset = pd.DataFrame(
        {
            "Contact Number": ["082 123 4567"],
            "Contact Email Address": ["Info@Example.org"],
            "Province": ["western cape"],
            "Runway Length": ["1500 m"],
        }
    )
    csv_path = tmp_path / "dataset.csv"
    dataset.to_csv(csv_path, index=False)

    descriptors = (
        ColumnDescriptor(name="Contact Number", semantic_type="phone"),
        ColumnDescriptor(name="Contact Email Address", semantic_type="email"),
        ColumnDescriptor(
            name="Province",
            semantic_type="enum",
            allowed_values=("Western Cape", "Gauteng"),
            format_hints={"default": "Unknown", "case": "title"},
        ),
        ColumnDescriptor(name="Runway Length", semantic_type="numeric_with_units"),
    )

    registry.numeric_rules["Runway Length"] = {
        "canonical_unit": "meter",
        "allowed_units": {"meter", "m"},
        "cast": float,
    }

    monkeypatch.setattr(config, "COLUMN_DESCRIPTORS", descriptors, raising=False)
    monkeypatch.setattr(config, "COLUMN_NORMALIZATION_REGISTRY", registry, raising=False)
    monkeypatch.setattr(config, "EXPECTED_COLUMNS", [d.name for d in descriptors], raising=False)
    monkeypatch.setattr(config, "INTERIM_DIR", tmp_path, raising=False)

    from firecrawl_demo.core.excel import read_dataset

    normalized = read_dataset(csv_path, registry=registry)

    assert normalized["Contact Number"].iloc[0] == "+27821234567"
    assert normalized["Contact Email Address"].iloc[0] == "info@example.org"
    assert normalized["Province"].iloc[0] == "Western Cape"
    assert normalized["Runway Length"].iloc[0] == pytest.approx(1500.0)

    report_path = tmp_path / "normalization_report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text())
    assert "Contact Number" in report
    assert report["Contact Number"]["semantic_type"] == "phone"
    assert report["Runway Length"]["issue_count"] == 0
