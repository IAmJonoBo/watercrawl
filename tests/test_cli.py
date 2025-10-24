import asyncio
import json
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

pytest.importorskip("yaml")
pytest.importorskip("pandas")

import pandas as pd

from watercrawl.application.progress import PipelineProgressListener
from watercrawl.domain.contracts import (
    CONTRACT_VERSION,
    PipelineReportContract,
    ValidationIssueContract,
    ValidationReportContract,
)
from watercrawl.domain.models import PipelineReport, SchoolRecord, ValidationReport
from watercrawl.interfaces import cli
from watercrawl.interfaces.cli import cli as cli_group


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
    base_row.update(
        {
            "Fleet Size": "",
            "Runway Length": "",
            "Runway Length (m)": "",
        }
    )
    df = pd.DataFrame([base_row])
    df.to_csv(path, index=False)


def _write_plan(tmp_path: Path) -> Path:
    plan_path = tmp_path / "change.plan"
    plan_payload = {
        "changes": [
            {
                "field": "Website URL",
                "value": "https://www.aerolabs.co.za",
            }
        ],
        "instructions": "Promote verified website",
        "contract": {
            "name": "PlanArtifact",
            "version": CONTRACT_VERSION,
            "schema_uri": "https://watercrawl.acesaero.co.za/schemas/v1/plan-artifact",
        },
    }
    plan_path.write_text(json.dumps(plan_payload), encoding="utf-8")
    return plan_path


def _write_commit(tmp_path: Path) -> Path:
    commit_path = tmp_path / "change.commit"
    commit_payload = {
        "if_match": '"etag-aerolabs"',
        "diff_summary": "Website URL updated to https://www.aerolabs.co.za",
        "diff_format": "markdown",
        "rag": {
            "faithfulness": 0.92,
            "context_precision": 0.88,
            "answer_relevancy": 0.9,
        },
        "contract": {
            "name": "CommitArtifact",
            "version": CONTRACT_VERSION,
            "schema_uri": "https://watercrawl.acesaero.co.za/schemas/v1/commit-artifact",
        },
    }
    commit_path.write_text(json.dumps(commit_payload), encoding="utf-8")
    return commit_path


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
    metadata = payload["contracts"]["validation"]
    assert metadata["version"] == CONTRACT_VERSION
    assert metadata["schema_uri"].endswith("/validation-report")


def test_cli_enrich_creates_output(tmp_path):
    input_path = tmp_path / "input.csv"
    output_path = tmp_path / "output.csv"
    _write_sample_csv(input_path, include_email=True)
    plan_path = _write_plan(tmp_path)
    commit_path = _write_commit(tmp_path)

    original_manager = cli.LineageManager
    with cli.override_cli_dependencies(
        LineageManager=lambda: original_manager(artifact_root=tmp_path),
        build_lakehouse_writer=lambda: None,
    ):
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
                "--plan",
                str(plan_path),
                "--commit",
                str(commit_path),
            ],
        )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["rows_enriched"] == 1
    assert output_path.exists()
    assert "lineage_artifacts" in payload
    assert payload["commit_artifacts"] == [str(commit_path)]
    lineage_dir = Path(payload["lineage_artifacts"]["openlineage"]).parent
    assert lineage_dir.exists()
    pipeline_contract = payload["contracts"]["pipeline_report"]
    assert pipeline_contract["version"] == CONTRACT_VERSION
    assert pipeline_contract["schema_uri"].endswith("/pipeline-report")


def test_cli_enrich_requires_plan(tmp_path):
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
    assert result.exit_code != 0
    assert "requires at least one *.plan" in result.output


def test_cli_enrich_requires_commit(tmp_path):
    input_path = tmp_path / "input.csv"
    output_path = tmp_path / "output.csv"
    _write_sample_csv(input_path, include_email=True)
    plan_path = _write_plan(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli_group,
        [
            "enrich",
            str(input_path),
            "--output",
            str(output_path),
            "--plan",
            str(plan_path),
        ],
    )
    assert result.exit_code != 0
    assert "requires at least one *.commit" in result.output


def test_cli_enrich_logs_plan_audit(tmp_path, caplog):
    input_path = tmp_path / "input.csv"
    output_path = tmp_path / "output.csv"
    plan_path = _write_plan(tmp_path)
    commit_path = _write_commit(tmp_path)
    _write_sample_csv(input_path, include_email=True)

    with caplog.at_level("INFO", logger="watercrawl.plan_commit"):
        runner = CliRunner()
        result = runner.invoke(
            cli_group,
            [
                "enrich",
                str(input_path),
                "--output",
                str(output_path),
                "--plan",
                str(plan_path),
                "--commit",
                str(commit_path),
            ],
        )
    assert result.exit_code == 0
    assert "plan_commit.audit" in caplog.text
    assert str(plan_path) in caplog.text
    audit_path = cli.plan_guard.contract.audit_log_path
    assert audit_path.exists()
    last_record = json.loads(
        audit_path.read_text(encoding="utf-8").strip().splitlines()[-1]
    )
    assert last_record["allowed"] is True
    assert str(plan_path) in last_record["plans"]


