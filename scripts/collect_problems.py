"""Aggregate QA findings into a compact ``problems_report.json`` artefact."""

# pylint: disable=missing-function-docstring,too-many-lines,line-too-long

from __future__ import annotations

import argparse
import functools
import json
import os
import re
import shlex
import shutil
import subprocess  # nosec B404 - subprocess usage is for controlled QA tool execution
import sys
import tempfile
import threading
import time
import tracemalloc
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any

try:
    import tomllib  # Python 3.11+
    from tomllib import TOMLDecodeError
except ModuleNotFoundError:  # pragma: no cover - fallback for older interpreters
    import tomli as tomllib  # type: ignore[no-redef]
    from tomli import TOMLDecodeError  # type: ignore

from urllib.parse import unquote, urlparse


def _int_from_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


CACHE_TOOL_AVAILABILITY: dict[str, tuple[float, bool]] = {}
CACHE_LOCK = threading.Lock()


_bootstrap: ModuleType | None

try:  # pragma: no cover - bootstrap helpers may be unavailable on minimal installs
    _bootstrap = import_module("tools.hooks.bootstrap")
except Exception:  # pragma: no cover - minimal fallback when bootstrap is unavailable
    _bootstrap = None


class _FallbackBootstrapError(RuntimeError):
    """Fallback BootstrapError when hooks module is unavailable."""


BootstrapError: type[Exception] = _FallbackBootstrapError
_ensure_python_package: Callable[..., None] | None = None
_ensure_trunk: Callable[..., Path] | None = None

if _bootstrap is not None:
    if hasattr(_bootstrap, "BootstrapError"):
        BootstrapError = _bootstrap.BootstrapError  # type: ignore[attr-defined]
    _ensure_python_package = getattr(_bootstrap, "ensure_python_package", None)
    _ensure_trunk = getattr(_bootstrap, "ensure_trunk", None)


BOOTSTRAP_AVAILABLE = any(
    helper is not None for helper in (_ensure_python_package, _ensure_trunk)
)


def ensure_python_package(
    package_name: str,
    version: str | None = None,
    python_executable: str = sys.executable,
    allow_network: bool = True,
) -> None:
    installer = _ensure_python_package
    if installer is None:
        raise BootstrapError(
            "Bootstrap helpers unavailable; cannot ensure python package "
            f"{package_name!r}."
        )
    installer(
        package_name,
        version,
        python_executable=python_executable,
        allow_network=allow_network,
    )


def ensure_trunk(version: str = "latest") -> Path:
    installer = _ensure_trunk
    if installer is None:
        raise BootstrapError("Bootstrap helpers unavailable; cannot ensure trunk CLI.")
    return installer(version)


def _python_package_installer(package: str, version: str) -> Callable[[], None]:
    def _install() -> None:
        ensure_python_package(
            package,
            version,
            python_executable=sys.executable,
            allow_network=True,
        )

    return _install


def _trunk_installer(version: str = "latest") -> Callable[[], None]:
    def _install() -> None:
        ensure_trunk(version)

    return _install


TOOL_INSTALLERS: dict[str, tuple[Callable[[], None], ...]] = {
    "pytest": (_python_package_installer("pytest", "8.4.2"),),
    "ruff": (_python_package_installer("ruff", "0.14.1"),),
    "mypy": (_python_package_installer("mypy", "1.18.2"),),
    "bandit": (_python_package_installer("bandit", "1.8.6"),),
    "black": (_python_package_installer("black", "25.9.0"),),
    "isort": (_python_package_installer("isort", "7.0.0"),),
    "yamllint": (
        _python_package_installer("yamllint", "1.37.1"),
        _python_package_installer("yamlfix", "1.16.0"),
    ),
    "yamlfix": (_python_package_installer("yamlfix", "1.16.0"),),
    "sqlfluff": (
        _python_package_installer("sqlfluff", "3.5.0"),
        _python_package_installer("sqlfluff-templater-dbt", "3.5.0"),
    ),
    "pre-commit": (_python_package_installer("pre-commit", "4.3.0"),),
}

if _ensure_trunk is not None:
    TOOL_INSTALLERS["trunk"] = (_trunk_installer(),)
else:
    TOOL_INSTALLERS["trunk"] = ()

CORE_TOOLCHAIN = ("pytest", "ruff", "mypy", "bandit", "black", "isort", "trunk")


@functools.lru_cache(maxsize=None)
def ensure_tool_dependencies(tool_name: str) -> None:
    if not BOOTSTRAP_AVAILABLE:
        return
    installers = TOOL_INSTALLERS.get(tool_name)
    if not installers:
        return
    for installer in installers:
        installer()


# Optional dependency on watercrawl for contract environment - graceful fallback
try:
    from watercrawl.integrations.contracts.shared_config import (
        environment_payload as contracts_environment_payload,
    )
except (ModuleNotFoundError, ImportError):  # pragma: no cover - ephemeral runners

    def contracts_environment_payload() -> dict[str, str]:
        """Fallback when watercrawl is not available (e.g., ephemeral runners)."""
        return {}


try:  # pragma: no cover - optional dependency
    import yaml as YAML  # type: ignore[import-untyped]
except ModuleNotFoundError:  # pragma: no cover
    YAML = None  # type: ignore

SQLFLUFF_AVAILABLE = sys.version_info < (3, 14)
if SQLFLUFF_AVAILABLE:
    try:  # pragma: no branch - import guard for script execution
        from tools.sql.sqlfluff_runner import (
            DEFAULT_DBT_PROJECT,
            DEFAULT_DUCKDB,
            ensure_duckdb,
        )
    except ModuleNotFoundError as exc:  # pragma: no cover - defensive path fix
        if exc.name == "duckdb":
            SQLFLUFF_AVAILABLE = False
        else:
            PROJECT_ROOT = Path(__file__).resolve().parents[1]
            if str(PROJECT_ROOT) not in sys.path:
                sys.path.insert(0, str(PROJECT_ROOT))
            try:
                from tools.sql.sqlfluff_runner import (
                    DEFAULT_DBT_PROJECT,
                    DEFAULT_DUCKDB,
                    ensure_duckdb,
                )
            except ModuleNotFoundError as inner_exc:  # pragma: no cover - fallback
                if inner_exc.name == "duckdb":
                    SQLFLUFF_AVAILABLE = False
                else:
                    raise
else:  # pragma: no cover - placeholders for type checking when disabled
    DEFAULT_DBT_PROJECT = Path("data_contracts/analytics")
    DEFAULT_DUCKDB = Path("target/contracts.duckdb")

    def ensure_duckdb(project_dir: Path, relative_path: Path) -> Path:
        raise RuntimeError(
            f"sqlfluff unavailable on Python {sys.version_info.major}.{sys.version_info.minor}"
        )


# Bandit doesn't support Python 3.14 yet (ast.Num removed)
BANDIT_AVAILABLE = sys.version_info < (3, 14)

PYTHON_TOOL_MODULES: dict[str, str] = {
    "ruff": "ruff",
    "mypy": "mypy",
    "black": "black",
    "isort": "isort",
    "bandit": "bandit",
    "yamllint": "yamllint",
    "yamlfix": "yamlfix",
    "pytest": "pytest",
}

PRE_COMMIT_CONFIG = Path(".pre-commit-config.yaml")
MAX_PARALLELISM = max(4, os.cpu_count() or 4)

DEFAULT_TOOL_CACHE_TTL = 900
TOOL_CACHE_TTL_SECONDS = max(
    0, _int_from_env("PROBLEMS_TOOL_CACHE_TTL", DEFAULT_TOOL_CACHE_TTL)
)
_DEFAULT_STREAM_CACHE_DIR = Path.home() / ".cache" / "watercrawl" / "problems_streams"
STREAM_CACHE_DIR = Path(
    os.getenv("PROBLEMS_STREAM_CACHE_DIR", str(_DEFAULT_STREAM_CACHE_DIR))
)
STREAM_PERSIST_THRESHOLD = max(
    0, _int_from_env("PROBLEMS_STREAM_CACHE_THRESHOLD", 64 * 1024)
)
STREAM_CACHE_MAX_AGE = max(
    0, _int_from_env("PROBLEMS_STREAM_CACHE_MAX_AGE", 7 * 24 * 60 * 60)
)
STREAM_CACHE_MAX_BYTES = max(
    0, _int_from_env("PROBLEMS_STREAM_CACHE_MAX_BYTES", 512 * 1024 * 1024)
)

REPORT_PATH = Path("problems_report.json")
TOOLS_CONFIG_PATH = Path("presets/problems_tools.toml")
VSCODE_PROBLEMS_ENV = "VSCODE_PROBLEMS_EXPORT"
PROBLEMS_MAX_ISSUES_ENV = "PROBLEMS_MAX_ISSUES"
MAX_TEXT = 2000
MAX_ISSUES = int(os.getenv(PROBLEMS_MAX_ISSUES_ENV, "100") or "100")
PREVIEW_CHUNK = 200
MAX_PREVIEW_CHUNKS = 40
TRUNK_ENV_VAR = "TRUNK_CHECK_OPTS"
AUTOFIX_COMMANDS: dict[str, list[str]] = {
    "ruff": ["ruff", "check", ".", "--fix"],
    "black": ["black", "."],
    "isort": ["isort", "."],
    "yamllint": ["yamlfix", "."],
    "biome": ["npx", "biome", "check", "--apply", "--reporter", "json"],
    "trunk": ["trunk", "fmt"],
    "pre-commit": ["pre-commit", "run", "--all-files"],
}
AUTOFIX_WITH_POETRY: dict[str, list[str]] = {
    "ruff": ["poetry", "run", "ruff", "check", ".", "--fix"],
    "black": ["poetry", "run", "black", "."],
    "isort": ["poetry", "run", "isort", "."],
    "yamllint": ["poetry", "run", "yamlfix", "."],
    "pre-commit": ["poetry", "run", "pre-commit", "run", "--all-files"],
}
WARNING_HIGHLIGHT_LIMIT = 10
TRUNK_CONFIG_PATH = Path(".trunk/trunk.yaml")
BIOME_CONFIG_FILES = (Path("biome.json"), Path("biome.jsonc"))
PACKAGE_JSON = Path("package.json")

