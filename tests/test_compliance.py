from __future__ import annotations

from datetime import datetime
from pathlib import Path

from firecrawl_demo import compliance
from firecrawl_demo import config as project_config
from firecrawl_demo.audit import CSVEvidenceSink
from firecrawl_demo.models import EvidenceRecord


def test_normalize_helpers_cover_edge_cases():
    assert compliance.normalize_province("gauteng") == "Gauteng"
    assert compliance.normalize_province(" ") == "Unknown"
    assert compliance.canonical_domain("https://www.example.org/path") == "example.org"
    assert compliance.canonical_domain(None) is None

    phone, issues = compliance.normalize_phone("011 555 0100")
    assert phone == "+27115550100"
    assert not issues

    invalid_phone, invalid_issues = compliance.normalize_phone("123")
    assert invalid_phone is None
    assert "E.164" in invalid_issues[0]


def test_validate_email_paths(monkeypatch):
    monkeypatch.setattr(compliance, "_check_mx_records", lambda _: None)
    cleaned, issues = compliance.validate_email(
        "Thandi.Nkosi@Example.org", "example.org"
    )
    assert cleaned == "thandi.nkosi@example.org"
    assert not issues

    monkeypatch.setattr(
        compliance,
        "_check_mx_records",
        lambda _: "MX lookup failed",
    )
    cleaned, issues = compliance.validate_email("support@other.org", "example.org")
    assert cleaned == "support@other.org"
    assert "Email domain does not match official domain" in issues
    assert any("MX" in issue for issue in issues)

    role_cleaned, role_issues = compliance.validate_email("info@example.org", None)
    assert role_cleaned == "info@example.org"
    assert any("Role inbox" in issue for issue in role_issues)

    missing, missing_issues = compliance.validate_email(None, None)
    assert missing is None
    assert missing_issues == ["Email missing"]

    invalid, invalid_issues = compliance.validate_email("not-an-email", None)
    assert invalid is None
    assert "Email format invalid" in invalid_issues


def test_check_mx_records_uses_resolver(monkeypatch):
    class DummyResolver:
        class NXDOMAIN(Exception):
            pass

        class NoAnswer(Exception):
            pass

        class Timeout(Exception):
            pass

        def __init__(self, answers: list[int]) -> None:
            self._answers = answers
            self.calls: list[tuple[str, str, float]] = []

        def resolve(self, domain: str, record_type: str, lifetime: float):
            self.calls.append((domain, record_type, lifetime))
            if domain == "missing.example":
                raise DummyResolver.NXDOMAIN()
            if domain == "empty.example":
                return []
            if domain == "timeout.example":
                raise DummyResolver.Timeout()
            return self._answers

    resolver = DummyResolver([1])
    monkeypatch.setattr(compliance, "dns_resolver", resolver)

    assert compliance._check_mx_records("example.org") is None
    assert compliance._check_mx_records("empty.example") == "No MX records found"
    assert (
        compliance._check_mx_records("missing.example") == "Domain has no DNS records"
    )
    assert compliance._check_mx_records("timeout.example") == "MX lookup failed"
    assert compliance._check_mx_records("") == "Missing email domain"


def test_status_and_confidence_decisions():
    assert compliance.determine_status(False, True, [], [], True) == "Needs Review"
    assert compliance.determine_status(True, True, ["issue"], [], True) == "Candidate"
    assert (
        compliance.determine_status(True, True, [], ["Role inbox used"], True)
        == "Candidate"
    )
    assert (
        compliance.determine_status(True, True, [], ["MX lookup failed"], True)
        == "Needs Review"
    )
    assert compliance.determine_status(True, False, [], [], True) == "Candidate"
    assert compliance.determine_status(True, True, [], [], True) == "Verified"

    assert (
        compliance.confidence_for_status("Verified", 2)
        == project_config.DEFAULT_CONFIDENCE_BY_STATUS["Verified"] - 10
    )
    assert compliance.confidence_for_status("Unknown", 10) == 20


def test_evidence_entry_and_append(monkeypatch, tmp_path):
    entry = compliance.evidence_entry(
        5,
        "Atlas",
        "Updated contact",
        ["https://www.caa.co.za/data", "https://archive.org/item"],
        "",
        80,
    )
    assert "Evidence shortfall" not in entry["Notes"]
    assert "Source may be stale" in entry["Notes"]

    shortfall_entry = compliance.evidence_entry(
        6,
        "Atlas",
        "Updated contact",
        ["https://example.org"],
        "Initial note",
        80,
    )
    assert "Evidence shortfall" in shortfall_entry["Notes"]

    evidence_log_path = tmp_path / "evidence.csv"
    monkeypatch.setattr(project_config, "EVIDENCE_LOG", evidence_log_path)

    recorded: list[list[EvidenceRecord]] = []

    class DummySink(CSVEvidenceSink):
        def __init__(self, path: Path) -> None:  # type: ignore[override]
            self.path = path

        def record(self, entries):  # type: ignore[override]
            recorded.append(list(entries))

    monkeypatch.setattr(compliance, "CSVEvidenceSink", lambda path: DummySink(path))

    compliance.append_evidence_log([entry, shortfall_entry])

    assert recorded and recorded[0][0].organisation == "Atlas"
    assert recorded[0][0].sources == [
        "https://www.caa.co.za/data",
        "https://archive.org/item",
    ]
    assert isinstance(recorded[0][0].timestamp, datetime)


def test_payload_hash_and_describe_changes():
    payload_a = {"alpha": 1, "beta": 2}
    payload_b = {"beta": 2, "alpha": 1}
    assert compliance.payload_hash(payload_a) == compliance.payload_hash(payload_b)

    original = {"Status": "Candidate", "Website URL": ""}
    enriched = {"Status": "Verified", "Website URL": "https://example.org"}
    assert (
        compliance.describe_changes(original, enriched)
        == "Status updated, Website URL updated"
    )
