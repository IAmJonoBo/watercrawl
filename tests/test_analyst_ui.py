import csv
from pathlib import Path

import pandas as pd

from firecrawl_demo.core import config as project_config
from firecrawl_demo.interfaces import analyst_ui


def test_loaders_use_configured_paths(monkeypatch, tmp_path):
    enriched_path = tmp_path / "enriched.xlsx"
    relationships_path = tmp_path / "relationships.csv"

    enriched_frame = pd.DataFrame(
        [
            {
                "Name of Organisation": "Atlas Flight School",
                "Province": "Gauteng",
                "Status": "Candidate",
            }
        ]
    )
    enriched_frame.to_excel(enriched_path, index=False)

    relationships_frame = pd.DataFrame(
        [{"source": "Atlas", "target": "Parent", "relationship": "subsidiary"}]
    )
    relationships_frame.to_csv(relationships_path, index=False)

    monkeypatch.setattr(project_config, "ENRICHED_XLSX", enriched_path)
    monkeypatch.setattr(project_config, "RELATIONSHIPS_CSV", relationships_path)

    loaded_enriched = analyst_ui.load_enriched_sheet()
    loaded_relationships = analyst_ui.load_relationships()

    pd.testing.assert_frame_equal(loaded_enriched, enriched_frame)
    pd.testing.assert_frame_equal(loaded_relationships, relationships_frame)


def test_main_updates_feedback_and_audit_log(monkeypatch, tmp_path):
    enriched_path = tmp_path / "enriched.xlsx"
    relationships_path = tmp_path / "relationships.csv"
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()

    base_frame = pd.DataFrame(
        [
            {
                "Name of Organisation": "Atlas Flight School",
                "Province": "Gauteng",
                "Status": "Candidate",
            }
        ]
    )
    base_frame.to_excel(enriched_path, index=False)

    pd.DataFrame([{"source": "Atlas", "target": "Parent"}]).to_csv(
        relationships_path, index=False
    )

    monkeypatch.setattr(project_config, "ENRICHED_XLSX", enriched_path)
    monkeypatch.setattr(project_config, "RELATIONSHIPS_CSV", relationships_path)
    monkeypatch.setattr(project_config, "PROCESSED_DIR", processed_dir)

    feedback_message = "Needs follow-up on fleet details"

    class FakeStreamlit:
        def __init__(self) -> None:
            self.titles: list[str] = []
            self.subheaders: list[str] = []
            self.frames: list[pd.DataFrame] = []
            self.success_messages: list[str] = []

        def title(self, text: str) -> None:
            self.titles.append(text)

        def subheader(self, text: str) -> None:
            self.subheaders.append(text)

        def dataframe(self, frame: pd.DataFrame) -> None:
            self.frames.append(frame.copy())

        def number_input(self, *_, **__) -> int:
            return 0

        def text_area(self, *_: object, **__: object) -> str:
            return feedback_message

        def button(self, *_: object, **__: object) -> bool:
            return True

        def success(self, message: str) -> None:
            self.success_messages.append(message)

    fake_st = FakeStreamlit()
    monkeypatch.setattr(analyst_ui, "st", fake_st)

    analyst_ui.main()

    updated_frame = pd.read_excel(enriched_path)
    assert updated_frame.at[0, "Analyst Feedback"] == feedback_message

    audit_path = Path(processed_dir) / "feedback_audit.csv"
    assert audit_path.exists()
    with audit_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[-1]["New"] == feedback_message
    assert fake_st.success_messages == ["Feedback saved and audit logged."]
