from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from firecrawl_demo.core.pipeline import Pipeline

_JSONRPC = "2.0"


class CopilotMCPServer:
    """Minimal JSON-RPC server exposing pipeline automation tasks to Copilot."""

    def __init__(self, pipeline: Pipeline) -> None:
        self.pipeline = pipeline

    def process_request(self, request: dict[str, Any]) -> dict[str, Any]:
        method = request.get("method")
        request_id = request.get("id")
        params = request.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": _JSONRPC,
                "id": request_id,
                "result": {
                    "capabilities": {
                        "listTasks": True,
                        "runTask": True,
                    }
                },
            }

        if method == "list_tasks":
            tasks = [
                {"name": name, "description": description}
                for name, description in self.pipeline.available_tasks().items()
            ]
            return {"jsonrpc": _JSONRPC, "id": request_id, "result": {"tasks": tasks}}

        if method == "run_task":
            task = params.get("task")
            payload = params.get("payload", {})
            try:
                result = self.pipeline.run_task(str(task), payload)
            except KeyError:
                return {
                    "jsonrpc": _JSONRPC,
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Unknown task '{task}'"},
                }
            except (ValueError, RuntimeError) as exc:
                return {
                    "jsonrpc": _JSONRPC,
                    "id": request_id,
                    "error": {"code": -32000, "message": str(exc)},
                }
            return {"jsonrpc": _JSONRPC, "id": request_id, "result": result}

        if method == "shutdown":
            return {"jsonrpc": _JSONRPC, "id": request_id, "result": {"status": "ok"}}

        return {
            "jsonrpc": _JSONRPC,
            "id": request_id,
            "error": {"code": -32601, "message": f"Unknown method '{method}'"},
        }

    async def serve_stdio(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                response = {
                    "jsonrpc": _JSONRPC,
                    "id": None,
                    "error": {"code": -32700, "message": "Invalid JSON"},
                }
            else:
                response = self.process_request(request)
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
            if request.get("method") == "shutdown":
                break
