import asyncio
import json
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from click.testing import CliRunner

from firecrawl_demo.core.models import SchoolRecord
from firecrawl_demo.core.progress import PipelineProgressListener
from firecrawl_demo.interfaces import cli
from firecrawl_demo.interfaces.cli import cli as cli_group


def _write_sample_csv(path: Path, include_email: bool = False) -> None:
    base_row = {
        "Name of Organisation": "Aero Labs",
        "Province": "KwaZulu-Natal",
        "Status": "Candidate",
        "Website URL": "",
        "Contact Person": "",
        "Contact Number": "",
    }
    if include_email:
        base_row["Contact Email Address"] = "info@aerolabs.co.za"
    df = pd.DataFrame([base_row])
    df.to_csv(path, index=False)


def _make_record(name: str = "Atlas") -> SchoolRecord:
    return SchoolRecord.from_dataframe_row(
        pd.Series(
            {
                "Name of Organisation": name,
                "Province": "Gauteng",
                "Status": "Candidate",
                "Website URL": "https://example.org",
                "Contact Person": "Analyst",
                "Contact Number": "+27115550100",
                "Contact Email Address": "analyst@example.org",
            }
        )
    )


def test_cli_validate_reports_issues(tmp_path):
    input_path = tmp_path / "input.csv"
    _write_sample_csv(input_path, include_email=False)

    runner = CliRunner()
    result = runner.invoke(cli_group, ["validate", str(input_path), "--format", "json"])
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["rows"] == 1
    assert payload["issues"][0]["code"] == "missing_column"