def test_cli_enrich_supports_multi_inputs(tmp_path: Path) -> None:
    primary_path = tmp_path / "primary.csv"
    secondary_path = tmp_path / "secondary.xlsx"
    output_path = tmp_path / "merged.csv"
    plan_path = _write_plan(tmp_path)
    commit_path = _write_commit(tmp_path)

    pd.DataFrame([{"Name of Organisation": "Primary", "Province": "Gauteng"}]).to_csv(
        primary_path, index=False
    )
    with pd.ExcelWriter(secondary_path) as writer:
        pd.DataFrame(
            [{"Name of Organisation": "Secondary", "Province": "Limpopo"}]
        ).to_excel(writer, sheet_name="Custom", index=False)

    class DummyMultiSourcePipeline:
        def __init__(self) -> None:
            self.last_call: dict[str, object] | None = None

        def run_file(
            self,
            input_path: object,
            output_path: Path | None = None,
            *,
            progress: PipelineProgressListener | None = None,
            lineage_context: object | None = None,
            sheet_map: Mapping[str, str] | None = None,
        ) -> PipelineReport:
            self.last_call = {
                "input_path": input_path,
                "output_path": output_path,
                "sheet_map": sheet_map,
            }
            dataframe = pd.DataFrame(
                [
                    {
                        "Name of Organisation": "Merged",
                        "Province": "Gauteng",
                        "Status": "Candidate",
                        "Website URL": "",
                        "Contact Person": "",
                        "Contact Number": "",
                        "Contact Email Address": "",
                    }
                ]
            )
            return PipelineReport(
                refined_dataframe=dataframe,
                validation_report=ValidationReport(issues=[], rows=1),
                evidence_log=[],
                metrics={
                    "rows_total": 1,
                    "enriched_rows": 0,
                    "verified_rows": 0,
                    "adapter_failures": 0,
                },
            )

    class FailingPipeline:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("Base pipeline should not be instantiated")

    dummy = DummyMultiSourcePipeline()
    runner = CliRunner()
    with cli.override_cli_dependencies(
        Pipeline=FailingPipeline,
        MultiSourcePipeline=lambda **_: dummy,
        LineageManager=lambda: None,
        build_lakehouse_writer=lambda: None,
    ):
        result = runner.invoke(
            cli_group,
            [
                "enrich",
                str(primary_path),
                "--inputs",
                str(secondary_path),
                "--sheet-map",
                f"{secondary_path.name}=Custom",
                "--output",
                str(output_path),
                "--plan",
                str(plan_path),
                "--commit",
                str(commit_path),
                "--format",
                "json",
            ],
        )

    assert result.exit_code == 0
    assert dummy.last_call is not None
    assert isinstance(dummy.last_call["input_path"], list)
    assert dummy.last_call["sheet_map"] == {secondary_path.name: "Custom"}
    assert dummy.last_call["output_path"] == output_path


def test_cli_enrich_force_rejected_when_policy_disallows(tmp_path):
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
            "--force",
        ],
    )
    assert result.exit_code != 0
    assert "Force overrides are disabled" in result.output


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


def test_rich_pipeline_progress_tracks_updates():
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

    with cli.override_cli_dependencies(Progress=DummyProgress):
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


def test_rich_pipeline_progress_handles_duplicate_start() -> None:
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

    with cli.override_cli_dependencies(Progress=DummyProgress):
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

    dummy_progress: DummyProgress = listener._progress  # type: ignore[assignment,attr-defined]
    assert dummy_progress.start_calls == 1
    assert dummy_progress.added == [("Validating dataset", 3)]


def test_rich_pipeline_progress_logs_adapter_failures() -> None:
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

    with cli.override_cli_dependencies(Progress=DummyProgress):
        listener = cli.RichPipelineProgress("Enriching dataset")
        listener.on_start(1)
        listener.on_complete({"adapter_failures": 2})
        dummy_progress: DummyProgress = listener._progress  # type: ignore[assignment,attr-defined]
    assert any("adapter failures" in log for log in dummy_progress.logs)


def test_mcp_server_stdio_invokes_async_loop():
    runner = CliRunner()

    server_instances: list[object] = []

    class DummyServer:
        def __init__(self, pipeline, *, plan_guard, pipeline_builder):
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

    with cli.override_cli_dependencies(
        CopilotMCPServer=DummyServer,
        Pipeline=fake_pipeline,
        build_evidence_sink=fake_sink,
        asyncio_run=fake_run,
        plan_guard=cli.plan_guard,
    ):
        result = runner.invoke(cli_group, ["mcp-server"])
    assert result.exit_code == 0
    assert async_calls == [True]
    assert server_instances and server_instances[0].called is True


