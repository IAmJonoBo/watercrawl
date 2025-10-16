import asyncio
import json
from pathlib import Path

import pandas as pd
from click.testing import CliRunner

from firecrawl_demo import cli
from firecrawl_demo.cli import cli as cli_group
from firecrawl_demo.models import SchoolRecord


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


def test_cli_validate_reports_issues(tmp_path):
    input_path = tmp_path / "input.csv"
    _write_sample_csv(input_path, include_email=False)

    runner = CliRunner()
    result = runner.invoke(cli_group, ["validate", str(input_path), "--format", "json"])
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["rows"] == 1
    assert payload["issues"][0]["code"] == "missing_column"


def test_cli_enrich_creates_output(tmp_path):
    input_path = tmp_path / "input.csv"
    output_path = tmp_path / "output.csv"
    _write_sample_csv(input_path, include_email=True)

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
