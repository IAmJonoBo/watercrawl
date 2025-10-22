"""Pipeline orchestration utilities for enrichment and validation."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Hashable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from math import ceil
from pathlib import Path
from statistics import mean
from time import monotonic
from typing import Any, cast
from urllib.parse import urlparse

try:
    import pandas as pd

    _PANDAS_AVAILABLE = True
except ImportError:
    pd = None  # type: ignore
    _PANDAS_AVAILABLE = False

from firecrawl_demo.application.change_tracking import describe_changes
from firecrawl_demo.application.interfaces import EvidenceSink, PipelineService
from firecrawl_demo.application.progress import (
    NullPipelineProgressListener,
    PipelineProgressListener,
)
from firecrawl_demo.application.quality import (
    QualityFinding,
    QualityGate,
    QualityGateDecision,
)
from firecrawl_demo.application.row_processing import RowProcessor
from firecrawl_demo.core import cache as global_cache, config

if _PANDAS_AVAILABLE:
    from firecrawl_demo.core.excel import EXPECTED_COLUMNS, read_dataset, write_dataset
else:
    EXPECTED_COLUMNS = []  # type: ignore

    def read_dataset(path: Any) -> Any:  # type: ignore
        raise NotImplementedError("Dataset operations require pandas (Python < 3.14)")

    def write_dataset(df: Any, path: Any) -> None:  # type: ignore
        raise NotImplementedError("Dataset operations require pandas (Python < 3.14)")


from firecrawl_demo.domain.compliance import (
    canonical_domain,
    confidence_for_status,
    determine_status,
    normalize_phone,
    normalize_province,
    validate_email,
)
from firecrawl_demo.domain.contracts import PipelineReportContract
from firecrawl_demo.domain.models import (
    EvidenceRecord,
    PipelineReport,
    QualityIssue,
    RollbackAction,
    RollbackPlan,
    SanityCheckFinding,
    SchoolRecord,
    evidence_record_to_contract,
    pipeline_report_to_contract,
)
from firecrawl_demo.domain.validation import DatasetValidator
from firecrawl_demo.infrastructure.evidence import NullEvidenceSink
from firecrawl_demo.integrations.adapters.research import (
    NullResearchAdapter,
    ResearchAdapter,
    ResearchFinding,
    lookup_with_adapter_async,
)
from firecrawl_demo.integrations.integration_plugins import (
    PluginLookupError,
    instantiate_plugin,
)
from firecrawl_demo.integrations.storage.lakehouse import LocalLakehouseWriter
from firecrawl_demo.integrations.storage.versioning import (
    VersioningManager,
    fingerprint_dataframe,
)
from firecrawl_demo.integrations.telemetry.alerts import send_slack_alert
from firecrawl_demo.integrations.telemetry.drift_dashboard import (
    append_alert_report,
    write_prometheus_metrics,
)
from firecrawl_demo.integrations.telemetry.lineage import LineageContext, LineageManager

_OFFICIAL_KEYWORDS = (".gov.za", "caa.co.za", ".ac.za", ".org.za", ".mil.za")
logger = logging.getLogger(__name__)


def _load_research_adapter() -> ResearchAdapter:
    try:
        adapter = instantiate_plugin("adapters", "research")
    except PluginLookupError:
        logger.warning(
            "Research plugin not registered; falling back to NullResearchAdapter"
        )
        return NullResearchAdapter()
    if adapter is None:
        return NullResearchAdapter()
    return cast(ResearchAdapter, adapter)


def _load_lakehouse_writer() -> LocalLakehouseWriter | None:
    try:
        writer = instantiate_plugin("storage", "lakehouse", allow_missing=True)
    except PluginLookupError:
        return None
    return cast(LocalLakehouseWriter | None, writer)


def _load_versioning_manager() -> VersioningManager | None:
    try:
        manager = instantiate_plugin("storage", "versioning", allow_missing=True)
    except PluginLookupError:
        return None
    return cast(VersioningManager | None, manager)


def _load_lineage_manager() -> LineageManager | None:
    try:
        manager = instantiate_plugin("telemetry", "lineage", allow_missing=True)
    except PluginLookupError:
        return None
    return cast(LineageManager | None, manager)


def _load_graph_semantics_toolkit() -> dict[str, Any] | None:
    try:
        toolkit = instantiate_plugin("telemetry", "graph_semantics", allow_missing=True)
    except PluginLookupError:
        return None
    return cast(dict[str, Any] | None, toolkit)


def _load_drift_tools() -> dict[str, Any] | None:
    try:
        tools = instantiate_plugin("telemetry", "drift", allow_missing=True)
    except PluginLookupError:
        return None
    return cast(dict[str, Any] | None, tools)


def _resolve_path(path: Path | None) -> Path | None:
    if path is None:
        return None
    return path if path.is_absolute() else (config.PROJECT_ROOT / path)


def _normalize_cache_key(name: str, province: str) -> tuple[str, str]:
    return (name.strip().casefold(), province)


def _p95(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = ceil(0.95 * len(ordered)) - 1
    if index < 0:
        index = 0
    if index >= len(ordered):
        index = len(ordered) - 1
    return ordered[index]


@dataclass(slots=True)
class _RowState:
    position: int
    index: Hashable
    row_id: int
    original_row: Any
    original_record: SchoolRecord
    working_record: SchoolRecord


@dataclass(slots=True)
class _LookupResult:
    state: _RowState
    finding: ResearchFinding
    error: Exception | None = None
    from_cache: bool = False
    retries: int = 0


@dataclass(slots=True)
class _LookupMetrics:
    cache_hits: int = 0
    cache_misses: int = 0
    queue_latencies: list[float] = field(default_factory=list)
    failures: int = 0
    retries: int = 0
    circuit_rejections: int = 0

    def record_queue_latency(self, latency: float) -> None:
        self.queue_latencies.append(latency)


class _CircuitBreaker:
    def __init__(self, *, failure_threshold: int, reset_seconds: float) -> None:
        self._failure_threshold = max(1, failure_threshold)
        self._reset_seconds = max(0.0, reset_seconds)
        self._failure_count = 0
        self._opened_at: float | None = None

    def allow(self) -> bool:
        if self._opened_at is None:
            return True
        if monotonic() - self._opened_at >= self._reset_seconds:
            self._failure_count = 0
            self._opened_at = None
            return True
        return False

    def record_failure(self) -> None:
        self._failure_count += 1
        if self._failure_count >= self._failure_threshold:
            self._opened_at = monotonic()

    def record_success(self) -> None:
        self._failure_count = 0
        self._opened_at = None


def _share_executor_with_adapter(
    adapter: ResearchAdapter, executor: ThreadPoolExecutor | None
) -> None:
    visited: set[int] = set()

    def _apply(target: Any) -> None:
        if target is None:
            return
        key = id(target)
        if key in visited:
            return
        visited.add(key)
        try:
            if executor is None:
                if hasattr(target, "_lookup_executor"):
                    delattr(target, "_lookup_executor")
            else:
                setattr(target, "_lookup_executor", executor)
        except AttributeError:
            pass

        for attr in ("adapters", "_adapters"):
            children = getattr(target, attr, None)
            if isinstance(children, Iterable):
                for child in children:
                    _apply(child)
        base = getattr(target, "base_adapter", None)
        if base is not None:
            _apply(base)

    _apply(adapter)


class _LookupCoordinator:
    def __init__(
        self,
        *,
        adapter: ResearchAdapter,
        listener: PipelineProgressListener,
        concurrency: int,
        cache_ttl_hours: float | None,
        max_retries: int,
        retry_backoff_base_seconds: float,
        circuit_breaker: _CircuitBreaker,
    ) -> None:
        self._adapter = adapter
        self._listener = listener
        self._concurrency = max(1, concurrency)
        self._semaphore = asyncio.Semaphore(self._concurrency)
        self._cache_ttl_hours = cache_ttl_hours
        self._max_retries = max(0, max_retries)
        self._retry_backoff_base = max(0.0, retry_backoff_base_seconds)
        self._circuit_breaker = circuit_breaker
        self._metrics = _LookupMetrics()
        self._executor: ThreadPoolExecutor | None = None

    @property
    def metrics(self) -> _LookupMetrics:
        return self._metrics

    async def __aenter__(self) -> "_LookupCoordinator":
        self._executor = ThreadPoolExecutor(
            max_workers=self._concurrency,
            thread_name_prefix="pipeline-lookup",
        )
        _share_executor_with_adapter(self._adapter, self._executor)
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        _share_executor_with_adapter(self._adapter, None)
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)

    async def run(self, states: Sequence[_RowState]) -> list[_LookupResult]:
        tasks: list[asyncio.Task[_LookupResult]] = []
        async with asyncio.TaskGroup() as group:
            for state in states:
                tasks.append(group.create_task(self._lookup(state)))
        results = [task.result() for task in tasks]
        return sorted(results, key=lambda item: item.state.position)

    async def _lookup(self, state: _RowState) -> _LookupResult:
        queue_entered = monotonic()
        async with self._semaphore:
            self._metrics.record_queue_latency(monotonic() - queue_entered)
            cache_key = _normalize_cache_key(
                state.working_record.name, state.working_record.province
            )
            cached = self._load_from_cache(cache_key)
            if cached is not None:
                self._metrics.cache_hits += 1
                return _LookupResult(state=state, finding=cached, from_cache=True)

            self._metrics.cache_misses += 1
            if not self._circuit_breaker.allow():
                self._metrics.circuit_rejections += 1
                return _LookupResult(
                    state=state,
                    finding=ResearchFinding(
                        notes=(
                            "Research adapter temporarily paused after repeated failures."
                        )
                    ),
                )

            try:
                finding, retries = await self._attempt_lookup(state)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - defensive guard
                self._metrics.failures += 1
                self._circuit_breaker.record_failure()
                logger.warning(
                    "Research adapter failed for %s (%s): %s",
                    state.working_record.name,
                    state.working_record.province,
                    exc,
                    exc_info=exc,
                )
                self._listener.on_error(exc, state.position)
                return _LookupResult(
                    state=state,
                    finding=ResearchFinding(notes=f"Research adapter failed: {exc}"),
                    error=exc,
                )

            if self._cache_ttl_hours is not None:
                global_cache.store(cache_key, finding)
            return _LookupResult(
                state=state,
                finding=finding,
                retries=retries,
            )

    def _load_from_cache(
        self, key: tuple[str, str]
    ) -> ResearchFinding | None:
        if self._cache_ttl_hours is None:
            return None
        cached = global_cache.load(key, max_age_hours=self._cache_ttl_hours)
        if isinstance(cached, ResearchFinding):
            return cached
        return None

    async def _attempt_lookup(
        self, state: _RowState
    ) -> tuple[ResearchFinding, int]:
        retries = 0
        max_delay = 5.0
        while True:
            try:
                finding = await lookup_with_adapter_async(
                    self._adapter,
                    state.working_record.name,
                    state.working_record.province,
                    executor=self._executor,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                retries += 1
                self._metrics.retries += 1
                self._circuit_breaker.record_failure()
                if retries > self._max_retries:
                    raise
                delay = min(max_delay, self._retry_backoff_base * (2 ** (retries - 1)))
                if delay > 0:
                    await asyncio.sleep(delay)
                continue
            else:
                self._circuit_breaker.record_success()
                return finding, retries
@dataclass
class Pipeline(PipelineService):
    """Coordinate validation, enrichment, and evidence logging."""

    research_adapter: ResearchAdapter = field(
        default_factory=lambda: _load_research_adapter()
    )
    validator: DatasetValidator = field(default_factory=DatasetValidator)
    evidence_sink: EvidenceSink = field(default_factory=NullEvidenceSink)
    quality_gate: QualityGate = field(default_factory=QualityGate)
    lineage_manager: LineageManager | None = field(
        default_factory=lambda: _load_lineage_manager()
    )
    lakehouse_writer: LocalLakehouseWriter | None = field(
        default_factory=lambda: _load_lakehouse_writer()
    )
    versioning_manager: VersioningManager | None = field(
        default_factory=lambda: _load_versioning_manager()
    )
    graph_semantics_toolkit: dict[str, Any] | None = field(
        default_factory=lambda: _load_graph_semantics_toolkit()
    )
    drift_tools: dict[str, Any] | None = field(
        default_factory=lambda: _load_drift_tools()
    )
    _last_report: PipelineReport | None = field(default=None, init=False, repr=False)
    _last_contract: PipelineReportContract | None = field(
        default=None, init=False, repr=False
    )

    @property
    def last_report(self) -> PipelineReport | None:
        """Return the most recent pipeline report, if available."""

        return self._last_report

    @property
    def last_contract(self) -> PipelineReportContract | None:
        """Return the most recent pipeline report contract, if available."""

        if self._last_contract is not None:
            return self._last_contract
        if self._last_report is not None:
            self._last_contract = pipeline_report_to_contract(self._last_report)
        return self._last_contract

    def run_dataframe(
        self,
        frame: Any,
        progress: PipelineProgressListener | None = None,
        lineage_context: LineageContext | None = None,
    ) -> PipelineReport:
        """Synchronously run the enrichment pipeline for a dataframe."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.run_dataframe_async(
                    frame, progress=progress, lineage_context=lineage_context
                )
            )
        raise RuntimeError(
            "Pipeline.run_dataframe cannot be used inside an active event loop; "
            "call run_dataframe_async instead."
        )

    async def run_dataframe_async(
        self,
        frame: Any,
        progress: PipelineProgressListener | None = None,
        lineage_context: LineageContext | None = None,
    ) -> PipelineReport:
        """Asynchronously run the enrichment pipeline for a dataframe."""
        validation = self.validator.validate_dataframe(frame)
        missing_column_errors = [
            issue for issue in validation.issues if issue.code == "missing_column"
        ]
        if missing_column_errors:
            columns = ", ".join(issue.column or "" for issue in missing_column_errors)
            raise ValueError(f"Missing expected columns: {columns}")

        working_frame = frame.copy(deep=True)
        working_frame_cast = cast(Any, working_frame)
        input_fingerprint = fingerprint_dataframe(frame)
        evidence_records: list[EvidenceRecord] = []
        enriched_rows = 0
        adapter_failures = 0
        sanity_findings: list[SanityCheckFinding] = []
        row_number_lookup: dict[Hashable, int] = {}
        quality_issues: list[QualityIssue] = []
        rollback_actions: list[RollbackAction] = []
        quality_rejections = 0
        listener = progress or NullPipelineProgressListener()

        listener.on_start(len(working_frame))

        row_states: list[_RowState] = []
        # Use itertuples() for better performance (2-3x faster than iterrows)
        for position, row_tuple in enumerate(working_frame.itertuples()):
            idx = row_tuple.Index
            # Convert named tuple to Series-like dict for compatibility
            row = working_frame.loc[idx]
            original_row = row.copy()
            original_record = SchoolRecord.from_dataframe_row(row)
            record = replace(original_record)
            record.province = normalize_province(record.province)
            working_frame_cast.at[idx, "Province"] = record.province
            row_id = position + 2
            row_number_lookup[idx] = row_id
            row_states.append(
                _RowState(
                    position=position,
                    index=idx,
                    row_id=row_id,
                    original_row=original_row,
                    original_record=original_record,
                    working_record=record,
                )
            )

        circuit_breaker = _CircuitBreaker(
            failure_threshold=config.RESEARCH_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            reset_seconds=config.RESEARCH_CIRCUIT_BREAKER_RESET_SECONDS,
        )
        coordinator = _LookupCoordinator(
            adapter=self.research_adapter,
            listener=listener,
            concurrency=config.RESEARCH_CONCURRENCY_LIMIT,
            cache_ttl_hours=config.RESEARCH_CACHE_TTL_HOURS,
            max_retries=config.RESEARCH_MAX_RETRIES,
            retry_backoff_base_seconds=config.RESEARCH_RETRY_BACKOFF_BASE_SECONDS,
            circuit_breaker=circuit_breaker,
        )
        async with coordinator:
            lookup_results = await coordinator.run(row_states)
        lookup_metrics = coordinator.metrics
        adapter_failures = lookup_metrics.failures

        # Create row processor for handling transformations
        row_processor = RowProcessor(quality_gate=self.quality_gate)
        
        # Build list of update instructions for vectorized application
        update_instructions: list[tuple[Any, SchoolRecord, list[str]]] = []
        
        for result in lookup_results:
            state = result.state
            position = state.position
            idx = state.index
            row_id = state.row_id
            original_row = state.original_row
            original_record = state.original_record
            finding = result.finding

            # Process the row using the new row processor
            processing_result = row_processor.process_row(
                original_record=original_record,
                finding=finding,
                row_id=row_id,
            )
            
            final_record = processing_result.final_record
            final_updated = processing_result.updated
            
            # Collect side effects
            sanity_findings.extend(processing_result.sanity_findings)
            quality_issues.extend(processing_result.quality_issues)
            if processing_result.rollback_action:
                rollback_actions.append(processing_result.rollback_action)
                quality_rejections += 1
            
            # Store update instruction for vectorized application
            update_instructions.append(
                (idx, final_record, processing_result.cleared_columns)
            )
            
            # Build evidence record
            if processing_result.rollback_action:
                # Quality gate rejection
                attempted_changes_text = describe_changes(original_row, processing_result.final_record)
                final_changes_text = describe_changes(original_row, final_record)
                rejection_reason = self._format_rejection_reason(processing_result.quality_issues)
                notes = self._compose_quality_rejection_notes(
                    rejection_reason,
                    attempted_changes_text,
                    [],  # decision.findings not available from processing_result
                    processing_result.sanity_notes,
                )
                evidence_records.append(
                    EvidenceRecord(
                        row_id=row_id,
                        organisation=final_record.name,
                        changes=final_changes_text or "No changes",
                        sources=processing_result.sources,
                        notes=notes,
                        confidence=0,
                    )
                )
            elif final_updated:
                # Successful enrichment
                (
                    total_source_count,
                    fresh_source_count,
                    official_source_count,
                    official_fresh_source_count,
                ) = processing_result.source_counts
                evidence_records.append(
                    EvidenceRecord(
                        row_id=row_id,
                        organisation=final_record.name,
                        changes=describe_changes(original_row, final_record),
                        sources=processing_result.sources,
                        notes=self._compose_evidence_notes(
                            finding,
                            original_row,
                            final_record,
                            has_official_source=official_source_count > 0,
                            total_source_count=total_source_count,
                            fresh_source_count=fresh_source_count,
                            sanity_notes=processing_result.sanity_notes,
                        ),
                        confidence=processing_result.confidence,
                    )
                )
                enriched_rows += 1
            
            listener.on_row_processed(position, final_updated, final_record)
        
        # Apply updates in a vectorized manner to preserve dtype stability
        self._apply_bulk_updates(working_frame, update_instructions)

        if evidence_records:
            contract_entries = [
                evidence_record_to_contract(record) for record in evidence_records
            ]
            self.evidence_sink.record(contract_entries)

        sanity_findings.extend(
            self._detect_duplicate_schools(working_frame, row_number_lookup)
        )

        cache_requests = lookup_metrics.cache_hits + lookup_metrics.cache_misses
        cache_hit_rate = (
            lookup_metrics.cache_hits / cache_requests if cache_requests else 0.0
        )
        avg_queue_latency = (
            mean(lookup_metrics.queue_latencies)
            if lookup_metrics.queue_latencies
            else 0.0
        )
        p95_queue_latency = _p95(lookup_metrics.queue_latencies)
        max_queue_latency = (
            max(lookup_metrics.queue_latencies) if lookup_metrics.queue_latencies else 0.0
        )

        metrics = {
            "rows_total": len(working_frame),
            "enriched_rows": enriched_rows,
            "verified_rows": int((working_frame["Status"] == "Verified").sum()),
            "issues_found": len(validation.issues),
            "adapter_failures": adapter_failures,
            "sanity_issues": len(sanity_findings),
            "quality_rejections": quality_rejections,
            "quality_issues": len(quality_issues),
            "research_cache_hits": lookup_metrics.cache_hits,
            "research_cache_misses": lookup_metrics.cache_misses,
            "research_cache_hit_rate": cache_hit_rate,
            "research_queue_latency_avg_ms": avg_queue_latency * 1000,
            "research_queue_latency_p95_ms": p95_queue_latency * 1000,
            "research_queue_latency_max_ms": max_queue_latency * 1000,
            "adapter_retry_attempts": lookup_metrics.retries,
            "adapter_circuit_rejections": lookup_metrics.circuit_rejections,
        }
        report = PipelineReport(
            refined_dataframe=working_frame,
            validation_report=validation,
            evidence_log=evidence_records,
            metrics=metrics,
            sanity_findings=sanity_findings,
            quality_issues=quality_issues,
            rollback_plan=(
                RollbackPlan(rollback_actions) if rollback_actions else None
            ),
        )
        active_context = lineage_context

        if self.graph_semantics_toolkit:
            generator = self.graph_semantics_toolkit.get(
                "generate_graph_semantics_report"
            )
            if callable(generator):
                dataset_uri = None
                if active_context:
                    dataset_uri = active_context.output_uri or active_context.input_uri
                if not dataset_uri:
                    dataset_uri = (
                        (config.PROCESSED_DIR / "enriched.csv").resolve().as_uri()
                    )
                evidence_path = config.EVIDENCE_LOG
                evidence_uri = (
                    evidence_path.resolve().as_uri()
                    if isinstance(evidence_path, Path) and evidence_path.exists()
                    else None
                )
                graph_report = generator(
                    frame=report.refined_dataframe,
                    dataset_uri=dataset_uri,
                    evidence_log_uri=evidence_uri,
                    table_name=config.LAKEHOUSE.table_name,
                )
                report.graph_semantics = graph_report
                if graph_report and graph_report.issues:
                    metrics["graph_semantics_issues"] = len(graph_report.issues)
        manifest = None
        version_info = None
        if self.lakehouse_writer and active_context:
            manifest = self.lakehouse_writer.write(
                run_id=active_context.run_id, dataframe=report.refined_dataframe
            )
            version_value = manifest.version
            if self.versioning_manager:
                version_info = self.versioning_manager.record_snapshot(
                    run_id=active_context.run_id,
                    manifest=manifest,
                    input_fingerprint=input_fingerprint,
                    extras={
                        "source": "pipeline.run_dataframe_async",
                        "environment": config.DEPLOYMENT.profile,
                    },
                )
                version_value = version_info.version
            active_context = active_context.with_lakehouse(
                uri=manifest.table_uri,
                version=version_value,
                manifest_path=manifest.manifest_path,
                fingerprint=manifest.fingerprint,
            )
            if version_info is not None:
                active_context = active_context.with_version(
                    version=version_info.version,
                    metadata_path=version_info.metadata_path,
                    reproduce_command=version_info.reproduce_command,
                    input_fingerprint=version_info.input_fingerprint,
                    output_fingerprint=version_info.output_fingerprint,
                    extras=version_info.extras,
                )
            else:
                active_context = active_context.with_version(version=version_value)
        if self.lineage_manager and active_context:
            artifacts = self.lineage_manager.capture(report, active_context)
            report.lineage_artifacts = artifacts
        if manifest is not None:
            report.lakehouse_manifest = manifest
        if version_info is not None:
            report.version_info = version_info

        if self.drift_tools and config.DRIFT.enabled:
            comparator = self.drift_tools.get("compare_to_baseline")
            load_baseline_fn = self.drift_tools.get("load_baseline")
            baseline_path = _resolve_path(config.DRIFT.baseline_path)
            baseline_missing = not (
                baseline_path is not None and baseline_path.exists()
            )
            if config.DRIFT.require_baseline and baseline_missing:
                metrics["drift_missing_baseline"] = (
                    metrics.get("drift_missing_baseline", 0) + 1
                )
                sanity_findings.append(
                    SanityCheckFinding(
                        row_id=0,
                        organisation="Global",
                        issue="drift_baseline_missing",
                        remediation=(
                            "Generate a baseline JSON with "
                            "`firecrawl_demo.integrations.telemetry.drift.save_baseline` "
                            "and point DRIFT_BASELINE_PATH to the stored file."
                        ),
                    )
                )
                metrics["sanity_issues"] = metrics.get("sanity_issues", 0) + 1
            if (
                callable(comparator)
                and callable(load_baseline_fn)
                and not baseline_missing
            ):
                try:
                    baseline = load_baseline_fn(baseline_path)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("drift.baseline_load_failed", exc_info=exc)
                    baseline = None
                if baseline is not None:
                    drift_report = comparator(
                        frame=report.refined_dataframe,
                        baseline=baseline,
                        threshold=config.DRIFT.threshold,
                    )
                    log_profile_fn = self.drift_tools.get("log_whylogs_profile")
                    load_meta_fn = self.drift_tools.get("load_whylogs_metadata")
                    compare_meta_fn = self.drift_tools.get("compare_whylogs_metadata")
                    output_dir = _resolve_path(config.DRIFT.whylogs_output_dir)
                    run_identifier = (
                        active_context.run_id
                        if active_context and active_context.run_id
                        else datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
                    )
                    if (
                        callable(log_profile_fn)
                        and callable(load_meta_fn)
                        and callable(compare_meta_fn)
                        and output_dir is not None
                    ):
                        profile_path = output_dir / f"{run_identifier}.whylogs"
                        profile_info = log_profile_fn(
                            report.refined_dataframe, profile_path
                        )
                        drift_report.whylogs_profile = profile_info
                        baseline_meta_path = _resolve_path(
                            config.DRIFT.whylogs_baseline_path
                        )
                        baseline_meta_missing = not (
                            baseline_meta_path is not None
                            and baseline_meta_path.exists()
                        )
                        if (
                            config.DRIFT.require_whylogs_metadata
                            and baseline_meta_missing
                        ):
                            metrics["drift_missing_whylogs_baseline"] = (
                                metrics.get("drift_missing_whylogs_baseline", 0) + 1
                            )
                            sanity_findings.append(
                                SanityCheckFinding(
                                    row_id=0,
                                    organisation="Global",
                                    issue="whylogs_baseline_missing",
                                    remediation=(
                                        "Persist metadata JSON from an approved baseline "
                                        "profile (via `log_whylogs_profile`) and set "
                                        "DRIFT_WHYLOGS_BASELINE."
                                    ),
                                )
                            )
                            metrics["sanity_issues"] = (
                                metrics.get("sanity_issues", 0) + 1
                            )
                        if not baseline_meta_missing:
                            baseline_meta = load_meta_fn(baseline_meta_path)
                            observed_meta = load_meta_fn(profile_info.metadata_path)
                            alerts = compare_meta_fn(
                                baseline_meta,
                                observed_meta,
                                config.DRIFT.threshold,
                            )
                            drift_report.whylogs_alerts = alerts
                            if alerts:
                                drift_report.exceeded_threshold = True
                                metrics["drift_alerts"] = metrics.get(
                                    "drift_alerts", 0
                                ) + len(alerts)
                    dataset_name = config.LINEAGE.dataset_name
                    alert_output = _resolve_path(config.DRIFT.alert_output_path)
                    prometheus_output = _resolve_path(
                        config.DRIFT.prometheus_output_path
                    )
                    slack_webhook = config.DRIFT.slack_webhook
                    dashboard_url = config.DRIFT.dashboard_url
                    profile_timestamp = (
                        drift_report.whylogs_profile.generated_at
                        if drift_report.whylogs_profile
                        else datetime.now(UTC)
                    )
                    if alert_output is not None:
                        try:
                            append_alert_report(
                                report=drift_report,
                                output_path=alert_output,
                                run_id=run_identifier,
                                dataset_name=dataset_name,
                                timestamp=profile_timestamp,
                            )
                        except Exception as exc:  # pragma: no cover - defensive
                            logger.warning("drift.alert_append_failed", exc_info=exc)
                    if prometheus_output is not None:
                        try:
                            write_prometheus_metrics(
                                report=drift_report,
                                metrics_path=prometheus_output,
                                run_id=run_identifier,
                                dataset_name=dataset_name,
                                timestamp=profile_timestamp,
                            )
                        except Exception as exc:  # pragma: no cover - defensive
                            logger.warning(
                                "drift.prometheus_write_failed", exc_info=exc
                            )
                    if drift_report.exceeded_threshold:
                        metrics["drift_alerts"] = metrics.get("drift_alerts", 0) + 1
                        if slack_webhook:
                            try:
                                sent = send_slack_alert(
                                    report=drift_report,
                                    webhook_url=slack_webhook,
                                    dataset=dataset_name,
                                    run_id=run_identifier,
                                    run_timestamp=profile_timestamp.isoformat(),
                                    dashboard_url=dashboard_url,
                                )
                                key = (
                                    "drift_alert_notifications"
                                    if sent
                                    else "drift_alert_notifications_failed"
                                )
                                metrics[key] = metrics.get(key, 0) + 1
                            except Exception:  # pragma: no cover - defensive
                                logger.warning(
                                    "drift.slack_notification_failed", exc_info=True
                                )
                                metrics["drift_alert_notifications_failed"] = (
                                    metrics.get("drift_alert_notifications_failed", 0)
                                    + 1
                                )
                    report.drift_report = drift_report

        self._last_report = report
        self._last_contract = pipeline_report_to_contract(report)
        listener.on_complete(metrics)
        return report

    async def run_file_async(
        self,
        input_path: Path,
        output_path: Path | None = None,
        *,
        progress: PipelineProgressListener | None = None,
        lineage_context: LineageContext | None = None,
    ) -> PipelineReport:
        """Asynchronously process a dataset file through the pipeline."""
        dataset = read_dataset(input_path)
        active_context = lineage_context
        if active_context:
            input_uri = input_path.resolve().as_uri()
            output_uri = output_path.resolve().as_uri() if output_path else None
            active_context = replace(
                active_context,
                input_uri=input_uri,
                output_uri=output_uri or active_context.output_uri,
            )
        report = await self.run_dataframe_async(
            dataset, progress=progress, lineage_context=active_context
        )
        if output_path:
            write_dataset(report.refined_dataframe, output_path)
        return report

    def run_file(
        self,
        input_path: Path,
        output_path: Path | None = None,
        *,
        progress: PipelineProgressListener | None = None,
        lineage_context: LineageContext | None = None,
    ) -> PipelineReport:
        """Synchronously process a dataset file through the pipeline."""
        dataset = read_dataset(input_path)
        report = self.run_dataframe(
            dataset, progress=progress, lineage_context=lineage_context
        )
        if output_path:
            write_dataset(report.refined_dataframe, output_path)
        return report

    def available_tasks(self) -> dict[str, str]:
        """Describe the tasks supported by the pipeline orchestrator."""
        return {
            "validate_dataset": "Validate the provided dataset",
            "enrich_dataset": "Validate and enrich the provided dataset",
            "summarize_last_run": "Summarise metrics from the most recent pipeline execution",
            "list_sanity_issues": "List outstanding sanity check findings from the latest run",
        }

    def run_task(self, task: str, payload: dict[str, object]) -> dict[str, object]:
        """Execute a named pipeline task and return a serialisable payload."""
        if task == "validate_dataset":
            frame = self._frame_from_payload(payload)
            validation_report = self.validator.validate_dataframe(frame)
            return {
                "status": "ok",
                "rows": validation_report.rows,
                "issues": [issue.__dict__ for issue in validation_report.issues],
            }
        if task == "enrich_dataset":
            frame = self._frame_from_payload(payload)
            pipeline_report = self.run_dataframe(frame)
            return {
                "status": "ok",
                "rows_enriched": pipeline_report.metrics["enriched_rows"],
                "metrics": pipeline_report.metrics,
                "quality_issues": [
                    issue.__dict__ for issue in pipeline_report.quality_issues
                ],
                "rollback_plan": (
                    pipeline_report.rollback_plan.as_dict()
                    if pipeline_report.rollback_plan
                    else None
                ),
            }
        if task == "summarize_last_run":
            return self._summarize_last_run()
        if task == "list_sanity_issues":
            return self._list_sanity_issues()
        raise KeyError(task)

    def _frame_from_payload(self, payload: dict[str, object]) -> Any:
        if "path" in payload:
            return read_dataset(Path(str(payload["path"])))
        if "rows" in payload:
            rows_obj = payload["rows"] or []
            if not isinstance(rows_obj, list):
                raise ValueError("Payload 'rows' must be a list of mappings")
            if not _PANDAS_AVAILABLE:
                raise NotImplementedError(
                    "DataFrame creation requires pandas (Python < 3.14)"
                )
            return pd.DataFrame(list(rows_obj), columns=list(EXPECTED_COLUMNS))  # type: ignore
        raise ValueError("Payload must include 'path' or 'rows'")

    def _apply_record(self, frame: Any, index: Hashable, record: SchoolRecord) -> None:
        frame_cast = cast(Any, frame)
        for column, value in record.as_dict().items():
            if value is not None:
                # Ensure column is object dtype to avoid pandas incompatibility warnings
                if frame_cast[column].dtype != "object":
                    frame_cast[column] = frame_cast[column].astype("object")
                frame_cast.at[index, column] = value
    
    def _apply_bulk_updates(
        self,
        frame: Any,
        instructions: list[tuple[Any, SchoolRecord, list[str]]],
    ) -> None:
        """Apply row updates in a vectorized manner to preserve dtype stability.
        
        Args:
            frame: The DataFrame to update
            instructions: List of (index, record, cleared_columns) tuples
        """
        frame_cast = cast(Any, frame)
        
        # Pre-convert columns to object dtype once to avoid repeated conversions
        columns_to_convert: set[str] = set()
        for _, record, cleared_cols in instructions:
            for column, value in record.as_dict().items():
                if value is not None:
                    columns_to_convert.add(column)
            columns_to_convert.update(cleared_cols)
        
        for column in columns_to_convert:
            if column in frame_cast.columns and frame_cast[column].dtype != "object":
                frame_cast[column] = frame_cast[column].astype("object")
        
        # Apply all updates
        for idx, record, cleared_cols in instructions:
            for column, value in record.as_dict().items():
                if value is not None:
                    frame_cast.at[idx, column] = value
            for column in cleared_cols:
                frame_cast.at[idx, column] = ""

    def _collect_changed_columns(
        self, original: SchoolRecord, proposed: SchoolRecord
    ) -> dict[str, tuple[str | None, str | None]]:
        changes: dict[str, tuple[str | None, str | None]] = {}
        original_map = original.as_dict()
        proposed_map = proposed.as_dict()
        for column, original_value in original_map.items():
            proposed_value = proposed_map.get(column)
            if (original_value or "") != (proposed_value or ""):
                changes[column] = (original_value, proposed_value)
        return changes

    def _quality_issue_from_finding(
        self,
        *,
        row_id: int,
        organisation: str,
        finding: QualityFinding,
    ) -> QualityIssue:
        return QualityIssue(
            row_id=row_id,
            organisation=organisation,
            code=finding.code,
            severity=finding.severity,
            message=finding.message,
            remediation=finding.remediation,
        )

    def _build_rollback_action(
        self,
        *,
        row_id: int,
        organisation: str,
        attempted_changes: dict[str, tuple[str | None, str | None]],
        issues: Sequence[QualityIssue],
    ) -> RollbackAction:
        columns = sorted(attempted_changes.keys())
        previous_values = {column: attempted_changes[column][0] for column in columns}
        reason_parts = [issue.message for issue in issues if issue.message]
        reason_text = "; ".join(reason_parts) or "Quality gate rejection"
        remediation = sorted(
            {issue.remediation for issue in issues if issue.remediation}
        )
        if remediation:
            reason_text += ". Remediation: " + "; ".join(remediation)
        return RollbackAction(
            row_id=row_id,
            organisation=organisation,
            columns=columns,
            previous_values=previous_values,
            reason=reason_text,
        )

    def _format_rejection_reason(self, issues: Sequence[QualityIssue]) -> str:
        blocking = [issue.message for issue in issues if issue.severity == "block"]
        if blocking:
            return "; ".join(blocking)
        fallback = [issue.message for issue in issues if issue.message]
        return "; ".join(fallback) or "Quality gate rejected enrichment"

    def _compose_quality_rejection_notes(
        self,
        reason: str,
        attempted_changes: str,
        findings: Sequence[QualityFinding],
        sanity_notes: Sequence[str],
    ) -> str:
        notes: list[str] = [f"Quality gate rejected enrichment: {reason}"]
        if attempted_changes:
            notes.append(f"Attempted updates: {attempted_changes}")
        remediation = sorted(
            {finding.remediation for finding in findings if finding.remediation}
        )
        if remediation:
            notes.append("Remediation: " + "; ".join(remediation))
        if sanity_notes:
            notes.extend(sanity_notes)
        return "; ".join(notes)

    def _merge_sources(
        self, record: SchoolRecord, finding: ResearchFinding
    ) -> list[str]:
        sources: list[str] = []
        if record.website_url:
            sources.append(record.website_url)
        if finding.website_url and finding.website_url not in sources:
            sources.append(finding.website_url)
        for source in finding.sources:
            if source not in sources:
                sources.append(source)
        if not sources:
            sources.append("internal://record")
        return sources

    def _summarize_sources(
        self, *, original: SchoolRecord, merged_sources: Sequence[str]
    ) -> tuple[int, int, int, int]:
        original_keys = {
            self._normalize_source_key(source)
            for source in self._collect_original_sources(original)
        }
        seen_keys: set[str] = set()
        total_sources = 0
        fresh_sources = 0
        official_sources = 0
        official_fresh_sources = 0
        for source in merged_sources:
            key = self._normalize_source_key(source)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            total_sources += 1
            is_official = self._is_official_source(source)
            if is_official:
                official_sources += 1
            if key not in original_keys:
                fresh_sources += 1
                if is_official:
                    official_fresh_sources += 1
        return total_sources, fresh_sources, official_sources, official_fresh_sources

    def _collect_original_sources(self, record: SchoolRecord) -> Sequence[str]:
        sources: list[str] = []
        if record.website_url:
            sources.append(record.website_url)
        return sources

    def _normalize_source_key(self, source: str) -> str:
        domain = canonical_domain(source)
        if domain:
            return f"domain:{domain}"
        return source.strip().lower()

    def _is_official_source(self, source: str) -> bool:
        candidate = source.lower()
        return any(keyword in candidate for keyword in _OFFICIAL_KEYWORDS)

    def _describe_changes(self, original_row: Any, record: SchoolRecord) -> str:
        changes: list[str] = []
        mapping = {
            "Website URL": record.website_url,
            "Contact Person": record.contact_person,
            "Contact Number": record.contact_number,
            "Contact Email Address": record.contact_email,
            "Status": record.status,
            "Province": record.province,
        }
        for column, new_value in mapping.items():
            original_value = str(original_row.get(column, "") or "").strip()
            if new_value and original_value != new_value:
                changes.append(f"{column} -> {new_value}")
        return "; ".join(changes) or "No changes"

    def _compose_evidence_notes(
        self,
        finding: ResearchFinding,
        original_row: Any,
        record: SchoolRecord,
        *,
        has_official_source: bool,
        total_source_count: int,
        fresh_source_count: int,
        sanity_notes: Sequence[str] | None = None,
    ) -> str:
        notes: list[str] = []
        if finding.notes:
            notes.append(finding.notes)

        if sanity_notes:
            for note in sanity_notes:
                if note and note not in notes:
                    notes.append(note)

        if config.FEATURE_FLAGS.investigate_rebrands:
            for note in finding.investigation_notes:
                if note and note not in notes:
                    notes.append(note)

            prior_domain = canonical_domain(str(original_row.get("Website URL", "")))
            current_domain = canonical_domain(record.website_url)
            if prior_domain and current_domain and prior_domain != current_domain:
                rename_note = f"Website changed from {prior_domain} to {current_domain}; investigate potential rename or ownership change."
                if rename_note not in notes:
                    notes.append(rename_note)

            if finding.alternate_names:
                alias_block = ", ".join(sorted(set(finding.alternate_names)))
                alias_note = f"Known aliases: {alias_block}"
                if alias_note not in notes:
                    notes.append(alias_note)

            if finding.physical_address:
                address_note = (
                    f"Latest address intelligence: {finding.physical_address}"
                )
                if address_note not in notes:
                    notes.append(address_note)

        if not notes:
            notes_text = ""
        else:
            notes_text = "; ".join(notes)

        remediation_reasons: list[str] = []
        if total_source_count < 2:
            remediation_reasons.append("add a second independent source")
        if fresh_source_count == 0:
            remediation_reasons.append("capture a fresh supporting source")
        if not has_official_source:
            remediation_reasons.append(
                "confirm an official (.gov.za/.caa.co.za/.ac.za/.org.za/.mil.za) source"
            )
        if remediation_reasons:
            shortfall_note = "Evidence shortfall: " + "; ".join(remediation_reasons)
            if not shortfall_note.endswith("."):
                shortfall_note += "."
            if notes_text:
                notes_text = "; ".join(filter(None, [notes_text, shortfall_note]))
            else:
                notes_text = shortfall_note

        return notes_text

    def _run_sanity_checks(
        self,
        *,
        record: SchoolRecord,
        row_id: int,
        sources: list[str],
        phone_issues: Sequence[str],
        email_issues: Sequence[str],
        previous_phone: str | None,
        previous_email: str | None,
    ) -> tuple[bool, list[str], list[SanityCheckFinding], list[str], list[str]]:
        updated = False
        notes: list[str] = []
        findings: list[SanityCheckFinding] = []
        normalized_sources = list(sources)
        cleared_columns: list[str] = []

        if record.website_url:
            parsed = urlparse(record.website_url)
            if not parsed.scheme:
                original_url = record.website_url
                normalized_url = f"https://{original_url.lstrip('/')}"
                record.website_url = normalized_url
                normalized_sources = [
                    normalized_url if source == original_url else source
                    for source in normalized_sources
                ]
                updated = True
                notes.append("Auto-normalised website URL to include https scheme.")
                findings.append(
                    SanityCheckFinding(
                        row_id=row_id,
                        organisation=record.name,
                        issue="website_url_missing_scheme",
                        remediation="Added an https:// prefix to the website URL for consistency.",
                    )
                )

        if previous_phone and record.contact_number is None and phone_issues:
            notes.append(
                "Removed invalid contact number after it failed +27 E.164 validation."
            )
            findings.append(
                SanityCheckFinding(
                    row_id=row_id,
                    organisation=record.name,
                    issue="contact_number_invalid",
                    remediation="Capture a verified +27-format contact number before publishing.",
                )
            )
            updated = True
            cleared_columns.append("Contact Number")

        if previous_email and record.contact_email is None and email_issues:
            notes.append("Removed invalid contact email after validation failures.")
            findings.append(
                SanityCheckFinding(
                    row_id=row_id,
                    organisation=record.name,
                    issue="contact_email_invalid",
                    remediation="Source a named contact email on the official organisation domain.",
                )
            )
            updated = True
            cleared_columns.append("Contact Email Address")

        if record.province == "Unknown":
            findings.append(
                SanityCheckFinding(
                    row_id=row_id,
                    organisation=record.name,
                    issue="province_unknown",
                    remediation=(
                        "Confirm the organisation's South African province and update the dataset."
                    ),
                )
            )
            notes.append("Province remains Unknown pending analyst confirmation.")

        return updated, notes, findings, normalized_sources, cleared_columns

    def _detect_duplicate_schools(
        self, frame: Any, row_lookup: dict[Hashable, int]
    ) -> list[SanityCheckFinding]:
        if "Name of Organisation" not in frame:
            return []
        names = frame["Name of Organisation"].fillna("").astype(str)
        normalized = names.str.strip().str.lower()
        duplicate_mask = normalized.duplicated(keep=False)
        findings: list[SanityCheckFinding] = []
        if not duplicate_mask.any():
            return findings

        for idx in frame.index[duplicate_mask]:
            row_id = row_lookup.get(idx, 0)
            organisation = names.loc[idx].strip()
            findings.append(
                SanityCheckFinding(
                    row_id=row_id,
                    organisation=organisation,
                    issue="duplicate_organisation",
                    remediation="Deduplicate or merge duplicate organisation rows before publishing.",
                )
            )
        return findings

    def _summarize_last_run(self) -> dict[str, object]:
        if self._last_report is None:
            return {
                "status": "empty",
                "message": "No pipeline runs have been executed yet.",
            }
        return {
            "status": "ok",
            "metrics": dict(self._last_report.metrics),
            "sanity_issue_count": len(self._last_report.sanity_findings),
        }

    def _list_sanity_issues(self) -> dict[str, object]:
        if self._last_report is None:
            return {"status": "empty", "findings": []}
        return {
            "status": "ok",
            "findings": [
                finding.as_dict() for finding in self._last_report.sanity_findings
            ],
        }