CompletedProcess = subprocess.CompletedProcess[str]


def _truncate(value: str, *, limit: int = MAX_TEXT) -> str:
    if len(value) <= limit:
        return value
    remaining = len(value) - limit
    return f"{value[:limit]}… (truncated {remaining} characters)"


def _normalise_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def build_preview(
    value: str,
    *,
    limit: int = MAX_TEXT,
    chunk_size: int = PREVIEW_CHUNK,
    max_chunks: int = MAX_PREVIEW_CHUNKS,
) -> dict[str, Any]:
    normalised = _normalise_newlines(value)
    truncated_chars = max(len(normalised) - limit, 0)
    limited = normalised[:limit]
    chunks: list[str] = []
    for raw_line in limited.split("\n"):
        if not raw_line:
            if chunks:
                chunks.append("")
            continue
        for start in range(0, len(raw_line), chunk_size):
            chunks.append(raw_line[start : start + chunk_size])
    omitted_chunks = 0
    truncated = truncated_chars > 0
    if len(chunks) > max_chunks:
        omitted_chunks = len(chunks) - max_chunks
        chunks = chunks[:max_chunks]
        truncated = True
    if truncated:
        if chunks:
            chunks[-1] = f"{chunks[-1]}…"
        else:
            chunks.append("…")
    payload: dict[str, Any] = {"chunks": chunks}
    if truncated:
        payload["truncated"] = True
    if truncated_chars:
        payload["omitted_characters"] = truncated_chars
    if omitted_chunks:
        payload["omitted_chunks"] = omitted_chunks
    return payload


def _attach_preview(entry: dict[str, Any], key: str, value: str | None) -> None:
    if not value:
        return None
    entry[key] = build_preview(value)
    return None


def _truncate_message(entry: dict[str, Any]) -> None:
    message = entry.get("message")
    if isinstance(message, str):
        entry["message"] = _truncate(message)
    return None


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _read_yaml(path: Path) -> dict[str, Any] | None:
    if YAML is None or not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = YAML.safe_load(fh)
            if isinstance(data, dict):
                return data
    # type: ignore[union-attr]
    except (OSError, UnicodeDecodeError, YAML.YAMLError):
        return None
    return None


_SQLFLUFF_WARNING_PATTERNS = (
    "because it is a macro",
    "was not found in dbt project",
)


def _should_ignore_warning(message: str) -> bool:
    lower = message.lower()
    return any(pattern in lower for pattern in _SQLFLUFF_WARNING_PATTERNS)


def _discover_trunk_linters(path: Path = TRUNK_CONFIG_PATH) -> list[str]:
    config = _read_yaml(path)
    if not config:
        return []
    lint_section = config.get("lint")
    if not isinstance(lint_section, dict):
        return []
    enabled = lint_section.get("enabled")
    if isinstance(enabled, list):
        return [str(item).split("@", maxsplit=1)[0] for item in enabled]
    return []


def _discover_biome_presence() -> bool:
    for candidate in BIOME_CONFIG_FILES:
        if candidate.exists():
            return True
    if PACKAGE_JSON.exists():
        try:
            data = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):  # pragma: no cover - best effort
            return False
        for section in ("dependencies", "devDependencies", "peerDependencies"):
            deps = data.get(section)
            if isinstance(deps, dict):
                if any("biome" in name.lower() for name in deps):
                    return True
    return False


_PYTHON_WARNING_PATTERN = re.compile(
    r"^(?P<path>[^:]+):(?P<line>\d+): (?:(?P<category>[\w\.]+Warning): )?(?P<message>.*)$"
)
_TAB_WARNING_PATTERN = re.compile(
    r"^(?P<prefix>\[[^\]]+\]|\w+|\S+?)\s*(?:\t+|\s{2,})WARNING\s*(?P<message>.+)$",
    re.IGNORECASE,
)
_GENERIC_WARNING_PATTERN = re.compile(
    r"^\s*WARNING[:\-\s]*(?P<message>.+)$", re.IGNORECASE
)
_NPM_WARN_PATTERN = re.compile(
    r"^\s*(npm)\s+(?P<level>warn|warning|notice|note)\s+(?P<message>.+)$",
    re.IGNORECASE,
)


def _derive_warning_kind(category: str | None, message: str) -> str:
    category_lower = (category or "").lower()
    message_lower = message.lower()
    if "deprec" in category_lower or "deprec" in message_lower:
        return "deprecation"
    return "general"


def _finalise_warning_entry(entry: dict[str, Any]) -> dict[str, Any]:
    _truncate_message(entry)
    kind = _derive_warning_kind(entry.get("category"), entry.get("message", ""))
    entry["kind"] = kind
    entry.setdefault("severity", "warning")
    if kind == "deprecation":
        entry.setdefault(
            "guidance",
            "Plan dependency or API updates before the deprecated behaviour is removed.",
        )
    return entry


def _parse_warning_line(line: str) -> dict[str, Any] | None:
    if not line or (
        "warning" not in line.lower() and "deprecationwarning" not in line.lower()
    ):
        return None
    match = _PYTHON_WARNING_PATTERN.match(line)
    if match:
        data = match.groupdict()
        entry: dict[str, Any] = {
            "path": data.get("path"),
            "line": _coerce_int(data.get("line")),
            "category": data.get("category") or "Warning",
            "message": data.get("message") or "",
        }
        if _should_ignore_warning(entry["message"]):
            return None
        return _finalise_warning_entry(entry)

    match = _TAB_WARNING_PATTERN.match(line)
    if match:
        prefix = match.group("prefix") or ""
        message = match.group("message") or ""
        entry = {
            "source": prefix.strip().strip("[]"),
            "category": "Warning",
            "message": message.strip(),
        }
        if _should_ignore_warning(entry["message"]):
            return None
        return _finalise_warning_entry(entry)

    match = _GENERIC_WARNING_PATTERN.match(line)
    if match:
        message = match.group("message") or ""
        entry = {
            "category": "Warning",
            "message": message.strip(),
        }
        if _should_ignore_warning(entry["message"]):
            return None
        return _finalise_warning_entry(entry)

    match = _NPM_WARN_PATTERN.match(line)
    if match:
        level = match.group("level") or "warn"
        entry = {
            "source": "npm",
            "category": f"npm {level.lower()}",
            "message": match.group("message").strip(),
        }
        if _should_ignore_warning(entry["message"]):
            return None
        return _finalise_warning_entry(entry)

    if "deprecationwarning" in line.lower():
        entry = {
            "category": "DeprecationWarning",
            "message": line.strip(),
        }
        if _should_ignore_warning(entry["message"]):
            return None
        return _finalise_warning_entry(entry)

    return None


def _extract_warnings(
    stdout: str | None, stderr: str | None
) -> tuple[list[dict[str, Any]], int]:
    warnings: list[dict[str, Any]] = []
    omitted = 0
    for stream_name, payload in (("stdout", stdout), ("stderr", stderr)):
        if not payload:
            continue
        for raw_line in payload.splitlines():
            entry = _parse_warning_line(raw_line)
            if entry is None:
                continue
            entry["stream"] = stream_name
            warnings.append(entry)
    if len(warnings) > MAX_ISSUES:
        omitted = len(warnings) - MAX_ISSUES
        warnings = warnings[:MAX_ISSUES]
    return warnings, omitted


@dataclass
class ToolSpec:
    """Describe how to execute and parse a QA tool."""

    name: str
    command: Callable[[], tuple[list[str], Mapping[str, str] | None, Path | None]]
    parser: Callable[[CompletedProcess], dict[str, Any]]
    optional: bool = False
    autofix: tuple[tuple[str, ...], ...] = ()


