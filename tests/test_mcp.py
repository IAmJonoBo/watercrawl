from firecrawl_demo.mcp.server import CopilotMCPServer
from firecrawl_demo.pipeline import Pipeline


class DummyPipeline(Pipeline):
    def __init__(self):  # pragma: no cover - base init
        super().__init__()


def test_mcp_lists_tasks():
    server = CopilotMCPServer(pipeline=DummyPipeline())
    response = server.process_request(
        {"jsonrpc": "2.0", "id": 1, "method": "list_tasks", "params": {}}
    )
    task_names = {task["name"] for task in response["result"]["tasks"]}
    assert "validate_dataset" in task_names


def test_mcp_runs_validation_task():
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


def test_mcp_handles_unknown_task():
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
