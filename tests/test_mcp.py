from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from firecrawl_demo.core.models import EvidenceRecord
from firecrawl_demo.core.pipeline import Pipeline
from firecrawl_demo.integrations.research import ResearchAdapter, ResearchFinding
from firecrawl_demo.interfaces.mcp.server import CopilotMCPServer


class DummyPipeline(Pipeline):
    def __init__(self) -> None:  # pragma: no cover - base init
        super().__init__()


def test_mcp_lists_tasks() -> None:
    server = CopilotMCPServer(pipeline=DummyPipeline())
    response = server.process_request(
        {"jsonrpc": "2.0", "id": 1, "method": "list_tasks", "params": {}}
    )
    task_names = {task["name"] for task in response["result"]["tasks"]}
    assert "validate_dataset" in task_names
    assert "enrich_dataset" in task_names
    assert "summarize_last_run" in task_names
    assert "list_sanity_issues" in task_names


def test_mcp_runs_validation_task() -> None:
    server = CopilotMCPServer(pipeline=DummyPipeline())
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
    server = CopilotMCPServer(pipeline=DummyPipeline())
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
    server = CopilotMCPServer(pipeline=DummyPipeline())
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


@dataclass
class RecordingSink:
    calls: list[list[EvidenceRecord]]

    def record(
        self, entries: Iterable[EvidenceRecord]
    ) -> None:  # pragma: no cover - passthrough
        self.calls.append(list(entries))


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


def test_mcp_enrich_task_uses_injected_sink() -> None:
    sink = RecordingSink(calls=[])
    pipeline = Pipeline(research_adapter=SimpleAdapter(), evidence_sink=sink)
    server = CopilotMCPServer(pipeline=pipeline)

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
            "params": {"task": "enrich_dataset", "payload": {"rows": rows}},
        }
    )

    assert response["result"]["status"] == "ok"
    assert sink.calls, "Evidence sink should receive at least one batch"
    recorded_entries = sink.calls[0]
    assert recorded_entries[0].organisation == "Example Flight School"
    assert any("caa.co.za" in source for source in recorded_entries[0].sources)


def test_mcp_reports_last_run_metrics_and_sanity_findings() -> None:
    sink = RecordingSink(calls=[])
    pipeline = Pipeline(research_adapter=SimpleAdapter(), evidence_sink=sink)
    server = CopilotMCPServer(pipeline=pipeline)

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
            "params": {"task": "enrich_dataset", "payload": {"rows": rows}},
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