def test_cli_enrich_creates_output(monkeypatch, tmp_path):
    input_path = tmp_path / "input.csv"
    output_path = tmp_path / "output.csv"
    _write_sample_csv(input_path, include_email=True)

    original_manager = cli.LineageManager
    monkeypatch.setattr(
        cli, "LineageManager", lambda: original_manager(artifact_root=tmp_path)
    )
    monkeypatch.setattr(cli, "build_lakehouse_writer", lambda: None)

    runner = CliRunner()
    result = runner.invoke(
        cli_group,
        [
            "enrich",
            str(input_path),
            "--output",
            str(output_path),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["rows_enriched"] == 1
    assert output_path.exists()
    assert "lineage_artifacts" in payload
    lineage_dir = Path(payload["lineage_artifacts"]["openlineage"]).parent
    assert lineage_dir.exists()


def test_cli_validate_text_mode_without_progress(tmp_path):
    input_path = tmp_path / "input.csv"
    _write_sample_csv(input_path, include_email=True)

    runner = CliRunner()
    result = runner.invoke(
        cli_group,
        ["validate", str(input_path), "--format", "text", "--no-progress"],
    )
    assert result.exit_code == 0
    assert "Rows:" in result.output


def test_resolve_progress_flag_behavior():
    assert cli._resolve_progress_flag("json", True) is True
    assert cli._resolve_progress_flag("json", None) is False
    assert cli._resolve_progress_flag("text", None) is True


def test_rich_pipeline_progress_tracks_updates(monkeypatch):
    events: dict[str, list[str]] = {"logs": [], "updates": []}

    class DummyProgress:
        def __init__(self, *args, **kwargs):
            self.started = False
            self._next_id = 1

        def start(self) -> None:
            self.started = True

        def add_task(self, description: str, total: int) -> int:
            events.setdefault("descriptions", []).append(description)
            events.setdefault("totals", []).append(str(total))
            task_id = self._next_id
            self._next_id += 1
            return task_id

        def advance(self, task_id: int, step: int) -> None:
            events.setdefault("advances", []).append(f"{task_id}:{step}")

        def update(self, task_id: int, *, description: str) -> None:
            events["updates"].append(description)

        def log(self, *parts: str) -> None:
            events["logs"].append("".join(parts))

        def stop(self) -> None:
            self.started = False

    monkeypatch.setattr(cli, "Progress", DummyProgress)

    listener = cli.RichPipelineProgress("Enriching dataset")
    listener.on_start(2)
    record = SchoolRecord(
        name="Atlas",
        province="Gauteng",
        status="Candidate",
        website_url=None,
        contact_person=None,
        contact_number=None,
        contact_email=None,
    )
    listener.on_row_processed(0, True, record)
    listener.on_error(RuntimeError("boom"), index=0)
    listener.on_complete({"adapter_failures": 1})

    assert events["updates"] == ["Updating Atlas"]
    assert any("adapter failures" in log for log in events["logs"])
    assert any("Adapter failure processing row 2" in log for log in events["logs"])


def test_rich_pipeline_progress_handles_duplicate_start(monkeypatch):
    class DummyProgress:
        def __init__(self, *args, **kwargs):
            self.start_calls = 0
            self.added: list[tuple[str, int]] = []
            self.advanced: list[int] = []
            self.logs: list[str] = []

        def start(self) -> None:
            self.start_calls += 1

        def add_task(self, description: str, total: int) -> int:
            self.added.append((description, total))
            return 1

        def advance(self, task_id: int, step: int) -> None:
            self.advanced.append(step)

        def stop(self) -> None:
            self.logs.append("stopped")

        def log(self, message: str) -> None:
            self.logs.append(message)

    monkeypatch.setattr(cli, "Progress", DummyProgress)

    listener = cli.RichPipelineProgress("Validating dataset")
    listener.on_row_processed(0, True, _make_record())
    listener.on_error(RuntimeError("boom"))
    listener.on_complete({})

    # First start initialises the progress task.
    listener.on_start(3)
    assert listener._started is True  # type: ignore[attr-defined]
    assert listener._task_id == 1  # type: ignore[attr-defined]

    # Subsequent starts should not restart the progress machinery.
    listener.on_start(10)
    assert listener._started is True  # type: ignore[attr-defined]

    listener.on_row_processed(0, False, _make_record())
    listener.on_complete({"adapter_failures": 0})

    dummy_progress: DummyProgress = listener._progress  # type: ignore[attr-defined]
    assert dummy_progress.start_calls == 1
    assert dummy_progress.added == [("Validating dataset", 3)]


def test_rich_pipeline_progress_logs_adapter_failures(monkeypatch):
    class DummyProgress:
        def __init__(self, *args, **kwargs):
            self.logs: list[str] = []

        def start(self) -> None:
            pass

        def add_task(self, description: str, total: int) -> int:
            return 1

        def advance(self, task_id: int, step: int) -> None:
            pass

        def update(self, task_id: int, *, description: str) -> None:
            pass

        def stop(self) -> None:
            pass

        def log(self, *parts: str) -> None:
            self.logs.append("".join(parts))

    monkeypatch.setattr(cli, "Progress", DummyProgress)

    listener = cli.RichPipelineProgress("Enriching dataset")
    listener.on_start(1)
    listener.on_complete({"adapter_failures": 2})
    dummy_progress: DummyProgress = listener._progress  # type: ignore[attr-defined]
    assert any("adapter failures" in log for log in dummy_progress.logs)


def test_mcp_server_stdio_invokes_async_loop(monkeypatch):
    runner = CliRunner()

    server_instances: list[object] = []

    class DummyServer:
        def __init__(self, pipeline):
            self.pipeline = pipeline
            self.called = False
            server_instances.append(self)

        async def serve_stdio(self):
            self.called = True

    def fake_pipeline(*_, **__):
        return "pipeline"

    def fake_sink():
        return "sink"

    async_calls: list[bool] = []

    def fake_run(coro):
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(coro)
        finally:
            loop.close()
        async_calls.append(True)
        return result

    monkeypatch.setattr(cli, "CopilotMCPServer", DummyServer)
    monkeypatch.setattr(cli, "Pipeline", fake_pipeline)
    monkeypatch.setattr(cli, "build_evidence_sink", fake_sink)
    monkeypatch.setattr(cli.asyncio, "run", fake_run)

    result = runner.invoke(cli_group, ["mcp-server"])
    assert result.exit_code == 0
    assert async_calls == [True]
    assert server_instances and server_instances[0].called is True


def test_mcp_server_rejects_non_stdio(monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(cli, "CopilotMCPServer", lambda pipeline: pipeline)
    monkeypatch.setattr(cli, "Pipeline", lambda *_, **__: "pipeline")
    monkeypatch.setattr(cli, "build_evidence_sink", lambda: "sink")

    result = runner.invoke(cli_group, ["mcp-server", "--no-stdio"])
    assert result.exit_code == 2
    assert "Only stdio transport" in result.output


def test_cli_validate_progress_path(monkeypatch, tmp_path):
    input_path = tmp_path / "input.csv"
    df = pd.DataFrame(
        [
            {
                "Name of Organisation": "Atlas",  # minimal columns for SchoolRecord
                "Province": "Gauteng",
                "Status": "Candidate",
            }
        ]
    )
    df.to_csv(input_path, index=False)

    class DummyIssue:
        def __init__(self) -> None:
            self.code = "missing_data"
            self.message = "Missing"
            self.column = "Website URL"

    class DummyReport:
        rows = 1
        is_valid = True
        issues = [DummyIssue()]

    class DummyValidator:
        def validate_dataframe(self, frame: pd.DataFrame) -> DummyReport:
            assert len(frame) == 1
            return DummyReport()

    class DummyPipeline:
        def __init__(self) -> None:
            self.validator = DummyValidator()

    class DummyProgressListener:
        def __init__(self, description: str) -> None:
            self.description = description
            self.start_calls: list[int] = []
            self.processed: list[tuple[int, bool, SchoolRecord]] = []
            self.completions: list[Mapping[str, int]] = []

        def on_start(self, total_rows: int) -> None:
            self.start_calls.append(total_rows)

        def on_row_processed(
            self, index: int, updated: bool, record: SchoolRecord
        ) -> None:
            self.processed.append((index, updated, record))

        def on_complete(self, metrics: Mapping[str, int]) -> None:
            self.completions.append(metrics)

    monkeypatch.setattr(cli, "Pipeline", DummyPipeline)
    monkeypatch.setattr(cli, "read_dataset", lambda path: df)
    monkeypatch.setattr(cli, "RichPipelineProgress", DummyProgressListener)

    runner = CliRunner()
    result = runner.invoke(
        cli_group,
        ["validate", str(input_path), "--format", "text", "--progress"],
    )

    assert result.exit_code == 0
    assert "Rows: 1" in result.output
    assert "missing_data" in result.output


def test_cli_enrich_warns_on_adapter_failures(monkeypatch, tmp_path):
    input_path = tmp_path / "input.csv"
    input_path.write_text("dummy", encoding="utf-8")

    class DummyReport:
        issues = []
        metrics = {
            "rows_total": 5,
            "enriched_rows": 3,
            "verified_rows": 2,
            "adapter_failures": 4,
        }
        lineage_artifacts = None
        lakehouse_manifest = None
        version_info = None

    class DummyProgress:
        def __init__(self, description: str) -> None:
            self.description = description
            self.started: list[int] = []
            self.completed: list[Mapping[str, int]] = []

        def on_start(self, total_rows: int) -> None:
            self.started.append(total_rows)

        def on_row_processed(
            self, index: int, updated: bool, record: SchoolRecord
        ) -> None:
            pass

        def on_complete(self, metrics: Mapping[str, int]) -> None:
            self.completed.append(metrics)

    class DummyPipeline:
        def __init__(self, **_: object) -> None:
            pass

        def run_file(
            self,
            path: Path,
            *,
            output_path: Path,
            progress: PipelineProgressListener | None,
            lineage_context: object | None = None,
        ) -> DummyReport:
            assert path == input_path
            output_path.write_text("data", encoding="utf-8")
            assert isinstance(progress, DummyProgress)
            progress.on_start(5)
            progress.on_complete(DummyReport.metrics)
            return DummyReport()

    monkeypatch.setattr(cli, "Pipeline", DummyPipeline)
    monkeypatch.setattr(cli, "build_evidence_sink", lambda: "sink")
    monkeypatch.setattr(
        cli,
        "LineageManager",
        lambda: SimpleNamespace(namespace="ns", job_name="job", dataset_name="dataset"),
    )
    monkeypatch.setattr(cli, "build_lakehouse_writer", lambda: None)
    monkeypatch.setattr(cli, "RichPipelineProgress", DummyProgress)

    runner = CliRunner()
    result = runner.invoke(cli_group, ["enrich", str(input_path)])

    assert result.exit_code == 0
    assert "Warnings: 4 research lookups failed" in result.output
