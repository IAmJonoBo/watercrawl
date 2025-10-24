import pytest
from watercrawl.domain.models import validation_report_to_contract
from watercrawl.domain.validation import DatasetValidator

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, strategies as st  # type: ignore  # noqa: E402

pd = pytest.importorskip("pandas")

BASE_ROW = {
    "Name of Organisation": "Aero Labs",
    "Province": "Gauteng",
    "Status": "Candidate",
    "Website URL": "https://aerolabs.co.za",
    "Contact Person": "Nomonde Jacobs",
    "Contact Number": "+27115550101",
    "Contact Email Address": "nomonde.jacobs@aerolabs.co.za",
}


def build_frame(*rows: dict[str, str]) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def extract_codes(report) -> set[str]:
    return {issue.code for issue in report.issues}


def test_contact_hygiene_flags_invalid_phone():
    frame = build_frame({**BASE_ROW, "Contact Number": "0115550101"})
    report = DatasetValidator().validate_dataframe(frame)
    assert "invalid_phone_format" in extract_codes(report)


def test_contact_hygiene_flags_email_domain_mismatch():
    frame = build_frame(
        {
            **BASE_ROW,
            "Website URL": "https://aerolabs.co.za",
            "Contact Email Address": "hello@otherdomain.co.za",
        }
    )
    report = DatasetValidator().validate_dataframe(frame)
    codes = extract_codes(report)
    assert "email_domain_mismatch" in codes
    contract = validation_report_to_contract(report)
    contract_codes = {issue.code for issue in contract.issues}
    assert "email_domain_mismatch" in contract_codes


def test_duplicate_detection_flags_repeated_rows():
    frame = build_frame(BASE_ROW, BASE_ROW)
    report = DatasetValidator().validate_dataframe(frame)
    codes = extract_codes(report)
    assert "duplicate_organisation" in codes
    assert "duplicate_contact" in codes
    assert "duplicate_contact_email" in codes


def test_multi_person_conflicts_surface_conflicting_roles_and_emails():
    frame = pd.DataFrame(
        [
            {
                **BASE_ROW,
                "Contact Role": "Head of Training",
            },
            {
                **BASE_ROW,
                "Contact Person": "Lerato Maseko",
                "Contact Email Address": "lerato.maseko@aerolabs.co.za",
                "Contact Role": "Chief Flight Instructor",
            },
        ]
    )
    report = DatasetValidator().validate_dataframe(frame)
    codes = extract_codes(report)
    assert "multiple_contacts" in codes
    assert "conflicting_contact_emails" in codes
    assert "conflicting_contact_roles" in codes


@given(
    labels=st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("Ll", "Nd")),
            min_size=3,
            max_size=12,
        ),
        min_size=2,
        max_size=2,
        unique=True,
    )
)
def test_email_domain_mismatch_property(labels):
    website_label, other_label = labels
    frame = build_frame(
        {
            **BASE_ROW,
            "Website URL": f"https://{website_label}.co.za",
            "Contact Email Address": f"team@{other_label}.co.za",
        }
    )
    report = DatasetValidator().validate_dataframe(frame)
    codes = extract_codes(report)
    assert "email_domain_mismatch" in codes
    contract = validation_report_to_contract(report)
    assert "email_domain_mismatch" in {issue.code for issue in contract.issues}
