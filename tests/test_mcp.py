from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from firecrawl_demo.application.pipeline import Pipeline
from firecrawl_demo.core import config
from firecrawl_demo.domain.contracts import CONTRACT_VERSION, EvidenceRecordContract
from firecrawl_demo.domain.models import (
    EvidenceRecord,
    evidence_record_from_contract,
)
from firecrawl_demo.infrastructure.planning import PlanCommitContract
from firecrawl_demo.integrations.adapters.research import (
    ResearchAdapter,
    ResearchFinding,
)
from firecrawl_demo.interfaces.cli_base import PlanCommitGuard
from firecrawl_demo.interfaces.mcp.server import CopilotMCPServer


class DummyPipeline(Pipeline):
    def __init__(self) -> None:  # pragma: no cover - base init
        super().__init__()


@pytest.fixture(autouse=True)
def reset_profile() -> Iterable[None]:
    original_path = config.PROFILE_PATH
    yield
    config.switch_profile(profile_path=original_path)


def _make_server(
    pipeline: Pipeline | None = None,
    guard: PlanCommitGuard | None = None,
    builder: Callable[[], Pipeline] | None = None,
) -> CopilotMCPServer:
    active_pipeline = pipeline or DummyPipeline()
    pipeline_builder = builder or active_pipeline.__class__
    return CopilotMCPServer(
        pipeline=active_pipeline,
        plan_guard=guard,
        pipeline_builder=pipeline_builder,
    )


def _write_plan(tmp_path: Path, name: str = "change") -> Path:
    plan_path = tmp_path / f"{name}.plan"
    plan_payload = {
        "changes": [
            {
                "field": "Website URL",
                "value": "https://example.org",
            }
        ],
        "instructions": "Promote verified contact details",
        "contract": {
            "name": "PlanArtifact",
            "version": CONTRACT_VERSION,
            "schema_uri": "https://watercrawl.acesaero.co.za/schemas/v1/plan-artifact",
        },
    }
    plan_path.write_text(json.dumps(plan_payload), encoding="utf-8")
    return plan_path


def _write_commit(
    tmp_path: Path,
    name: str = "change",
    rag: dict[str, float] | None = None,
) -> Path:
    commit_path = tmp_path / f"{name}.commit"
    commit_payload = {
        "diff_format": "markdown",
        "if_match": '"etag-example"',
        "diff_summary": "Update contact information",
        "rag": rag
        or {
            "faithfulness": 0.94,
            "context_precision": 0.91,
            "answer_relevancy": 0.92,
        },
        "contract": {
            "name": "CommitArtifact",
            "version": CONTRACT_VERSION,
            "schema_uri": "https://watercrawl.acesaero.co.za/schemas/v1/commit-artifact",
        },
    }
    commit_path.write_text(json.dumps(commit_payload), encoding="utf-8")
    return commit_path


def _plan_commit_payload(
    tmp_path: Path, *, rag: dict[str, float] | None = None, name: str = "change"
) -> dict[str, object]:
    plan_path = _write_plan(tmp_path, name=name)
    commit_path = _write_commit(tmp_path, name=name, rag=rag)
    return {
        "plan_artifacts": [str(plan_path)],
        "commit_artifacts": [str(commit_path)],
    }


def _make_guard(tmp_path: Path) -> PlanCommitGuard:
    contract = PlanCommitContract(
        require_plan=True,
        diff_format="markdown",
        audit_topic="audit.plan-commit.test",
        allow_force_commit=False,
        require_commit=True,
        require_if_match=True,
        audit_log_path=tmp_path / "plan_commit_audit.jsonl",
        max_diff_size=5000,
        blocked_domains=(),
        blocked_keywords=(),
        rag_thresholds={
            "faithfulness": 0.8,
            "context_precision": 0.7,
            "answer_relevancy": 0.7,
        },
    )
    return PlanCommitGuard(contract=contract)


def test_mcp_lists_tasks() -> None:
    server = _make_server()
    response = server.process_request(
        {"jsonrpc": "2.0", "id": 1, "method": "list_tasks", "params": {}}
    )
    task_names = {task["name"] for task in response["result"]["tasks"]}
    assert "validate_dataset" in task_names
    assert "enrich_dataset" in task_names
    assert "summarize_last_run" in task_names
    assert "list_sanity_issues" in task_names


def test_mcp_runs_validation_task() -> None:
    server = _make_server()
    response = server.process_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "run_task",
            "params": {"task": "validate_dataset", "payload": {"rows": []}},
        }
    )
    assert response["result"]["status"] == "ok"


def test_mcp_handles_unknown_task() -> None:
    server = _make_server()
    response = server.process_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "run_task",
            "params": {"task": "unknown", "payload": {}},
        }
    )
    assert response["error"]["code"] == -32601


