from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from firecrawl_demo.application.pipeline import Pipeline
from firecrawl_demo.core import config
from firecrawl_demo.core.profiles import ProfileError
from firecrawl_demo.interfaces.cli_base import (
    PlanCommitError,
    PlanCommitGuard,
    load_cli_environment,
)

_JSONRPC = "2.0"


class CopilotMCPServer:
    """Minimal JSON-RPC server exposing pipeline automation tasks to Copilot."""

    def __init__(
        self,
        pipeline: Pipeline,
        *,
        plan_guard: PlanCommitGuard | None = None,
        pipeline_builder: Callable[[], Pipeline] | None = None,
    ) -> None:
        self.pipeline = pipeline
        self._pipeline_builder = pipeline_builder
        environment = load_cli_environment()
        self._plan_guard = plan_guard or environment.plan_guard

    @staticmethod
    def _profile_payload() -> dict[str, Any]:
        return {
            "id": config.PROFILE.identifier,
            "name": config.PROFILE.name,
            "description": config.PROFILE.description,
            "path": str(config.PROFILE_PATH),
        }

    def _reload_pipeline(self) -> None:
        if self._pipeline_builder is not None:
            self.pipeline = self._pipeline_builder()
        else:
            self.pipeline = Pipeline()

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
                        "listProfiles": True,
                        "selectProfile": True,
                    },
                    "profile": self._profile_payload(),
                },
            }

        if method == "list_tasks":
            tasks = [
                {"name": name, "description": description}
                for name, description in self.pipeline.available_tasks().items()
            ]
            return {"jsonrpc": _JSONRPC, "id": request_id, "result": {"tasks": tasks}}

        if method == "list_profiles":
            profiles = config.list_profiles()
            return {
                "jsonrpc": _JSONRPC,
                "id": request_id,
                "result": {"profiles": profiles},
            }

        if method == "select_profile":
            profile_id = params.get("profile_id")
            profile_path = params.get("profile_path")
            try:
                resolved_path = Path(profile_path) if profile_path else None
                profile = config.switch_profile(
                    profile_id=profile_id,
                    profile_path=resolved_path,
                )
            except (ProfileError, FileNotFoundError) as exc:
                return {
                    "jsonrpc": _JSONRPC,
                    "id": request_id,
                    "error": {"code": -32002, "message": str(exc)},
                }
            self._reload_pipeline()
            return {
                "jsonrpc": _JSONRPC,
                "id": request_id,
                "result": {
                    "profile": {
                        "id": profile.identifier,
                        "name": profile.name,
                        "description": profile.description,
                        "path": str(config.PROFILE_PATH),
                    }
                },
            }

        if method == "run_task":
            task = params.get("task")
            payload = params.get("payload", {})
            if (
                task == "enrich_dataset"
                and isinstance(payload, dict)
                and self._plan_guard is not None
            ):
                try:
                    self._plan_guard.require_for_payload("mcp.enrich_dataset", payload)
                except PlanCommitError as exc:
                    return {
                        "jsonrpc": _JSONRPC,
                        "id": request_id,
                        "error": {"code": -32001, "message": str(exc)},
                    }
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
