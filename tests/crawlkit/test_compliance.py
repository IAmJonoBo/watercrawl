from __future__ import annotations

from crawlkit.compliance.guard import ComplianceGuard


def test_compliance_guard_decisions(tmp_path):
    guard = ComplianceGuard(region="ZA", log_directory=tmp_path)
    decision = guard.decide_collection("business_email")
    assert decision.allowed is True
    assert "POPIA" in decision.reason

    personal = guard.decide_collection("personal_email")
    assert personal.allowed is False

    eu_guard = ComplianceGuard(region="EU", log_directory=tmp_path)
    eu_decision = eu_guard.decide_collection("business_email")
    assert eu_decision.allowed is True
    assert eu_decision.evidence


def test_compliance_guard_logs(tmp_path):
    guard = ComplianceGuard(region="US", log_directory=tmp_path)
    guard.log_provenance("https://example.com/privacy", "robots")
    log_file = tmp_path / "compliance.log"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8").strip()
    assert "robots" in content