def test_mcp_server_rejects_non_stdio():
    runner = CliRunner()
    with cli.override_cli_dependencies(
        CopilotMCPServer=lambda pipeline, *, plan_guard, pipeline_builder: pipeline,
        Pipeline=lambda *_, **__: "pipeline",
        build_evidence_sink=lambda: "sink",
        plan_guard=cli.plan_guard,
    ):
        result = runner.invoke(cli_group, ["mcp-server", "--no-stdio"])
    assert result.exit_code == 2
    assert "Only stdio transport" in result.output


def test_cli_validate_progress_path(tmp_path):
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

        def to_contract(self) -> ValidationReportContract:
            return ValidationReportContract(
                issues=[
                    ValidationIssueContract(
                        code=issue.code,
                        message=issue.message,
                        column=issue.column,
                        row=None,
                    )
                    for issue in self.issues
                ],
                rows=self.rows,
            )

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

    def _dummy_read_dataset(_path, **kwargs):
        assert "sheet_map" not in kwargs or kwargs["sheet_map"] is None
        return df

    with cli.override_cli_dependencies(
        Pipeline=DummyPipeline,
        read_dataset=_dummy_read_dataset,
        RichPipelineProgress=DummyProgressListener,
    ):
        runner = CliRunner()
        result = runner.invoke(
            cli_group,
            ["validate", str(input_path), "--format", "text", "--progress"],
        )

    assert result.exit_code == 0
    assert "Rows: 1" in result.output
    assert "missing_data" in result.output


def test_cli_validate_emits_inference_preview(tmp_path):
    input_path = tmp_path / "input.csv"
    input_path.write_text("dummy", encoding="utf-8")

    df = pd.DataFrame({"Name": ["A"]})
    df.attrs["column_inference"] = {
        "matches": [
            {
                "source": "Org Name",
                "canonical": "Name of Organisation",
                "score": 0.82,
                "reasons": ["Synonym match"],
            }
        ],
        "unmatched_sources": [],
        "missing_targets": [],
        "rename_map": {"Org Name": "Name of Organisation"},
    }

    class DummyReport:
        rows = 1
        issues: list[dict[str, str]] = []
        is_valid = True

        def to_contract(self) -> ValidationReportContract:
            return ValidationReportContract(issues=[], rows=1)

    class DummyValidator:
        def validate_dataframe(self, frame: pd.DataFrame) -> DummyReport:
            assert frame is df
            return DummyReport()

    class DummyPipeline:
        def __init__(self) -> None:
            self.validator = DummyValidator()

    def _dummy_read_dataset(path: Path | list[Path], **kwargs):
        return df

    with cli.override_cli_dependencies(
        Pipeline=DummyPipeline,
        read_dataset=_dummy_read_dataset,
    ):
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(
            cli_group,
            ["validate", str(input_path), "--format", "json"],
        )

    assert result.exit_code == 0
    assert "Inferred column mappings" in result.stderr
    assert "Org Name → Name of Organisation" in result.stderr


def test_cli_enrich_warns_on_adapter_failures(tmp_path):
    input_path = tmp_path / "input.csv"
    input_path.write_text("dummy", encoding="utf-8")
    plan_path = _write_plan(tmp_path)

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

        def to_contract(self) -> PipelineReportContract:
            return PipelineReportContract(
                validation_report=ValidationReportContract(issues=[], rows=5),
                evidence_log=[],
                metrics=self.metrics,
            )

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
            **_: object,
        ) -> DummyReport:
            assert path == input_path
            output_path.write_text("data", encoding="utf-8")
            assert isinstance(progress, DummyProgress)
            progress.on_start(5)
            progress.on_complete(DummyReport.metrics)
            return DummyReport()

    with cli.override_cli_dependencies(
        Pipeline=DummyPipeline,
        build_evidence_sink=lambda: "sink",
        LineageManager=lambda: SimpleNamespace(
            namespace="ns", job_name="job", dataset_name="dataset"
        ),
        build_lakehouse_writer=lambda: None,
        RichPipelineProgress=DummyProgress,
        plan_guard=cli.plan_guard,
    ):
        runner = CliRunner()
        result = runner.invoke(
            cli_group,
            [
                "enrich",
                str(input_path),
                "--plan",
                str(plan_path),
                "--commit",
                str(_write_commit(tmp_path)),
            ],
        )

    assert result.exit_code == 0
    assert "Warnings: 4 research lookups failed" in result.output