def test_mcp_summarize_last_run_handles_empty_history() -> None:
    server = _make_server()
    response = server.process_request(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "run_task",
            "params": {"task": "summarize_last_run", "payload": {}},
        }
    )

    assert response["result"]["status"] == "empty"
    assert "message" in response["result"]


def test_mcp_initialize_reports_profile() -> None:
    server = _make_server()
    response = server.process_request(
        {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}}
    )
    assert response["result"]["profile"]["id"] == config.PROFILE.identifier


def test_mcp_list_profiles_marks_active() -> None:
    server = _make_server()
    response = server.process_request(
        {"jsonrpc": "2.0", "id": 99, "method": "list_profiles", "params": {}}
    )
    profiles = response["result"]["profiles"]
    assert profiles, "Expected at least one profile"
    active = [entry for entry in profiles if entry["active"]]
    assert active and active[0]["id"] == config.PROFILE.identifier


def test_mcp_select_profile_by_path(tmp_path: Path) -> None:
    server = _make_server()
    original_path = config.PROFILE_PATH
    target_path = config.PROJECT_ROOT / "profiles" / "unit_test_profile.yaml"
    definition = yaml.safe_load(original_path.read_text(encoding="utf-8"))
    definition["id"] = "unit-test-profile"
    definition["name"] = "Unit Test Profile"
    definition["description"] = "Temporary profile for MCP tests"
    target_path.write_text(yaml.safe_dump(definition), encoding="utf-8")

    try:
        response = server.process_request(
            {
                "jsonrpc": "2.0",
                "id": 77,
                "method": "select_profile",
                "params": {"profile_path": str(target_path)},
            }
        )
        assert response["result"]["profile"]["id"] == "unit-test-profile"
        assert config.PROFILE.identifier == "unit-test-profile"
        assert server.pipeline is not None
    finally:
        config.switch_profile(profile_path=original_path)
        target_path.unlink(missing_ok=True)


@dataclass
class RecordingSink:
    calls: list[list[EvidenceRecord]]

    def record(
        self, entries: Iterable[EvidenceRecord | EvidenceRecordContract]
    ) -> None:  # pragma: no cover - passthrough
        normalised: list[EvidenceRecord] = []
        for entry in entries:
            if isinstance(entry, EvidenceRecord):
                normalised.append(entry)
            else:
                normalised.append(evidence_record_from_contract(entry))
        self.calls.append(normalised)


class SimpleAdapter(ResearchAdapter):
    def lookup(self, organisation: str, province: str) -> ResearchFinding:
        return ResearchFinding(
            website_url="https://example.org",
            contact_person="Thandi Nkosi",
            contact_email="thandi.nkosi@example.org",
            contact_phone="+27 11 555 0100",
            sources=["https://example.org", "https://caa.co.za/example"],
            notes="Stubbed enrichment",
            confidence=88,
        )


def test_mcp_enrich_task_uses_injected_sink(tmp_path: Path) -> None:
    sink = RecordingSink(calls=[])
    pipeline = Pipeline(research_adapter=SimpleAdapter(), evidence_sink=sink)
    guard = _make_guard(tmp_path)
    server = _make_server(
        pipeline=pipeline,
        guard=guard,
        builder=lambda: Pipeline(research_adapter=SimpleAdapter(), evidence_sink=sink),
    )

    rows = [
        {
            "Name of Organisation": "Example Flight School",
            "Province": "gauteng",
            "Status": "Candidate",
            "Website URL": "",
            "Contact Person": "",
            "Contact Number": "011 555 0000",
            "Contact Email Address": "",
        }
    ]

    response = server.process_request(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "run_task",
            "params": {
                "task": "enrich_dataset",
                "payload": {"rows": rows, **_plan_commit_payload(tmp_path)},
            },
        }
    )

    assert response["result"]["status"] == "ok"
    assert sink.calls, "Evidence sink should receive at least one batch"
    recorded_entries = sink.calls[0]
    assert recorded_entries[0].organisation == "Example Flight School"
    assert any("caa.co.za" in source for source in recorded_entries[0].sources)


def test_mcp_enrich_rejects_missing_plan(tmp_path: Path) -> None:
    pipeline = Pipeline(research_adapter=SimpleAdapter())
    guard = _make_guard(tmp_path)
    server = _make_server(
        pipeline=pipeline,
        guard=guard,
        builder=lambda: Pipeline(research_adapter=SimpleAdapter()),
    )

    rows = [
        {
            "Name of Organisation": "Example Flight School",
            "Province": "gauteng",
            "Status": "Candidate",
            "Website URL": "",
            "Contact Person": "",
            "Contact Number": "011 555 0000",
            "Contact Email Address": "",
        }
    ]

    response = server.process_request(
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "run_task",
            "params": {
                "task": "enrich_dataset",
                "payload": {
                    "rows": rows,
                    "commit_artifacts": [str(_write_commit(tmp_path))],
                },
            },
        }
    )

    assert response["error"]["code"] == -32001
    assert "plan" in response["error"]["message"].lower()


