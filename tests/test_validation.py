import pandas as pd  # type: ignore[import-untyped]

from firecrawl_demo.validation import DatasetValidator


def test_validator_flags_missing_columns():
    df = pd.DataFrame(
        [
            {
                "Name of Organisation": "Aero Labs",
                "Province": "Gauteng",
            }
        ]
    )
    report = DatasetValidator().validate_dataframe(df)
    codes = {issue.code for issue in report.issues}
    assert "missing_column" in codes


def test_validator_detects_invalid_province():
    df = pd.DataFrame(
        [
            {
                "Name of Organisation": "Aero Labs",
                "Province": "Atlantis",
                "Status": "Candidate",
                "Website URL": "https://aerolabs.co.za",
                "Contact Person": "Jane Dlamini",
                "Contact Number": "+27 11 555 0101",
                "Contact Email Address": "hello@aerolabs.co.za",
            }
        ]
    )
    report = DatasetValidator().validate_dataframe(df)
    assert not report.is_valid
    assert report.issues[0].code == "invalid_province"
