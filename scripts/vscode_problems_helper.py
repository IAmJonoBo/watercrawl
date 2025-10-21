"""Helper to process VS Code problems export and invoke collect_problems.py.

Features:
- Read VS Code problems export (path via ENV VSCODE_PROBLEMS_EXPORT or --path)
- Optional watch mode (polling) to re-run on file changes
- Filters: workspace-folder prefix, minimum severity, source/tool include list
- Produce a small evidence suggestions JSON mapping diagnostics to a conservative
  evidence_log-like payload for downstream tooling or Codex post-processing
- Invoke the existing `scripts/collect_problems.py` to regenerate `problems_report.json`

This file intentionally avoids extra dependencies and uses polling for watch.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

DEFAULT_POLL_INTERVAL = 2.0


def load_export(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        # maybe the export is an array or empty
        payload = json.loads(text or "[]")
    return payload


def extract_markers(payload: Any) -> list[Mapping[str, Any]]:
    # Accept either top-level array or object with a key like 'markers'/'problems'
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("markers", "problems", "items", "diagnostics"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, Mapping)]
        # fallback to single payload as marker
        return [payload]
    return []


def marker_uri_path(marker: Mapping[str, Any]) -> str | None:
    loc = marker.get("location") or marker.get("resource")
    if isinstance(loc, Mapping):
        uri = loc.get("uri") or loc.get("url")
        if isinstance(uri, str):
            # handle file:/// paths
            if uri.startswith("file:"):
                try:
                    from urllib.parse import unquote, urlparse

                    parsed = urlparse(uri)
                    return unquote(parsed.path)
                except Exception:  # pragma: no cover - fallback
                    return uri
            return uri
        # sometimes path is directly available
        path_val = loc.get("path") or loc.get("fsPath") or loc.get("file")
        if isinstance(path_val, str):
            return path_val
    if isinstance(loc, str):
        return loc
    return None


def marker_severity(marker: Mapping[str, Any]) -> int | None:
    sev = marker.get("severity")
    if isinstance(sev, int):
        return sev
    # try to parse textual severities
    if isinstance(sev, str):
        s = sev.lower()
        if s.startswith("err"):
            return 1
        if s.startswith("warn"):
            return 2
        if s.startswith("info"):
            return 4
        if s.startswith("hint"):
            return 8
    return None


def filter_markers(
    markers: Iterable[Mapping[str, Any]],
    workspace_prefix: str | None = None,
    min_severity: int | None = None,
    sources: Iterable[str] | None = None,
) -> list[Mapping[str, Any]]:
    allowed_sources = {s.lower() for s in sources} if sources else None
    out: list[Mapping[str, Any]] = []
    for m in markers:
        uri = marker_uri_path(m)
        if workspace_prefix and uri:
            if not str(uri).startswith(workspace_prefix):
                continue
        sev = marker_severity(m)
        if min_severity is not None and sev is not None:
            # larger numeric value is lower priority for some conventions; we use numeric match
            if sev > min_severity:
                continue
        if allowed_sources is not None:
            src = m.get("source") or m.get("owner") or ""
            src_l = str(src).lower()
            if src_l and src_l not in allowed_sources:
                continue
        out.append(m)
    return out


def build_evidence_suggestions(
    markers: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    suggestions: list[dict[str, Any]] = []
    for marker in markers:
        uri = marker_uri_path(marker)
        loc = marker.get("location") or marker.get("resource") or {}
        # attempt to extract line
        line = None
        if isinstance(loc, Mapping):
            rng = loc.get("range") or {}
            if isinstance(rng, Mapping):
                start = rng.get("start") or {}
                if isinstance(start, Mapping):
                    line = start.get("line") or start.get("lineNumber")
        if line is None:
            line = marker.get("line") or marker.get("lineNumber")
        code = marker.get("code")
        message = marker.get("message") or marker.get("description") or ""
        suggestion: dict[str, Any] = {
            "path": uri,
            "line": int(line) if isinstance(line, int) else None,
            "code": str(code) if code is not None else None,
            "message": message,
            "suggested_what_changed": message,
            "sources": [],
            "notes": "Auto-generated evidence suggestion from VS Code diagnostics",
            "timestamp": now,
            "confidence": 50,
        }
        suggestions.append(suggestion)
    return suggestions


def run_collector(
    output: Path | None = None, env_vars: Mapping[str, str] | None = None
) -> int:
    cmd = [sys.executable, "-m", "scripts.collect_problems"]
    if output:
        cmd.extend(["--output", str(output)])
    print("Invoking collect_problems:", " ".join(cmd))
    env = os.environ.copy()
    if env_vars:
        env.update({str(k): str(v) for k, v in env_vars.items()})
    proc = subprocess.run(cmd, check=False, env=env)
    return proc.returncode


def process_once(
    path: Path,
    out_evidence: Path | None,
    filtered_export_path: Path | None,
    workspace_prefix: str | None,
    min_severity: int | None,
    sources: Iterable[str] | None,
    collector_output: Path | None,
) -> None:
    payload = load_export(path)
    markers = extract_markers(payload)
    print(f"Loaded {len(markers)} markers from {path}")
    filtered = filter_markers(markers, workspace_prefix, min_severity, sources)
    print(f"After filtering: {len(filtered)} markers")

    if filtered_export_path:
        obj = {"markers": filtered}
        filtered_export_path.parent.mkdir(parents=True, exist_ok=True)
        filtered_export_path.write_text(json.dumps(obj, indent=2), encoding="utf-8")
        print(f"Wrote filtered export to {filtered_export_path}")
    export_for_collector = filtered_export_path or path

    if out_evidence:
        suggestions = build_evidence_suggestions(filtered)
        out_evidence.parent.mkdir(parents=True, exist_ok=True)
        out_evidence.write_text(json.dumps(suggestions, indent=2), encoding="utf-8")
        print(f"Wrote evidence suggestions to {out_evidence}")

    # invoke collector
    env_override: dict[str, str] = {}
    if export_for_collector:
        env_override["VSCODE_PROBLEMS_EXPORT"] = (
            export_for_collector.expanduser().as_posix()
        )
    rc = run_collector(collector_output, env_override)
    if rc == 0:
        print("collect_problems.py completed successfully")
    else:
        print(f"collect_problems.py returned {rc}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Process VS Code problems export and run local collector"
    )
    p.add_argument(
        "--path",
        type=Path,
        help="Path to VS Code export JSON. If omitted, uses VSCODE_PROBLEMS_EXPORT env var.",
    )
    p.add_argument(
        "--watch",
        action="store_true",
        help="Enable watch mode (polling) and re-run on changes",
    )
    p.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL,
        help="Polling interval seconds when watching",
    )
    p.add_argument(
        "--workspace-prefix",
        type=str,
        default=None,
        help="Only include markers whose path starts with this prefix",
    )
    p.add_argument(
        "--min-severity",
        type=int,
        default=None,
        help="Minimum severity numeric value to include (e.g. 1 for error)",
    )
    p.add_argument(
        "--source",
        action="append",
        dest="sources",
        help="Only include markers from these sources/tools (can be repeated)",
    )
    p.add_argument(
        "--evidence-out",
        type=Path,
        default=Path(".vscode/evidence_suggestions.json"),
        help="Path to write evidence suggestions JSON",
    )
    p.add_argument(
        "--filtered-export-out",
        type=Path,
        default=Path(".vscode/problems-export.filtered.json"),
        help="Path to write filtered VS Code export JSON",
    )
    p.add_argument(
        "--collector-output",
        type=Path,
        default=Path("problems_report.json"),
        help="Path for collect_problems.py output",
    )
    return p.parse_args(argv)


def _main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    export_path = args.path
    if not export_path:
        env_path = os.getenv("VSCODE_PROBLEMS_EXPORT")
        if not env_path:
            print(
                "Error: no --path provided and VSCODE_PROBLEMS_EXPORT not set",
                file=sys.stderr,
            )
            return 2
        export_path = Path(env_path)
    if not export_path.exists():
        print(f"Error: export file not found: {export_path}", file=sys.stderr)
        return 3

    last_mtime = None
    try:
        while True:
            mtime = export_path.stat().st_mtime
            if last_mtime is None or mtime != last_mtime:
                print(f"Detected change or first run for {export_path}")
                process_once(
                    export_path,
                    args.evidence_out,
                    args.filtered_export_out,
                    args.workspace_prefix,
                    args.min_severity,
                    args.sources,
                    args.collector_output,
                )
                last_mtime = mtime
            if not args.watch:
                break
            time.sleep(args.poll_interval)
    except KeyboardInterrupt:
        print("Interrupted, exiting")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
