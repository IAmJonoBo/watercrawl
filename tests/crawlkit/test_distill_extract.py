from __future__ import annotations

from pathlib import Path

from crawlkit.distill.distill import distill
from crawlkit.extract.entities import extract_entities

FIXTURE = Path(__file__).parent / "fixtures" / "sample.html"


def test_distill_generates_markdown():
    html = FIXTURE.read_text(encoding="utf-8")
    doc = distill(html, "https://acesaero.co.za")
    assert "# ACES Aerodynamics Research" in doc.markdown
    assert doc.meta["profile"] == "article"
    assert doc.meta["title"] == "ACES Aero"
    assert doc.microdata["json_ld"]


def test_extract_entities_from_distilled_doc():
    html = FIXTURE.read_text(encoding="utf-8")
    doc = distill(html, "https://acesaero.co.za")
    entities = extract_entities(doc)
    emails = {entry["address"] for entry in entities.emails}
    assert "info@acesaero.co.za" in emails
    assert any("Jane" in person["name"] for person in entities.people)
    assert entities.org["name"] == "ACES Aerodynamics"
