"""Execute dbt-based data contract tests for the curated dataset."""

from __future__ import annotations

import json
import logging
import os
import warnings
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from firecrawl_demo.core import config

warnings.filterwarnings("ignore", category=DeprecationWarning, module="dbt.cli.options")


@dataclass(frozen=True)
class DbtContractResult:
    """Serialisable summary of a dbt test run."""

    success: bool
    total: int
    failures: int
    elapsed: float
    results: list[dict[str, Any]]
    project_dir: Path
    profiles_dir: Path
    target_path: Path
    log_path: Path
    run_results_path: Path | None

    @property
    def passed(self) -> int:
        return self.total - self.failures


def _default_project_dir() -> Path:
    return config.PROJECT_ROOT / "analytics"


def _ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _close_dbt_log_handlers(log_directory: Path) -> None:
    """Close file-based dbt log handlers to avoid resource warnings."""

    resolved_log_dir = log_directory.resolve()
    candidate_loggers: list[logging.Logger] = [logging.getLogger()]

    for name in list(logging.root.manager.loggerDict.keys()):
        logger = logging.getLogger(name)
        if isinstance(logger, logging.Logger) and logger not in candidate_loggers:
            candidate_loggers.append(logger)

    for logger in candidate_loggers:
        for handler in list(logger.handlers):
            if not isinstance(handler, RotatingFileHandler):
                continue

            base_filename = getattr(handler, "baseFilename", "")
            if not base_filename:
                continue

            try:
                handler_path = Path(base_filename).resolve()
            except OSError:
                handler_path = None

            if handler_path is not None:
                try:
                    handler_path.relative_to(resolved_log_dir)
                except ValueError:
                    continue

            try:
                handler.flush()
            except OSError:
                pass

            handler.close()
            logger.removeHandler(handler)


def run_dbt_contract_tests(
    dataset_path: Path,
    *,
    project_dir: Path | None = None,
    profiles_dir: Path | None = None,
    target_path: Path | None = None,
    log_path: Path | None = None,
    threads: int | None = None,
) -> DbtContractResult:
    """Execute dbt tests against the curated dataset staging model."""

    warnings.filterwarnings(
        "ignore", category=DeprecationWarning, module=r"dbt\.cli\.options", append=False
    )

    try:
        from dbt.cli.main import dbtRunner
    except ModuleNotFoundError as exc:  # pragma: no cover - defensive guard
        raise RuntimeError(
            "dbt-core is not installed; install the dev dependencies to run contracts."
        ) from exc

    project_dir = project_dir or _default_project_dir()
    profiles_dir = profiles_dir or project_dir

    if not project_dir.exists():
        raise FileNotFoundError(
            f"dbt project directory '{project_dir}' does not exist; run contracts setup."
        )

    target_path = Path(
        target_path or os.environ.get("DBT_TARGET_PATH") or project_dir / "target"
    )
    log_path = Path(log_path or os.environ.get("DBT_LOG_PATH") or project_dir / "logs")

    overrides = {
        "DBT_PROFILES_DIR": str(profiles_dir),
        "DBT_TARGET_PATH": str(_ensure_directory(target_path)),
        "DBT_LOG_PATH": str(_ensure_directory(log_path)),
        "CURATED_DATASET_PATH": str(dataset_path),
    }

    vars_payload = json.dumps({"curated_source_path": str(dataset_path)})

    args = [
        "build",
        "--project-dir",
        str(project_dir),
        "--profiles-dir",
        str(profiles_dir),
        "--target",
        os.environ.get("DBT_TARGET", "ci"),
        "--vars",
        vars_payload,
        "--fail-fast",
        "--select",
        "tag:contracts",
    ]
    if threads is not None:
        args.extend(["--threads", str(threads)])

    previous: dict[str, str] = {}
    try:
        for key, value in overrides.items():
            if key in os.environ:
                previous[key] = os.environ[key]
            os.environ[key] = value

        runner = dbtRunner()
        result = runner.invoke(args)
    finally:
        for key in overrides:
            if key in previous:
                os.environ[key] = previous[key]
            else:
                os.environ.pop(key, None)

        _close_dbt_log_handlers(log_path)

    run_results_path = Path(overrides["DBT_TARGET_PATH"]) / "run_results.json"
    results: list[dict[str, Any]] = []
    failures = 0
    elapsed = 0.0

    if run_results_path.exists():
        payload = json.loads(run_results_path.read_text())
        elapsed_raw = payload.get("elapsed_time")
        if isinstance(elapsed_raw, (int, float)):
            elapsed = float(elapsed_raw)
        raw_results = payload.get("results", [])
        if isinstance(raw_results, list):
            for entry in raw_results:
                if isinstance(entry, dict):
                    results.append(dict(entry))
    else:
        # Fall back to dbt CLI response if run_results is unavailable
        response = getattr(result, "result", None)
        if response is not None:
            raw_results = getattr(response, "results", None)
            if isinstance(raw_results, list):
                for entry in raw_results:
                    try:
                        record = entry.to_dict()  # type: ignore[assignment]
                    except AttributeError:  # pragma: no cover - compatibility
                        record = dict(entry)
                    results.append(record)

    for record in results:
        status = str(record.get("status", "")).lower()
        if status not in {"pass", "skipped", "warn", "success"}:
            failures += 1

    total = len(results)
    success = bool(result.success) and failures == 0

    return DbtContractResult(
        success=success,
        total=total,
        failures=failures,
        elapsed=elapsed,
        results=results,
        project_dir=project_dir,
        profiles_dir=profiles_dir,
        target_path=Path(overrides["DBT_TARGET_PATH"]),
        log_path=Path(overrides["DBT_LOG_PATH"]),
        run_results_path=run_results_path if run_results_path.exists() else None,
    )
