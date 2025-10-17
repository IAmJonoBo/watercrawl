import csv
from pathlib import Path

from firecrawl_demo.core.audit import CSVEvidenceSink
from firecrawl_demo.core.models import EvidenceRecord


def test_csv_evidence_sink_appends(tmp_path: Path) -> None:
    path = tmp_path / "evidence.csv"
    sink = CSVEvidenceSink(path=path)

    # Should not create file when no entries are provided.
    sink.record([])
    assert not path.exists()

    entries = [
        EvidenceRecord(
            row_id=2,
            organisation="Test Org",
            changes="Website URL -> https://example.org",
            sources=["https://example.org", "https://regulator.gov.za"],
            notes="Sample note",
            confidence=80,
        ),
        EvidenceRecord(
            row_id=3,
            organisation="Another Org",
            changes="Contact Person -> Jane",
            sources=["https://another.org", "https://caa.co.za"],
            notes="",  # empty notes should serialize as blank string
            confidence=70,
        ),
    ]

    sink.record(entries)

    assert path.exists()
    with path.open("r", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    assert len(rows) == 2
    first, second = rows
    assert first["RowID"] == "2"
    assert first["Organisation"] == "Test Org"
    assert first["Sources"].count("https://") == 2
    assert second["RowID"] == "3"
    assert second["Notes"] == ""
    assert second["Sources"].endswith("caa.co.za")