class ToolRegistry:
    """Registry providing deduplicated tool specs with optional overrides."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec, *, replace: bool = False) -> None:
        existing = self._tools.get(spec.name)
        if existing is not None and not replace:
            return None
        self._tools[spec.name] = spec
        return None

    def extend(self, specs: Iterable[ToolSpec], *, replace: bool = False) -> None:
        for spec in specs:
            self.register(spec, replace=replace)
        return None

    def values(self) -> list[ToolSpec]:
        return list(self._tools.values())


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    normalised = value.strip().lower()
    if not normalised:
        return False
    return normalised not in {"0", "false", "no", "off"}


def _static_command(*args: str) -> Callable[[], tuple[list[str], None, None]]:
    def _factory() -> tuple[list[str], None, None]:
        return list(args), None, None

    return _factory


def _configured_command(
    args: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    cwd: str | Path | None = None,
) -> Callable[[], tuple[list[str], Mapping[str, str] | None, Path | None]]:
    def _factory() -> tuple[list[str], Mapping[str, str] | None, Path | None]:
        env_copy: Mapping[str, str] | None = None
        if env:
            env_copy = {str(key): str(value) for key, value in env.items()}
        resolved_cwd: Path | None = None
        if cwd is not None:
            resolved_cwd = Path(cwd)
        return list(args), env_copy, resolved_cwd

    return _factory


def _sqlfluff_command() -> tuple[list[str], Mapping[str, str], None]:
    duckdb_path = ensure_duckdb(DEFAULT_DBT_PROJECT, DEFAULT_DUCKDB)
    env = os.environ.copy()
    env.update(contracts_environment_payload())
    env.setdefault("DBT_DUCKDB_PATH", duckdb_path.as_posix())
    cmd = [
        "sqlfluff",
        "lint",
        str(DEFAULT_DBT_PROJECT),
        "--format",
        "json",
    ]
    return cmd, env, None


def _probe_tool_command(tool_name: str) -> bool:
    try:
        result = subprocess.run(  # nosec B603 - controlled arguments
            [tool_name, "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if result.returncode == 0:
            return True
    except FileNotFoundError:
        pass
    except subprocess.TimeoutExpired:
        return False

    module = PYTHON_TOOL_MODULES.get(tool_name)
    if module:
        try:
            result = subprocess.run(  # nosec B603 - controlled arguments
                [sys.executable, "-m", module, "--version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    return False


def _check_tool_available(tool_name: str) -> bool:
    now = time.monotonic()
    with CACHE_LOCK:
        cached_entry: tuple[float, bool] | None = CACHE_TOOL_AVAILABILITY.get(tool_name)
    if cached_entry is not None:
        cached_timestamp, cached_value = cached_entry
        if (
            TOOL_CACHE_TTL_SECONDS <= 0
            or now - cached_timestamp <= TOOL_CACHE_TTL_SECONDS
        ):
            return cached_value
    available = _probe_tool_command(tool_name)
    with CACHE_LOCK:
        CACHE_TOOL_AVAILABILITY[tool_name] = (now, available)
    return available


def _run_subprocess(
    _spec: ToolSpec,
    cmd: Sequence[str],
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> CompletedProcess:
    # nosec B603 - cmd is constructed from trusted tool specs (ruff, mypy, etc.)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        env=dict(env) if env is not None else None,
        cwd=cwd,
    )


def _prune_stream_cache(max_age_seconds: int, max_bytes: int) -> dict[str, int]:
    stats = {"files_removed": 0, "bytes_removed": 0}
    if not STREAM_CACHE_DIR.exists():
        return stats
    now = time.time()
    entries: list[tuple[Path, float, int]] = []
    for candidate in STREAM_CACHE_DIR.iterdir():
        if not candidate.is_file():
            continue
        with suppress(OSError):
            metadata = candidate.stat()
            entries.append((candidate, metadata.st_mtime, metadata.st_size))
    if not entries:
        return stats
    entries.sort(key=lambda item: item[1])  # oldest first
    total_size = sum(size for _, _, size in entries)
    to_remove: list[Path] = []
    if max_age_seconds > 0:
        cutoff = now - max_age_seconds
        to_remove.extend(path for path, mtime, _ in entries if mtime < cutoff)
    if max_bytes > 0 and total_size > max_bytes:
        remaining = total_size
        for path, _, file_size in entries:
            if path in to_remove:
                remaining -= file_size
                continue
            to_remove.append(path)
            remaining -= file_size
            if remaining <= max_bytes:
                break
    removed: set[Path] = set(to_remove)
    for path in removed:
        file_size = 0
        with suppress(OSError):
            file_size = path.stat().st_size
        with suppress(OSError):
            path.unlink()
        if file_size:
            stats["bytes_removed"] += file_size
        stats["files_removed"] += 1
    with suppress(OSError):
        if not any(STREAM_CACHE_DIR.iterdir()):
            STREAM_CACHE_DIR.rmdir()
    return stats


def _persist_stream_payload(payload: str, prefix: str) -> Path | None:
    if not payload:
        return None
    safe_prefix = re.sub(r"[^A-Za-z0-9_.-]+", "_", prefix).strip("_") or "stream"
    safe_prefix = (
        (safe_prefix[:32] + "_") if len(safe_prefix) >= 32 else f"{safe_prefix}_"
    )
    try:
        STREAM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            dir=STREAM_CACHE_DIR,
            prefix=safe_prefix,
            suffix=".log",
        ) as handle:
            handle.write(payload)
        return Path(handle.name)
    except OSError:
        return None


def _handle_stream(
    entry: dict[str, Any],
    *,
    data: str | None,
    label: str,
    spec_name: str,
) -> str | None:
    if not data:
        return data
    preview_key = f"{label}_preview"
    _attach_preview(entry, preview_key, data)
    if STREAM_PERSIST_THRESHOLD > 0 and len(data) > STREAM_PERSIST_THRESHOLD:
        persisted = _persist_stream_payload(data, f"{spec_name}_{label}")
        if persisted is not None:
            entry[f"{label}_path"] = persisted.as_posix()
            return ""
    return data


def _remove_directory(path: Path) -> dict[str, int]:
    stats = {"files_removed": 0, "bytes_removed": 0}
    if not path.exists():
        return stats
    for root, _, files in os.walk(path):
        root_path = Path(root)
        for filename in files:
            file_path = root_path / filename
            with suppress(OSError):
                stats["bytes_removed"] += file_path.stat().st_size
                stats["files_removed"] += 1
    shutil.rmtree(path, ignore_errors=True)
    return stats


def clear_cache_state(
    *,
    remove_stream_files: bool = False,
    remove_bootstrap_cache: bool = False,
) -> dict[str, Any]:
    cleared: dict[str, Any] = {
        "tool_cache_entries": 0,
        "stream_files_removed": 0,
        "stream_bytes_removed": 0,
        "bootstrap_bytes_removed": 0,
    }
    with CACHE_LOCK:
        cleared["tool_cache_entries"] = len(CACHE_TOOL_AVAILABILITY)
        CACHE_TOOL_AVAILABILITY.clear()
    ensure_tool_dependencies.cache_clear()
    if remove_stream_files:
        stats = _remove_directory(STREAM_CACHE_DIR)
        cleared["stream_files_removed"] = stats["files_removed"]
        cleared["stream_bytes_removed"] = stats["bytes_removed"]
    if remove_bootstrap_cache and _bootstrap is not None:
        cache_root = getattr(_bootstrap, "CACHE_ROOT", None)
        if isinstance(cache_root, Path):
            stats = _remove_directory(cache_root)
            cleared["bootstrap_bytes_removed"] = stats["bytes_removed"]
    return cleared


def parse_ruff_output(result: CompletedProcess) -> dict[str, Any]:
    try:
        findings = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        payload = {"issues": [], "summary": {"issue_count": 0}}
        _attach_preview(payload, "raw_preview", result.stdout or "")
        return payload

    filtered: list[dict[str, Any]] = []
    for item in findings:
        code = item.get("code")
        filename = item.get("filename") or ""
        if code == "F401" and filename.endswith("__init__.py"):
            # __init__ re-export patterns commonly trigger false positives; skip them.
            continue
        filtered.append(item)
        # TODO: Extract filename from "would reformat <path>" messages and add synthetic issues.

    issues: list[dict[str, Any]] = []
    fixable = sum(1 for item in filtered if item.get("fix"))
    potential_dead_code = sum(
        1 for item in filtered if item.get("code") in {"F401", "F841"}
    )
    for item in filtered[:MAX_ISSUES]:
        location = item.get("location") or {}
        entry = {
            "path": item.get("filename"),
            "line": location.get("row"),
            "column": location.get("column"),
            "code": item.get("code"),
            "message": item.get("message"),
        }
        code = entry.get("code")
        if code in {"F401", "F841"}:
            entry["insight"] = (
                "Unused symbol detected; confirm whether a planned feature was fully implemented."
            )
        _truncate_message(entry)
        issues.append(entry)
    omitted = max(len(filtered) - MAX_ISSUES, 0)
    return {
        "issues": issues,
        "summary": {
            "issue_count": len(filtered),
            "fixable": fixable,
            "potential_dead_code": potential_dead_code,
            **({"omitted_issues": omitted} if omitted else {}),
        },
    }


_MYPY_PATTERN = re.compile(
    r"^(?P<path>[^:]+):(?P<line>\d+): (?:(?P<column>\d+): )?(?P<severity>\w+): "
    r"(?P<message>.*?)(?: \[(?P<code>[\w\-\.]+)\])?$"
)


def parse_mypy_output(result: CompletedProcess) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    notes: list[dict[str, Any]] = []
    for raw_line in (result.stdout or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("Success:"):
            continue
        match = _MYPY_PATTERN.match(line)
        if not match:
            continue
        data = match.groupdict()
        entry: dict[str, Any] = {
            "path": data.get("path"),
            "line": _coerce_int(data.get("line")),
            "message": data.get("message"),
            "severity": (data.get("severity") or "").lower(),
        }
        column = _coerce_int(data.get("column"))
        if column is not None:
            entry["column"] = column
        code = data.get("code")
        if code:
            entry["code"] = code
        _truncate_message(entry)
        target = notes if entry["severity"] == "note" else issues
        target.append(entry)
    trimmed_issues = issues[:MAX_ISSUES]
    trimmed_notes = notes[:MAX_ISSUES]
    summary: dict[str, Any] = {
        "issue_count": len(issues),
        "note_count": len(notes),
    }
    if len(issues) > MAX_ISSUES:
        summary["omitted_issues"] = len(issues) - MAX_ISSUES
    if len(notes) > MAX_ISSUES:
        summary["omitted_notes"] = len(notes) - MAX_ISSUES
    return {
        "issues": trimmed_issues,
        "notes": trimmed_notes,
        "summary": summary,
    }


def parse_pre_commit_output(result: CompletedProcess) -> dict[str, Any]:
    stdout = result.stdout or ""
    issues: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower().endswith("failed") or stripped.endswith("FAIL"):
            hook_name = stripped.split(" ", 1)[0]
            issues.append(
                {
                    "message": stripped,
                    "severity": "error",
                    "code": "pre-commit",
                    "hook": hook_name,
                }
            )
    if result.returncode != 0 and not issues:
        issues.append(
            {
                "message": "pre-commit reported failures; inspect the stdout preview.",
                "severity": "error",
                "code": "pre-commit",
            }
        )
    summary = {"issue_count": len(issues)}
    return {"issues": issues[:MAX_ISSUES], "summary": summary}


def parse_pylint_output(result: CompletedProcess) -> dict[str, Any]:
    payload = result.stdout or ""
    if not payload.strip():
        return {"issues": [], "summary": {"issue_count": 0}}
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        fallback_result: dict[str, Any] = {"issues": [], "summary": {"issue_count": 0}}
        _attach_preview(fallback_result, "raw_preview", payload)
        return fallback_result
    messages: Iterable[dict[str, Any]]
    score: Any = None
    if isinstance(parsed, dict):
        messages = parsed.get("messages", [])
        score = parsed.get("score")
    else:
        messages = parsed
    items = list(messages)
    issues = []
    for message in items[:MAX_ISSUES]:
        entry = {
            "path": message.get("path") or message.get("module"),
            "line": message.get("line"),
            "column": message.get("column"),
            "code": message.get("symbol") or message.get("message-id"),
            "message": message.get("message"),
            "severity": message.get("type"),
        }
        _truncate_message(entry)
        issues.append(entry)
    summary: dict[str, Any] = {"issue_count": len(items)}
    if len(items) > MAX_ISSUES:
        summary["omitted_issues"] = len(items) - MAX_ISSUES
    if score is not None:
        summary["score"] = score
    return {"issues": issues, "summary": summary}


def parse_bandit_output(result: CompletedProcess) -> dict[str, Any]:
    payload = result.stdout or ""
    try:
        parsed = json.loads(payload) if payload else {}
    except json.JSONDecodeError:
        fallback_result: dict[str, Any] = {"issues": [], "summary": {"issue_count": 0}}
        _attach_preview(fallback_result, "raw_preview", payload)
        return fallback_result
    results = parsed.get("results", []) or []
    issues: list[dict[str, Any]] = []
    severity_counts: Counter[str] = Counter()
    confidence_counts: Counter[str] = Counter()
    for finding in results[:MAX_ISSUES]:
        severity = finding.get("issue_severity") or "UNKNOWN"
        confidence = finding.get("issue_confidence") or "UNKNOWN"
        severity_counts[severity] += 1
        confidence_counts[confidence] += 1
        entry = {
            "path": finding.get("filename"),
            "line": finding.get("line_number"),
            "code": finding.get("test_id"),
            "message": finding.get("issue_text"),
            "severity": severity,
            "confidence": confidence,
        }
        _truncate_message(entry)
        issues.append(entry)
    summary: dict[str, Any] = {
        "issue_count": len(results),
        "severity_counts": dict(severity_counts),
        "confidence_counts": dict(confidence_counts),
    }
    if len(results) > MAX_ISSUES:
        summary["omitted_issues"] = len(results) - MAX_ISSUES
    totals = parsed.get("metrics", {}).get("_totals")
    if isinstance(totals, dict):
        summary["metrics"] = {
            key: totals.get(key) for key in ("loc", "nosec", "skipped_tests")
        }
    return {"issues": issues, "summary": summary}


_YAMLLINT_PATTERN = re.compile(
    r"^(?P<path>[^:]+):(?P<line>\d+):(?P<column>\d+): \[(?P<level>[^]]+)\] "
    r"(?P<message>.*?)(?:  \((?P<rule>[^)]+)\))?$"
)


def parse_black_output(result: CompletedProcess) -> dict[str, Any]:
    """Parse black check output (text-based)."""
    issues: list[dict[str, Any]] = []
    # Black uses exit code 1 when files need reformatting
    if result.returncode == 1:
        # Parse "would reformat" messages
        for line in (result.stderr or result.stdout or "").splitlines():
            if "would reformat" in line.lower():
                # Extract filename from "would reformat <path>"
                parts = line.strip().split()
                if len(parts) >= 3:
                    issues.append(
                        {
                            "path": parts[-1],
                            "message": "File needs reformatting",
                            "code": "black-reformat",
                            "fixable": True,
                        }
                    )
    return {
        "issues": issues,
        "summary": {
            "issue_count": len(issues),
            "fixable": len(issues),
        },
    }


def parse_isort_output(result: CompletedProcess) -> dict[str, Any]:
    """Parse isort check output (text-based)."""
    issues: list[dict[str, Any]] = []
    if result.returncode != 0:
        seen_paths: set[str] = set()
        payload = result.stderr or result.stdout or ""
        for line in payload.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            lower = stripped.lower()
            if (
                "imports are incorrectly sorted" not in lower
                and "would reformat" not in lower
            ):
                continue
            candidate: str | None = None
            for token in stripped.replace(",", " ").split():
                normalized = token.strip(":")
                if normalized.endswith(".py"):
                    candidate = normalized
                    break
            if not candidate or candidate in seen_paths:
                continue
            seen_paths.add(candidate)
            issues.append(
                {
                    "path": candidate,
                    "message": "Imports need sorting",
                    "code": "isort-unsorted",
                    "fixable": True,
                }
            )
    return {
        "issues": issues,
        "summary": {
            "issue_count": len(issues),
            "fixable": len(issues),
        },
    }


def parse_yamllint_output(result: CompletedProcess) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    for raw_line in (result.stdout or "").splitlines():
        match = _YAMLLINT_PATTERN.match(raw_line.strip())
        if not match:
            continue
        data = match.groupdict()
        entry: dict[str, Any] = {
            "path": data.get("path"),
            "line": _coerce_int(data.get("line")),
            "column": _coerce_int(data.get("column")),
            "severity": (data.get("level") or "").lower(),
            "message": data.get("message"),
        }
        if data.get("rule"):
            entry["rule"] = data["rule"]
        _truncate_message(entry)
        issues.append(entry)
    trimmed = issues[:MAX_ISSUES]
    summary: dict[str, Any] = {"issue_count": len(issues)}
    if len(issues) > MAX_ISSUES:
        summary["omitted_issues"] = len(issues) - MAX_ISSUES
    return {"issues": trimmed, "summary": summary}


def parse_sqlfluff_output(result: CompletedProcess) -> dict[str, Any]:
    payload = result.stdout or ""
    try:
        parsed = json.loads(payload) if payload else []
    except json.JSONDecodeError:
        fallback_result: dict[str, Any] = {"issues": [], "summary": {"issue_count": 0}}
        _attach_preview(fallback_result, "raw_preview", payload)
        return fallback_result
    issues: list[dict[str, Any]] = []
    files_with_issues = 0
    for entry in parsed:
        violations = entry.get("violations") or []
        if violations:
            files_with_issues += 1
        for violation in violations:
            item = {
                "path": entry.get("filepath"),
                "line": violation.get("start_line_no"),
                "column": violation.get("start_line_pos"),
                "code": violation.get("code"),
                "message": violation.get("description"),
                "warning": bool(violation.get("warning")),
            }
            _truncate_message(item)
            issues.append(item)
            if len(issues) >= MAX_ISSUES:
                break
        if len(issues) >= MAX_ISSUES:
            break
    omitted = max(len(issues) - MAX_ISSUES, 0)
    return {
        "issues": issues,
        "summary": {
            "issue_count": len(issues),
            "files_with_issues": files_with_issues,
            **({"omitted_issues": omitted} if omitted else {}),
        },
    }


def parse_biome_output(result: CompletedProcess) -> dict[str, Any]:
    raw_output = result.stdout or ""
    chunks = [line for line in raw_output.splitlines() if line.strip()]
    objects: list[Mapping[str, Any]] = []
    for line in chunks:
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, Mapping):
            objects.append(parsed)
        elif isinstance(parsed, list):
            objects.extend(item for item in parsed if isinstance(item, Mapping))
    if not objects:
        fallback = {"issues": [], "summary": {"issue_count": 0}}
        _attach_preview(fallback, "raw_preview", raw_output)
        return fallback

    def iter_diagnostics(node: Mapping[str, Any], default_path: str | None = None):
        diagnostics = node.get("diagnostics")
        path = (
            node.get("path")
            or node.get("file_path")
            or node.get("file")
            or default_path
        )
        if isinstance(diagnostics, list):
            for diag in diagnostics:
                if isinstance(diag, Mapping):
                    yield path, diag
        files = node.get("files")
        if isinstance(files, list):
            for entry in files:
                if isinstance(entry, Mapping):
                    yield from iter_diagnostics(entry, entry.get("path") or path)

    issues: list[dict[str, Any]] = []
    severity_counts: Counter[str] = Counter()
    potential_dead_code = 0

    for obj in objects:
        for path, diag in iter_diagnostics(obj):
            severity = str(
                diag.get("severity") or diag.get("category") or "unknown"
            ).lower()
            severity_counts[severity] += 1
            span = diag.get("span") or diag.get("location") or {}
            start = span.get("start") if isinstance(span, Mapping) else {}
            line_number = _coerce_int(
                start.get("line") if isinstance(start, Mapping) else None
            )
            column_number = _coerce_int(
                start.get("column") if isinstance(start, Mapping) else None
            )
            code = diag.get("code") or diag.get("rule")
            normalized_code = None
            if isinstance(code, str):
                normalized_code = code.split("/")[-1]
            elif code is not None:
                normalized_code = str(code)

            message = diag.get("message") or diag.get("description") or ""
            fixable = bool(diag.get("fixable") or diag.get("actions"))

            record: dict[str, Any] = {
                "path": path,
                "line": line_number,
                "column": column_number,
                "code": code,
                "message": message,
                "severity": severity,
            }
            if fixable:
                record["fixable"] = True

            if normalized_code in {"noUnusedVariables", "noUnusedImports"}:
                record["insight"] = (
                    "Biome detected unused symbols; evaluate refactoring or removal to reduce dead code."
                )
                potential_dead_code += 1

            _truncate_message(record)
            issues.append(record)
            if len(issues) >= MAX_ISSUES:
                break
        if len(issues) >= MAX_ISSUES:
            break

    omitted = max(len(issues) - MAX_ISSUES, 0)
    summary: dict[str, Any] = {
        "issue_count": len(issues),
        "severity_counts": dict(severity_counts),
    }
    if omitted:
        summary["omitted_issues"] = omitted
    if potential_dead_code:
        summary["potential_dead_code"] = potential_dead_code
    return {"issues": issues[:MAX_ISSUES], "summary": summary}


def parse_trunk_output(result: CompletedProcess) -> dict[str, Any]:
    raw_output = result.stdout or ""
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError:
        fallback = {"issues": [], "summary": {"issue_count": 0}}
        _attach_preview(fallback, "raw_preview", raw_output)
        return fallback

    if isinstance(parsed, dict):
        findings = parsed.get("results")
        if not isinstance(findings, list):
            findings = []
    elif isinstance(parsed, list):
        findings = parsed
    else:
        findings = []

    issues: list[dict[str, Any]] = []
    severity_counts: Counter[str] = Counter()
    potential_dead_code = 0

    for entry in findings[:MAX_ISSUES]:
        if not isinstance(entry, Mapping):
            continue
        severity = str(entry.get("severity") or entry.get("level") or "unknown").lower()
        severity_counts[severity] += 1

        location = entry.get("location")
        path = None
        line = None
        column = None
        if isinstance(location, Mapping):
            path = location.get("path") or location.get("file")
            line = location.get("line") or location.get("start_line")
            column = location.get("column") or location.get("start_column")
        if path is None:
            path = entry.get("path") or entry.get("file")
        if line is None:
            line = entry.get("line")
        if column is None:
            column = entry.get("column")

        code = entry.get("check_id") or entry.get("rule") or entry.get("code")
        normalized_code = None
        if isinstance(code, str):
            normalized_code = code.split("/")[-1]
        elif code is not None:
            normalized_code = str(code)
        message = entry.get("message") or entry.get("description") or ""
        source = entry.get("linter") or entry.get("tool") or entry.get("origin")

        record: dict[str, Any] = {
            "path": path,
            "line": _coerce_int(line),
            "column": _coerce_int(column),
            "code": code,
            "message": message,
            "severity": severity,
        }
        if source:
            record["source"] = str(source)

        if normalized_code in {"F401", "F841", "RUF100"}:
            record["insight"] = (
                "Unused symbol reported via Trunk; verify whether the related code should be refactored or removed."
            )
            potential_dead_code += 1

        _truncate_message(record)
        issues.append(record)

    omitted = max(len(findings) - MAX_ISSUES, 0)
    summary: dict[str, Any] = {
        "issue_count": len(findings),
        "severity_counts": dict(severity_counts),
    }
    if omitted:
        summary["omitted_issues"] = omitted
    if potential_dead_code:
        summary["potential_dead_code"] = potential_dead_code
    return {"issues": issues, "summary": summary}


PARSER_REGISTRY: dict[str, Callable[[CompletedProcess], dict[str, Any]]] = {
    "ruff": parse_ruff_output,
    "mypy": parse_mypy_output,
    "pylint": parse_pylint_output,
    "bandit": parse_bandit_output,
    "yamllint": parse_yamllint_output,
    "sqlfluff": parse_sqlfluff_output,
    "trunk": parse_trunk_output,
    "biome": parse_biome_output,
    "pre-commit": parse_pre_commit_output,
}


def _trunk_command() -> tuple[list[str], Mapping[str, str] | None, Path | None]:
    cmd = ["trunk", "check", "--no-progress", "--output=json"]
    extra = os.getenv(TRUNK_ENV_VAR)
    if extra:
        cmd.extend(extra.split())
    return cmd, None, None


def _mypy_command() -> tuple[list[str], Mapping[str, str] | None, Path | None]:
    """Build mypy command with proper stub paths for ephemeral runners."""
    repo_root = Path(__file__).resolve().parents[1]
    stubs_path = repo_root / "stubs"
    third_party_path = stubs_path / "third_party"

    # Build MYPYPATH to include stubs
    mypypath_parts = []
    if third_party_path.exists():
        mypypath_parts.append(str(third_party_path))
    if stubs_path.exists():
        mypypath_parts.append(str(stubs_path))

    env_override = None
    if mypypath_parts:
        env = os.environ.copy()
        existing_mypypath = env.get("MYPYPATH", "")
        if existing_mypypath:
            mypypath_parts.append(existing_mypypath)
        env["MYPYPATH"] = ":".join(mypypath_parts)
        env_override = env

    cmd = [
        "mypy",
        ".",
        "--no-pretty",
        "--show-error-codes",
        "--hide-error-context",
        "--no-error-summary",
    ]
    return cmd, env_override, None


def _iter_builtin_tool_specs(env: Mapping[str, str]) -> Iterable[ToolSpec]:
    yield ToolSpec(
        name="ruff",
        command=_static_command("ruff", "check", ".", "--output-format", "json"),
        parser=parse_ruff_output,
        autofix=(
            ("poetry", "run", "ruff", "check", ".", "--fix"),
            ("ruff", "check", ".", "--fix"),
        ),
    )
    yield ToolSpec(
        name="black",
        command=_static_command("black", ".", "--check"),
        parser=parse_black_output,
        autofix=(
            ("poetry", "run", "black", "."),
            ("black", "."),
        ),
        optional=True,
    )
    yield ToolSpec(
        name="isort",
        command=_static_command("isort", ".", "--check-only"),
        parser=parse_isort_output,
        autofix=(
            ("poetry", "run", "isort", "."),
            ("isort", "."),
        ),
        optional=True,
    )
    yield ToolSpec(
        name="mypy",
        command=_mypy_command,
        parser=parse_mypy_output,
    )
    yield ToolSpec(
        name="yamllint",
        command=_static_command("yamllint", "--format", "parsable", "."),
        parser=parse_yamllint_output,
    )
    if _truthy(env.get("ENABLE_PYLINT")):
        yield ToolSpec(
            name="pylint",
            command=_static_command(
                "pylint",
                "watercrawl",
                "app",
                "scripts",
                "tests",
                "--output-format=json",
                "--score=n",
            ),
            parser=parse_pylint_output,
            optional=True,
        )
    if BANDIT_AVAILABLE:
        yield ToolSpec(
            name="bandit",
            command=_static_command("bandit", "-r", "watercrawl", "-f", "json"),
            parser=parse_bandit_output,
        )
    if SQLFLUFF_AVAILABLE:
        yield ToolSpec(
            name="sqlfluff",
            command=_sqlfluff_command,
            parser=parse_sqlfluff_output,
        )
    yield ToolSpec(
        name="trunk",
        command=_trunk_command,
        parser=parse_trunk_output,
        optional=True,
        autofix=(("trunk", "fmt"),),
    )
    yield ToolSpec(
        name="biome",
        command=_static_command("npx", "biome", "check", "--reporter", "json"),
        parser=parse_biome_output,
        optional=True,
        autofix=(
            (
                "npx",
                "biome",
                "check",
                "--apply",
                "--reporter",
                "json",
            ),
        ),
    )


def _coerce_command(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(part) for part in value]
    if isinstance(value, str):
        return [value]
    raise ValueError(f"Unsupported command specification: {value!r}")


def _enable_from_config(entry: Mapping[str, Any], env: Mapping[str, str]) -> bool:
    if not entry.get("enabled", True):
        return False
    enable_vars = entry.get("enable_if_env") or []
    disable_vars = entry.get("disable_if_env") or []
    if not isinstance(enable_vars, Iterable) or isinstance(enable_vars, (str, bytes)):
        enable_vars = [enable_vars]  # type: ignore[list-item]
    if not isinstance(disable_vars, Iterable) or isinstance(disable_vars, (str, bytes)):
        disable_vars = [disable_vars]  # type: ignore[list-item]
    for var in enable_vars:
        if isinstance(var, str):
            if not _truthy(env.get(var)):
                return False
    for var in disable_vars:
        if isinstance(var, str):
            if _truthy(env.get(var)):
                return False
    return True


def _iter_configured_tool_specs(
    path: Path, env: Mapping[str, str]
) -> Iterable[ToolSpec]:
    if not path.exists():
        return
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, TOMLDecodeError) as exc:  # pragma: no cover - config parse issues
        print(f"Warning: failed to parse {path}: {exc}", file=sys.stderr)
        return
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return
    for entry in tools:
        if not isinstance(entry, Mapping):
            continue
        name = entry.get("name")
        parser_key = entry.get("parser")
        command_value = entry.get("command")
        if not name or not parser_key or not command_value:
            continue
        if not _enable_from_config(entry, env):
            continue
        parser = PARSER_REGISTRY.get(str(parser_key))
        if parser is None:
            continue
        try:
            command = _coerce_command(command_value)
        except ValueError:
            continue
        env_override = entry.get("env")
        env_mapping: Mapping[str, str] | None = None
        if isinstance(env_override, Mapping):
            env_mapping = {str(key): str(value) for key, value in env_override.items()}
        cwd = entry.get("cwd")
        autofix_entries = entry.get("autofix")
        autofix_commands: list[tuple[str, ...]] = []
        if isinstance(autofix_entries, (list, tuple)):
            for item in autofix_entries:
                try:
                    coerced = _coerce_command(item)
                except ValueError:
                    continue
                autofix_commands.append(tuple(coerced))
        elif autofix_entries:
            try:
                coerced = _coerce_command(autofix_entries)
            except ValueError:
                coerced = None
            if coerced:
                autofix_commands.append(tuple(coerced))
        spec = ToolSpec(
            name=str(name),
            command=_configured_command(command, env=env_mapping, cwd=cwd),
            parser=parser,
            optional=bool(entry.get("optional", False)),
            autofix=tuple(autofix_commands),
        )
        yield spec


def build_tool_registry(
    *,
    env: Mapping[str, str] | None = None,
    config_path: Path = TOOLS_CONFIG_PATH,
) -> ToolRegistry:
    env_mapping = dict(env) if env is not None else dict(os.environ)
    registry = ToolRegistry()
    registry.extend(_iter_builtin_tool_specs(env_mapping))
    registry.extend(_iter_configured_tool_specs(config_path, env_mapping), replace=True)
    return registry


def collect(
    *,
    tools: Sequence[ToolSpec] | None = None,
    runner: (
        Callable[
            [ToolSpec, Sequence[str], Mapping[str, str] | None, Path | None],
            CompletedProcess,
        ]
        | None
    ) = None,
) -> list[dict[str, Any]]:
    if tools is None:
        specs = list(build_tool_registry().values())
    else:
        specs = list(tools)
    run = runner or _run_subprocess

    preflight_results: list[dict[str, Any]] = []
    for tool in CORE_TOOLCHAIN:
        try:
            ensure_tool_dependencies(tool)
        except BootstrapError as exc:
            preflight_results.append(
                {
                    "tool": tool,
                    "status": "provision_failed",
                    "summary": {"issue_count": 0},
                    "issues": [],
                    "error": _truncate(str(exc)),
                }
            )

    def _execute_tool_spec(index: int, spec: ToolSpec) -> tuple[int, dict[str, Any]]:
        start_time = datetime.now(timezone.utc)
        try:
            ensure_tool_dependencies(spec.name)
        except BootstrapError as exc:
            return (
                index,
                {
                    "tool": spec.name,
                    "status": "provision_failed",
                    "summary": {"issue_count": 0},
                    "issues": [],
                    "error": _truncate(str(exc)),
                },
            )

        try:
            cmd, env, cwd = spec.command()
        except Exception as exc:  # pragma: no cover - defensive guard
            return (
                index,
                {
                    "tool": spec.name,
                    "status": "failed_to_prepare",
                    "error": _truncate(str(exc)),
                    "summary": {"issue_count": 0},
                    "issues": [],
                },
            )

        primary_cmd = cmd[0] if cmd else None
        should_check_tool = run is _run_subprocess
        if should_check_tool and primary_cmd and not _check_tool_available(primary_cmd):
            status = "not_installed" if spec.optional else "not_available"
            return (
                index,
                {
                    "tool": spec.name,
                    "status": status,
                    "summary": {"issue_count": 0},
                    "issues": [],
                    "error": (
                        f"Tool '{primary_cmd}' is not available in PATH after provisioning."
                        " Install dependencies with: PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1"
                        " poetry install --no-root --with dev"
                    ),
                },
            )

        try:
            completed = run(spec, cmd, env, cwd)
        except FileNotFoundError as exc:
            return (
                index,
                {
                    "tool": spec.name,
                    "status": "not_installed" if spec.optional else "failed",
                    "summary": {"issue_count": 0},
                    "issues": [],
                    "error": str(exc),
                },
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            return (
                index,
                {
                    "tool": spec.name,
                    "status": "failed",
                    "summary": {"issue_count": 0},
                    "issues": [],
                    "error": _truncate(str(exc)),
                },
            )

        duration_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()
        parsed = spec.parser(completed)
        status = (
            "completed" if completed.returncode == 0 else "completed_with_exit_code"
        )
        result_entry: dict[str, Any] = {
            "tool": spec.name,
            "status": status,
            "returncode": completed.returncode,
            "duration_seconds": round(duration_seconds, 3),
        }
        result_entry.update(parsed)
        existing_issues = result_entry.get("issues")
        if isinstance(existing_issues, list):
            issues_list = existing_issues
        elif existing_issues is None:
            issues_list = []
            result_entry["issues"] = issues_list
        else:
            issues_list = list(existing_issues)
            result_entry["issues"] = issues_list
        summary_obj = result_entry.get("summary")
        if isinstance(summary_obj, dict):
            summary_block: dict[str, Any] = summary_obj
        else:
            summary_block = {}
            result_entry["summary"] = summary_block
        if completed.returncode != 0:
            if summary_block.get("issue_count", 0) == 0:
                issues_list.append(
                    {
                        "message": (
                            f"{spec.name} exited with status {completed.returncode}"
                            " but did not report any findings."
                        ),
                        "severity": "error",
                        "code": "tool_exit_non_zero",
                        "tool": spec.name,
                    }
                )
                summary_block["issue_count"] = 1
                severity_counts = summary_block.setdefault("severity_counts", {})
                if not isinstance(severity_counts, dict):
                    severity_counts = {}
                    summary_block["severity_counts"] = severity_counts
                severity_counts["error"] = severity_counts.get("error", 0) + 1
        warnings, omitted_warnings = _extract_warnings(
            completed.stdout, completed.stderr
        )
        stdout_after = _handle_stream(
            result_entry,
            data=completed.stdout,
            label="stdout",
            spec_name=spec.name,
        )
        if stdout_after is not None:
            completed.stdout = stdout_after
        stderr_after = _handle_stream(
            result_entry,
            data=completed.stderr,
            label="stderr",
            spec_name=spec.name,
        )
        if stderr_after is not None:
            completed.stderr = stderr_after
        if warnings:
            result_entry["warnings"] = list(warnings)
        if spec.autofix:
            result_entry["autofix_commands"] = [
                shlex.join(value) for value in spec.autofix
            ]
        if warnings or omitted_warnings:
            summary_obj = result_entry.get("summary")
            if isinstance(summary_obj, dict):
                summary_block = summary_obj
            else:
                summary_block = {}
                result_entry["summary"] = summary_block
            summary_block["warning_count"] = (
                summary_block.get("warning_count", 0) + len(warnings) + omitted_warnings
            )
            if omitted_warnings:
                summary_block["omitted_warnings"] = (
                    summary_block.get("omitted_warnings", 0) + omitted_warnings
                )
        return index, result_entry

    if not specs:
        aggregated = preflight_results
    else:
        results: list[tuple[int, dict[str, Any]]] = []
        max_workers = min(MAX_PARALLELISM, max(1, len(specs)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(_execute_tool_spec, idx, spec): idx
                for idx, spec in enumerate(specs)
            }
            for future in as_completed(future_map):
                try:
                    results.append(future.result())
                except (
                    Exception
                ) as exc:  # pragma: no cover - guard against executor errors
                    idx = future_map[future]
                    results.append(
                        (
                            idx,
                            {
                                "tool": specs[idx].name,
                                "status": "failed",
                                "summary": {"issue_count": 0},
                                "issues": [],
                                "error": _truncate(str(exc)),
                            },
                        )
                    )
        results.sort(key=lambda item: item[0])
        aggregated = [entry for _, entry in results]

    aggregated = preflight_results + aggregated
    aggregated = _expand_trunk_results(aggregated)
    if tools is None:
        aggregated.extend(_collect_vscode_problems_fallback(dict(os.environ)))
    return aggregated


def _autofix_command_map(registry: ToolRegistry) -> dict[str, list[list[str]]]:
    mapping: dict[str, list[list[str]]] = {}
    for spec in registry.values():
        commands: list[list[str]] = [list(cmd) for cmd in spec.autofix]
        if not commands:
            fallback = AUTOFIX_COMMANDS.get(spec.name)
            if fallback:
                commands.append(list(fallback))
        if commands:
            mapping[spec.name] = commands
    return mapping


def _expand_trunk_results(results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for entry in results:
        if entry.get("tool") != "trunk":
            expanded.append(dict(entry))
            continue
        expanded.extend(_split_trunk_entry(entry))
    return expanded


def _split_trunk_entry(entry: Mapping[str, Any]) -> list[dict[str, Any]]:
    issues = entry.get("issues") or []
    if not isinstance(issues, list):
        issues = []
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in issues:
        if not isinstance(item, Mapping):
            continue
        source = str(item.get("source") or "unknown")
        grouped[source].append(dict(item))
    if not grouped:
        clean_entry = dict(entry)
        clean_entry["tool"] = "trunk"
        clean_entry.setdefault("summary", {"issue_count": 0})
        clean_entry.setdefault("issues", [])
        return [clean_entry]
    omitted = entry.get("summary", {}).get("omitted_issues")
    base_notes = list(entry.get("notes") or [])
    if omitted:
        base_notes = list(base_notes)
        base_notes.append(
            {
                "message": f"Trunk reported {omitted} additional issues beyond the first {MAX_ISSUES}.",
                "severity": "info",
            }
        )
    expanded_entries: list[dict[str, Any]] = []
    for source, items in sorted(grouped.items()):
        severity_counts = Counter(
            str(item.get("severity") or "unknown")
            for item in items
            if item.get("severity")
        )
        summary: dict[str, Any] = {"issue_count": len(items)}
        if severity_counts:
            summary["severity_counts"] = dict(severity_counts)
        expanded_entry: dict[str, Any] = {
            "tool": f"trunk:{source}",
            "status": entry.get("status", "completed"),
            "returncode": entry.get("returncode", 0),
            "issues": items,
            "summary": summary,
        }
        if base_notes:
            expanded_entry["notes"] = list(base_notes)
        if entry.get("stderr_preview"):
            expanded_entry["stderr_preview"] = entry["stderr_preview"]
        if entry.get("autofix_commands"):
            expanded_entry["autofix_commands"] = entry["autofix_commands"]
        expanded_entries.append(expanded_entry)
    return expanded_entries


_VSCODE_SEVERITY_MAP = {
    1: "error",
    2: "warning",
    4: "info",
    8: "hint",
}


def _collect_vscode_problems_fallback(env: Mapping[str, str]) -> list[dict[str, Any]]:
    path_value = env.get(VSCODE_PROBLEMS_ENV)
    if not path_value:
        return []
    path = Path(path_value).expanduser()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - fallback for parse errors
        print(
            f"Warning: failed to parse VS Code problems export {path}: {exc}",
            file=sys.stderr,
        )
        return []
    markers = _extract_vscode_markers(payload)
    if not markers:
        return []
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for marker in markers:
        issue = _marker_to_issue(marker)
        source = str(issue.pop("source") or "vscode")
        issue["source"] = source
        grouped[source].append(issue)
    entries: list[dict[str, Any]] = []
    for source, issues in sorted(grouped.items()):
        severity_counts = Counter(
            str(issue.get("severity")) for issue in issues if issue.get("severity")
        )
        summary: dict[str, Any] = {"issue_count": len(issues)}
        if severity_counts:
            summary["severity_counts"] = dict(severity_counts)
        entries.append(
            {
                "tool": f"vscode:{source}",
                "status": "collected",
                "returncode": 0,
                "issues": issues,
                "summary": summary,
            }
        )
    return entries


def _extract_vscode_markers(payload: Any) -> list[Mapping[str, Any]]:
    candidates: list[Mapping[str, Any]] = []
    if isinstance(payload, list):
        candidates = [item for item in payload if isinstance(item, Mapping)]
    elif isinstance(payload, Mapping):
        for key in ("problems", "markers", "items", "diagnostics"):
            value = payload.get(key)
            if isinstance(value, list):
                candidates = [item for item in value if isinstance(item, Mapping)]
                if candidates:
                    break
        else:
            if payload.get("message"):
                candidates = [payload]
    return candidates


def _marker_to_issue(marker: Mapping[str, Any]) -> dict[str, Any]:
    severity = marker.get("severity")
    severity_label: str | None = None
    if isinstance(severity, int):
        mapped = _VSCODE_SEVERITY_MAP.get(severity)
        if mapped is not None:
            severity_label = mapped
        else:
            severity_label = str(severity)
    else:
        severity_label = str(severity).lower() if severity else None
    path, line, column = _parse_vscode_location(marker)
    code = marker.get("code")
    if isinstance(code, Mapping):
        code = code.get("value") or code.get("id") or code.get("name")
    issue: dict[str, Any] = {
        "path": path,
        "line": _coerce_int(line),
        "column": _coerce_int(column),
        "code": code,
        "message": marker.get("message"),
        "severity": str(severity_label) if severity_label is not None else None,
        "source": marker.get("source") or marker.get("owner") or "vscode",
    }
    _truncate_message(issue)
    return issue


def _parse_vscode_location(
    marker: Mapping[str, Any],
) -> tuple[str | None, int | None, int | None]:
    location = marker.get("location") or marker.get("resource")
    path: str | None = None
    line: int | None = None
    column: int | None = None
    if isinstance(location, Mapping):
        uri = location.get("uri") or location.get("url")
        path = location.get("path") or location.get("file") or location.get("fsPath")
        if isinstance(uri, str) and uri.startswith("file:"):
            parsed = urlparse(uri)
            path = unquote(parsed.path)
        elif isinstance(uri, str) and not path:
            path = uri
        if not path:
            resource = location.get("path") or location.get("fsPath")
            if isinstance(resource, str):
                path = resource
        range_block = location.get("range")
        if isinstance(range_block, Mapping):
            start = range_block.get("start") or range_block.get("startLineNumber")
            if isinstance(start, Mapping):
                line = start.get("line") or start.get("lineNumber")
                column = start.get("character") or start.get("column")
            else:
                line = range_block.get("startLineNumber") or range_block.get(
                    "startLine"
                )
                column = range_block.get("startColumn")
        else:
            line = location.get("line") or location.get("lineNumber")
            column = location.get("character") or location.get("column")
    elif isinstance(location, str):
        path = location
    if path:
        path = Path(path).as_posix()
    return path, _coerce_int(line), _coerce_int(column)


def build_overall_summary(
    results: Sequence[Mapping[str, Any]],
    autofixes: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    issue_total = 0
    note_total = 0
    fixable_total = 0
    dead_code_total = 0
    severity_total: Counter[str] = Counter()
    tools_run: list[str] = []
    tools_missing: list[str] = []
    tools_not_available: list[str] = []
    highlight_insights: list[dict[str, Any]] = []
    warning_total = 0
    warning_highlights: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []

    # Track ephemeral runner compatibility
    repo_root = Path(__file__).resolve().parents[1]
    stubs_available = (repo_root / "stubs").exists()

    def _add_action(action: dict[str, Any]) -> None:
        actions.append(action)

    for entry in results:
        tool = entry.get("tool")
        status = entry.get("status")
        if status == "not_installed" and tool:
            tools_missing.append(tool)
            continue
        if status == "not_available" and tool:
            tools_not_available.append(tool)
            continue
        if tool:
            tools_run.append(tool)
        summary = entry.get("summary") or {}
        issue_total += summary.get("issue_count", 0)
        note_total += summary.get("note_count", 0)
        dead_code_total += summary.get("potential_dead_code", 0)
        severity_total.update(summary.get("severity_counts", {}))
        declared_warning_count = summary.get("warning_count")

        issues = entry.get("issues") or []
        for issue in issues:
            if issue.get("fixable"):
                fixable_total += 1
            insight = issue.get("insight")
            if insight and len(highlight_insights) < 10:
                highlight_insights.append(
                    {
                        "tool": tool,
                        "path": issue.get("path"),
                        "line": issue.get("line"),
                        "code": issue.get("code"),
                        "insight": insight,
                    }
                )
        if summary.get("issue_count", 0) > 0 and tool:
            autofix_cmds = entry.get("autofix_commands") or []
            if autofix_cmds:
                _add_action(
                    {
                        "type": "autofix",
                        "tool": tool,
                        "command": autofix_cmds[0],
                    }
                )
            else:
                _add_action({"type": "review", "tool": tool})

        warnings = entry.get("warnings") or []
        if isinstance(declared_warning_count, int):
            warning_total += declared_warning_count
        else:
            warning_total += len(warnings)
        for warning in warnings:
            if len(warning_highlights) >= WARNING_HIGHLIGHT_LIMIT:
                break
            warning_highlights.append(
                {
                    "tool": tool,
                    "message": warning.get("message"),
                    "category": warning.get("category"),
                    "kind": warning.get("kind"),
                    "path": warning.get("path"),
                    "source": warning.get("source"),
                }
            )

    summary_payload: dict[str, Any] = {
        "issue_count": issue_total,
        "note_count": note_total,
        "fixable_count": fixable_total,
        "potential_dead_code": dead_code_total,
        "severity_counts": dict(severity_total),
        "tools_run": tools_run,
        "tools_missing": tools_missing,
        "insights": highlight_insights,
        "warning_count": warning_total,
        "warning_insights": warning_highlights,
    }
    # Add guidance for unavailable tools
    if tools_not_available:
        summary_payload["tools_not_available"] = tools_not_available
        summary_payload.setdefault("setup_guidance", []).append(
            {
                "issue": "Required QA tools not available",
                "tools": tools_not_available,
                "solution": (
                    "Install dependencies with: PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 "
                    "poetry install --no-root --with dev"
                ),
                "alternative": "Or use Python directly: python3 -m pip install ruff mypy black isort bandit yamllint",
            }
        )

    # Add performance diagnostics for ephemeral runner optimization
    tool_durations = {
        entry["tool"]: entry.get("duration_seconds", 0)
        for entry in results
        if entry.get("duration_seconds") is not None
    }
    if tool_durations:
        total_duration = sum(tool_durations.values())
        slowest_tools = sorted(
            tool_durations.items(), key=lambda x: x[1], reverse=True
        )[:5]
        summary_payload["performance"] = {
            "total_duration_seconds": round(total_duration, 3),
            "slowest_tools": [
                {"tool": tool, "duration_seconds": duration}
                for tool, duration in slowest_tools
            ],
        }

    if warning_total:
        _add_action({"type": "warnings", "count": warning_total})
    for missing_tool in tools_missing:
        _add_action({"type": "missing_tool", "tool": missing_tool})
    for unavailable_tool in tools_not_available:
        _add_action({"type": "install_required", "tool": unavailable_tool})
    configured_tools: dict[str, Any] = {}
    trunk_linters = _discover_trunk_linters()
    if trunk_linters:
        configured_tools["trunk_enabled"] = trunk_linters
        if "trunk" not in tools_run:
            configured_tools.setdefault("missing", []).append("trunk")
            _add_action({"type": "run_tool", "tool": "trunk"})
    biome_present = _discover_biome_presence()
    if biome_present:
        configured_tools["biome_present"] = True
        if "biome" not in tools_run:
            configured_tools.setdefault("missing", []).append("biome")
            _add_action({"type": "run_tool", "tool": "biome"})
    if configured_tools:
        summary_payload["configured_tools"] = configured_tools

    # Add ephemeral runner guidance
    if stubs_available:
        summary_payload["stubs_available"] = True
        if "mypy" in tools_run:
            summary_payload.setdefault("ephemeral_runner_notes", []).append(
                "Type stubs are properly configured for mypy via MYPYPATH"
            )
    else:
        summary_payload["stubs_available"] = False
        _add_action(
            {
                "type": "warning",
                "message": "Type stubs directory not found; mypy may report false positives",
            }
        )

    if autofixes:
        attempted = len(autofixes)
        succeeded = sum(1 for entry in autofixes if entry.get("status") == "succeeded")
        failed = sum(1 for entry in autofixes if entry.get("status") == "failed")
        unsupported = sum(
            1 for entry in autofixes if entry.get("status") == "unsupported"
        )
        summary_payload["autofix"] = {
            "attempted": attempted,
            "succeeded": succeeded,
            "failed": failed,
            "unsupported": unsupported,
        }
        if failed:
            for entry in autofixes:
                if entry.get("status") == "failed":
                    _add_action(
                        {
                            "type": "autofix_failed",
                            "tool": entry.get("tool"),
                            "command": " ".join(entry.get("command", [])),
                        }
                    )
    if actions:
        summary_payload["actions"] = actions
    return summary_payload


def write_report(
    results: Sequence[dict[str, Any]],
    *,
    autofixes: Sequence[Mapping[str, Any]] | None = None,
    output_path: Path = REPORT_PATH,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": build_overall_summary(results, autofixes),
        "tools": list(results),
        "autofixes": list(autofixes or []),
    }
    if metadata:
        payload["metadata"] = dict(metadata)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return None


def _run_autofix_command(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603 - commands are predefined tool invocations
        cmd,
        check=False,
        capture_output=True,
        text=True,
    )


def run_autofixes(
    tools: Sequence[str] | None = None,
    runner: Callable[
        [Sequence[str]], subprocess.CompletedProcess[str]
    ] = _run_autofix_command,
) -> list[dict[str, Any]]:
    registry = build_tool_registry()
    autofix_map = _autofix_command_map(registry)
    selected_names = list(dict.fromkeys(tools or autofix_map.keys()))
    results: list[dict[str, Any]] = []
    for tool in selected_names:
        commands = autofix_map.get(tool)
        if not commands:
            results.append({"tool": tool, "status": "unsupported"})
            continue
        command_results: list[dict[str, Any]] = []
        failure = False
        for command in commands:
            process = runner(command)
            command_entry: dict[str, Any] = {
                "command": list(command),
                "returncode": process.returncode,
            }
            _attach_preview(command_entry, "stdout_preview", process.stdout)
            _attach_preview(command_entry, "stderr_preview", process.stderr)
            if process.returncode != 0:
                failure = True
            command_results.append(command_entry)
        entry: dict[str, Any] = {
            "tool": tool,
            "status": "failed" if failure else "succeeded",
            "returncode": command_results[-1]["returncode"],
            "commands": command_results,
            "command": command_results[0]["command"],
        }
        results.append(entry)
    return results


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect lint/type-check results into problems_report.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPORT_PATH,
        help=f"Write report to this path (default: {REPORT_PATH})",
    )
    parser.add_argument(
        "--autofix",
        action="store_true",
        help="Attempt to run autofix commands for supported tools before collection.",
    )
    parser.add_argument(
        "--autofix-tool",
        action="append",
        dest="autofix_tools",
        help="Limit autofix to specific tools (can be repeated).",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print a quick summary to stdout after generating the report.",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear cached tool metadata and persisted stream logs before execution.",
    )
    parser.add_argument(
        "--clear-bootstrap-cache",
        action="store_true",
        help="When used with --clear-cache, also delete the vendored bootstrap cache.",
    )
    parser.add_argument(
        "--profile-memory",
        action="store_true",
        help="Capture tracemalloc statistics during the run and store them in the report metadata.",
    )
    parser.add_argument(
        "--memory-profile-limit",
        type=int,
        default=10,
        help="Number of top allocation entries to include when --profile-memory is enabled (default: 10).",
    )
    parser.add_argument(
        "--tool-cache-ttl",
        type=int,
        help="Override the tool availability cache TTL in seconds (0 disables caching).",
    )
    return parser.parse_args(argv)


def print_summary(report_path: Path) -> None:
    """Print a human-readable summary of the problems report."""
    try:
        with report_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error reading report: {exc}", file=sys.stderr)
        return

    summary = data.get("summary", {})
    print("\n" + "=" * 70)
    print("PROBLEMS REPORT SUMMARY")
    print("=" * 70)

    issue_count = summary.get("issue_count", 0)
    fixable = summary.get("fixable_count", 0)
    dead_code = summary.get("potential_dead_code", 0)

    print(f"\nIssues found: {issue_count}")
    if fixable:
        print(f"  - Fixable: {fixable}")
    if dead_code:
        print(f"  - Potential dead code: {dead_code}")

    tools_run = summary.get("tools_run", [])
    tools_missing = summary.get("tools_missing", [])
    tools_not_available = summary.get("tools_not_available", [])

    if tools_run:
        print(f"\nTools executed successfully: {', '.join(tools_run)}")
    if tools_not_available:
        print(
            f"\nTools not available (need installation): {', '.join(tools_not_available)}"
        )
    if tools_missing:
        print(f"\nOptional tools missing: {', '.join(tools_missing)}")

    setup_guidance = summary.get("setup_guidance", [])
    if setup_guidance:
        print("\n" + "-" * 70)
        print("SETUP GUIDANCE")
        print("-" * 70)
        for guide in setup_guidance:
            print(f"\nIssue: {guide.get('issue')}")
            print(f"Tools affected: {', '.join(guide.get('tools', []))}")
            print(f"Solution: {guide.get('solution')}")
            alternative = guide.get("alternative")
            if alternative:
                print(f"Alternative: {alternative}")

    actions = summary.get("actions", [])
    autofix_actions = [action for action in actions if action.get("type") == "autofix"]
    if autofix_actions:
        print("\n" + "-" * 70)
        print("AUTOFIX COMMANDS AVAILABLE")
        print("-" * 70)
        for action in autofix_actions:
            print(f"\n{action.get('tool')}: {action.get('command')}")

    perf = summary.get("performance", {})
    if perf:
        total = perf.get("total_duration_seconds", 0)
        print(f"\nTotal execution time: {total:.2f}s")

    print("\n" + "=" * 70)
    print(f"Full report: {report_path}")
    print("=" * 70 + "\n")


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    metadata: dict[str, Any] = {}
    config_meta: dict[str, Any] = {
        "stream_cache_dir": STREAM_CACHE_DIR.as_posix(),
        "stream_cache_threshold": STREAM_PERSIST_THRESHOLD,
        "stream_cache_max_age": STREAM_CACHE_MAX_AGE,
        "stream_cache_max_bytes": STREAM_CACHE_MAX_BYTES,
    }

    global TOOL_CACHE_TTL_SECONDS
    if args.tool_cache_ttl is not None:
        TOOL_CACHE_TTL_SECONDS = max(0, args.tool_cache_ttl)
    config_meta["tool_cache_ttl_seconds"] = TOOL_CACHE_TTL_SECONDS

    cache_reset_stats: dict[str, Any] | None = None
    if args.clear_cache:
        cache_reset_stats = clear_cache_state(
            remove_stream_files=True,
            remove_bootstrap_cache=args.clear_bootstrap_cache,
        )
        metadata["cleared_caches"] = cache_reset_stats

    if STREAM_CACHE_MAX_AGE > 0 or STREAM_CACHE_MAX_BYTES > 0:
        prune_stats = _prune_stream_cache(STREAM_CACHE_MAX_AGE, STREAM_CACHE_MAX_BYTES)
        metadata["stream_cache_prune"] = prune_stats

    start_snapshot = None
    if args.profile_memory:
        tracemalloc.start()
        start_snapshot = tracemalloc.take_snapshot()

    autofix_results: list[dict[str, Any]] = []
    if args.autofix:
        autofix_results = run_autofixes(args.autofix_tools or None)

    results = collect()

    if args.profile_memory:
        current_bytes, peak_bytes = tracemalloc.get_traced_memory()
        snapshot = tracemalloc.take_snapshot()
        tracemalloc.stop()
        stats = (
            snapshot.compare_to(start_snapshot, "lineno")
            if start_snapshot is not None
            else snapshot.statistics("lineno")
        )
        limit = max(1, args.memory_profile_limit)
        top_entries: list[dict[str, Any]] = []
        for stat in stats[:limit]:
            entry = {
                "size_bytes": getattr(stat, "size", 0),
                "count": stat.count,
                "traceback": stat.traceback.format(),
            }
            size_diff = getattr(stat, "size_diff", None)
            if size_diff is not None:
                entry["size_diff_bytes"] = size_diff
            top_entries.append(entry)
        metadata["memory_profile"] = {
            "current_bytes": current_bytes,
            "peak_bytes": peak_bytes,
            "top_allocations": top_entries,
        }

    metadata["config"] = config_meta

    write_report(
        results,
        autofixes=autofix_results,
        output_path=args.output,
        metadata=metadata if metadata else None,
    )
    print(f"Problems report written to {args.output}")
    if args.summary:
        print_summary(args.output)

    return None


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    main()
