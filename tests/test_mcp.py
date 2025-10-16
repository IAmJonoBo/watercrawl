from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from firecrawl_demo.mcp.server import CopilotMCPServer
from firecrawl_demo.models import EvidenceRecord
from firecrawl_demo.pipeline import Pipeline
from firecrawl_demo.research import ResearchAdapter, ResearchFinding


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