def test_mcp_enrich_rejects_missing_commit(tmp_path: Path) -> None:
    pipeline = Pipeline(research_adapter=SimpleAdapter())
    guard = _make_guard(tmp_path)
    server = _make_server(
        pipeline=pipeline,
        guard=guard,
        builder=lambda: Pipeline(research_adapter=SimpleAdapter()),
    )

    rows = [
        {
            "Name of Organisation": "Commit Flight",
            "Province": "gauteng",
            "Status": "Candidate",
            "Website URL": "",
            "Contact Person": "",
            "Contact Number": "011 555 0000",
            "Contact Email Address": "",
        }
    ]

    response = server.process_request(
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "run_task",
            "params": {
                "task": "enrich_dataset",
                "payload": {
                    "rows": rows,
                    "plan_artifacts": [str(_write_plan(tmp_path, name="missing"))],
                },
            },
        }
    )

    assert response["error"]["code"] == -32001
    assert "commit" in response["error"]["message"].lower()


def test_mcp_enrich_logs_audit_entry(tmp_path: Path) -> None:
    guard = _make_guard(tmp_path)
    pipeline = Pipeline(research_adapter=SimpleAdapter())
    server = _make_server(
        pipeline=pipeline,
        guard=guard,
        builder=lambda: Pipeline(research_adapter=SimpleAdapter()),
    )

    response = server.process_request(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "run_task",
            "params": {
                "task": "enrich_dataset",
                "payload": {"rows": [], **_plan_commit_payload(tmp_path)},
            },
        }
    )

    assert response["result"]["status"] == "ok"
    audit_path = guard.contract.audit_log_path
    assert audit_path.exists()
    entry = json.loads(audit_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert entry["command"] == "mcp.enrich_dataset"
    assert entry["allowed"] is True
    assert entry["plans"]
    assert entry["commits"]
    assert entry["metrics"]["rag_faithfulness"] >= 0.9


def test_mcp_enrich_rejects_low_rag_metrics(tmp_path: Path) -> None:
    guard = _make_guard(tmp_path)
    pipeline = Pipeline(research_adapter=SimpleAdapter())
    server = _make_server(
        pipeline=pipeline,
        guard=guard,
        builder=lambda: Pipeline(research_adapter=SimpleAdapter()),
    )

    low_rag = {"faithfulness": 0.5, "context_precision": 0.9, "answer_relevancy": 0.9}
    response = server.process_request(
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "run_task",
            "params": {
                "task": "enrich_dataset",
                "payload": {"rows": [], **_plan_commit_payload(tmp_path, rag=low_rag)},
            },
        }
    )

    assert response["error"]["code"] == -32001
    assert "rag" in response["error"]["message"].lower()

    audit_lines = (
        guard.contract.audit_log_path.read_text(encoding="utf-8").strip().splitlines()
    )
    failure_entry = json.loads(audit_lines[-1])
    assert failure_entry["allowed"] is False
    assert any(
        violation["code"].startswith("rag_")
        for violation in failure_entry["violations"]
    )


def test_mcp_reports_last_run_metrics_and_sanity_findings(tmp_path: Path) -> None:
    sink = RecordingSink(calls=[])
    pipeline = Pipeline(research_adapter=SimpleAdapter(), evidence_sink=sink)
    guard = _make_guard(tmp_path)
    server = _make_server(
        pipeline=pipeline,
        guard=guard,
        builder=lambda: Pipeline(research_adapter=SimpleAdapter(), evidence_sink=sink),
    )

    rows = [
        {
            "Name of Organisation": "Metrics Flight School",
            "Province": "",
            "Status": "Candidate",
            "Website URL": "example.org",
            "Contact Person": "",
            "Contact Number": "",
            "Contact Email Address": "",
        }
    ]

    server.process_request(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "run_task",
            "params": {
                "task": "enrich_dataset",
                "payload": {"rows": rows, **_plan_commit_payload(tmp_path)},
            },
        }
    )

    summary = server.process_request(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "run_task",
            "params": {"task": "summarize_last_run", "payload": {}},
        }
    )

    assert summary["result"]["status"] == "ok"
    assert summary["result"]["metrics"]["rows_total"] == 1
    assert summary["result"]["sanity_issue_count"] >= 1

    findings_response = server.process_request(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "run_task",
            "params": {"task": "list_sanity_issues", "payload": {}},
        }
    )

    assert findings_response["result"]["status"] == "ok"
    findings = findings_response["result"]["findings"]
    assert isinstance(findings, list)
    assert findings, "Expected at least one sanity finding"
    assert all("issue" in finding and "remediation" in finding for finding in findings)
