"""Pipeline orchestration utilities for enrichment and validation."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Hashable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from math import ceil
from pathlib import Path
from statistics import mean
from time import monotonic
from typing import Any, cast

try:
    import pandas as pd

    _PANDAS_AVAILABLE = True
except ImportError:
    pd = None  # type: ignore
    _PANDAS_AVAILABLE = False

from watercrawl.application.interfaces import EvidenceSink, PipelineService
from watercrawl.application.progress import (
    NullPipelineProgressListener,
    PipelineProgressListener,
)
from watercrawl.application.quality import QualityGate
from watercrawl.application.row_processing import (
    RowProcessingRequest,
    RowProcessingResult,
    compose_evidence_notes,
    process_row,
)
from watercrawl.core import cache as global_cache
from watercrawl.core import config
from watercrawl.core.normalization import (
    ColumnConflictResolver,
    MergeDuplicatesResult,
    merge_duplicate_records,
)

if _PANDAS_AVAILABLE:
    from watercrawl.core.excel import EXPECTED_COLUMNS, read_dataset, write_dataset
else:
    EXPECTED_COLUMNS = []  # type: ignore

    def read_dataset(path: Any) -> Any:  # type: ignore
        raise NotImplementedError("Dataset operations require pandas (Python < 3.14)")

    def write_dataset(df: Any, path: Any) -> None:  # type: ignore
        raise NotImplementedError("Dataset operations require pandas (Python < 3.14)")


from watercrawl.domain import relationships
from watercrawl.domain.compliance import normalize_province
from watercrawl.domain.contracts import PipelineReportContract
from watercrawl.domain.models import (
    ComplianceScheduleEntry,
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
from watercrawl.domain.validation import DatasetValidator
from watercrawl.infrastructure.evidence import NullEvidenceSink
from watercrawl.integrations.adapters.research import (
    NullResearchAdapter,
    ResearchAdapter,
    ResearchFinding,
    lookup_with_adapter_async,
)
from watercrawl.integrations.integration_plugins import (
    PluginLookupError,
    instantiate_plugin,
)
from watercrawl.integrations.storage.lakehouse import LocalLakehouseWriter
from watercrawl.integrations.storage.versioning import (
    VersioningManager,
    fingerprint_dataframe,
)
from watercrawl.integrations.telemetry.alerts import send_slack_alert
from watercrawl.integrations.telemetry.drift_dashboard import (
    append_alert_report,
    write_prometheus_metrics,
)
from watercrawl.integrations.telemetry.graph_semantics import (
    GraphSemanticsReport,
)
from watercrawl.integrations.telemetry.lineage import LineageContext, LineageManager

logger = logging.getLogger(__name__)


_CONNECTOR_PUBLISHERS = {
    "regulator": "South African Civil Aviation Authority",
    "press": "Press Coverage",
    "corporate_filings": "Companies and Intellectual Property Commission",
    "social": "Social Media Monitoring",
}


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
    source_info: Mapping[str, Any] | None = None


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
    connector_latency: defaultdict[str, list[float]] = field(
        default_factory=lambda: defaultdict(list)
    )
    connector_success: defaultdict[str, list[bool]] = field(
        default_factory=lambda: defaultdict(list)
    )
    confidence_deltas: list[tuple[int, int, int]] = field(default_factory=list)

    def record_queue_latency(self, latency: float) -> None:
        self.queue_latencies.append(latency)

    def record_connector_metrics(self, finding: ResearchFinding) -> None:
        for name, evidence in finding.evidence_by_connector.items():
            if evidence.latency_seconds is not None:
                self.connector_latency[name].append(evidence.latency_seconds)
            self.connector_success[name].append(evidence.success)
        if finding.validation is not None:
            report = finding.validation
            self.confidence_deltas.append(
                (
                    report.base_confidence,
                    report.confidence_adjustment,
                    report.final_confidence,
                )
            )


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
                # prefer direct attribute assignment instead of setattr with a constant name
                target._lookup_executor = executor
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

    async def __aenter__(self) -> _LookupCoordinator:
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
            self._metrics.record_connector_metrics(finding)
            return _LookupResult(
                state=state,
                finding=finding,
                retries=retries,
            )

    def _load_from_cache(self, key: tuple[str, str]) -> ResearchFinding | None:
        if self._cache_ttl_hours is None:
            return None
        cached = global_cache.load(key, max_age_hours=self._cache_ttl_hours)
        if isinstance(cached, ResearchFinding):
            return cached
        return None

    async def _attempt_lookup(self, state: _RowState) -> tuple[ResearchFinding, int]:
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
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "Retrying research lookup (%s/%s) for %s (%s): %s",
                        retries,
                        self._max_retries,
                        state.working_record.name,
                        state.working_record.province,
                        exc,
                    )
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

    def _compose_evidence_notes(
        self,
        finding: ResearchFinding,
        original_row: Mapping[str, Any],
        record: SchoolRecord,
        *,
        has_official_source: bool,
        total_source_count: int,
        fresh_source_count: int,
        sanity_notes: Sequence[str] | None = None,
    ) -> str:
        """Backward-compatible shim delegating to row_processing.compose_evidence_notes."""

        return compose_evidence_notes(
            finding,
            original_row,
            record,
            has_official_source=has_official_source,
            total_source_count=total_source_count,
            fresh_source_count=fresh_source_count,
            sanity_notes=sanity_notes,
        )

    def _update_relationship_state(
        self,
        *,
        organisations: dict[str, relationships.Organisation],
        people: dict[str, relationships.Person],
        sources: dict[str, relationships.SourceDocument],
        edges: dict[tuple[str, str, str], relationships.EvidenceLink],
        row_state: _RowState,
        row_result: RowProcessingResult,
        finding: ResearchFinding,
    ) -> None:
        now = datetime.now(UTC)
        name = row_result.record.name or row_state.original_record.name
        if not name:
            name = f"Row {row_state.row_id}"
        organisation_id = relationships.canonical_id("organisation", name)
        provinces = (
            {row_result.record.province}
            if getattr(row_result.record, "province", None)
            else set()
        )
        statuses = (
            {row_result.record.status}
            if getattr(row_result.record, "status", None)
            else set()
        )
        organisation = relationships.Organisation(
            identifier=organisation_id,
            name=name,
            provinces=provinces,
            statuses=statuses,
            website_url=row_result.record.website_url,
            aliases=set(finding.alternate_names),
            provenance={
                relationships.ProvenanceTag(
                    source="pipeline:dataset",
                    retrieved_at=now,
                    notes=f"row:{row_state.row_id}",
                )
            },
        )
        dataset_sources = []
        if row_state.source_info:
            dataset_sources = list(row_state.source_info.get("sources", []))
            for source_entry in dataset_sources:
                source_path = Path(str(source_entry.get("path", "")))
                provenance_tag = relationships.ProvenanceTag(
                    source=f"dataset:{source_path.name}",
                    retrieved_at=now,
                    notes=f"row:{row_state.row_id};source_row:{source_entry.get('source_row')}",
                )
                organisation.provenance.add(provenance_tag)
        existing_org = organisations.get(organisation_id)
        if existing_org:
            organisation = relationships.merge_organisations(existing_org, organisation)
        organisations[organisation_id] = organisation

        def _store_edge(
            key: tuple[str, str, str], link: relationships.EvidenceLink
        ) -> None:
            existing = edges.get(key)
            if existing:
                edges[key] = relationships.merge_evidence_links(existing, link)
            else:
                edges[key] = link

        contact_name = row_result.record.contact_person or finding.contact_person
        person_id: str | None = None
        if contact_name:
            person_id = relationships.canonical_id("person", contact_name)
            emails = {
                value
                for value in (
                    row_result.record.contact_email,
                    finding.contact_email,
                )
                if value
            }
            phones = {
                value
                for value in (
                    row_result.record.contact_number,
                    finding.contact_phone,
                )
                if value
            }
            person = relationships.Person(
                identifier=person_id,
                name=contact_name,
                role="Primary Contact",
                emails=emails,
                phones=phones,
                organisations={organisation_id},
                provenance={
                    relationships.ProvenanceTag(
                        source="pipeline:dataset",
                        retrieved_at=now,
                        notes=f"row:{row_state.row_id}",
                    )
                },
            )
            if finding.contact_person and finding.contact_person != contact_name:
                person.provenance.add(
                    relationships.ProvenanceTag(
                        source="pipeline:research",
                        retrieved_at=now,
                        notes="adapter_contact",
                    )
                )
            existing_person = people.get(person_id)
            if existing_person:
                person = relationships.merge_people(existing_person, person)
            people[person_id] = person
            organisations[organisation_id].contacts.add(person_id)
            if dataset_sources:
                for source_entry in dataset_sources:
                    source_path = Path(str(source_entry.get("path", "")))
                    person.provenance.add(
                        relationships.ProvenanceTag(
                            source=f"dataset:{source_path.name}",
                            retrieved_at=now,
                            notes=f"row:{row_state.row_id};source_row:{source_entry.get('source_row')}",
                        )
                    )
            contact_edge = relationships.EvidenceLink(
                source=organisation_id,
                target=person_id,
                kind="has_contact",
                weight=1.0,
                provenance={
                    relationships.ProvenanceTag(
                        source="pipeline:dataset",
                        retrieved_at=now,
                        notes=f"row:{row_state.row_id}",
                    )
                },
                attributes={"status": row_result.record.status or ""},
            )
            _store_edge((organisation_id, person_id, "has_contact"), contact_edge)

        def _record_source(
            url: str, *, connector: str | None, note: str | None
        ) -> None:
            if not url:
                return
            document_id = relationships.canonical_id("source", url)
            provenance_tag = relationships.ProvenanceTag(
                source=url,
                connector=connector,
                retrieved_at=now,
                notes=note,
            )
            publisher = _CONNECTOR_PUBLISHERS.get(connector)
            document = relationships.SourceDocument(
                identifier=document_id,
                uri=url,
                publisher=publisher,
                connector=connector,
                tags={connector} if connector else set(),
                provenance={provenance_tag},
            )
            existing_document = sources.get(document_id)
            if existing_document:
                document = relationships.merge_sources(existing_document, document)
            sources[document_id] = document
            evidence_link = relationships.EvidenceLink(
                source=organisation_id,
                target=document_id,
                kind="corroborated_by",
                weight=1.0,
                provenance={provenance_tag},
                attributes={"connector": connector} if connector else {},
            )
            _store_edge(
                (organisation_id, document_id, "corroborated_by"), evidence_link
            )
            if person_id and person_id in people:
                contact_link = relationships.EvidenceLink(
                    source=person_id,
                    target=document_id,
                    kind="contact_evidence",
                    weight=1.0,
                    provenance={provenance_tag},
                    attributes={"connector": connector} if connector else {},
                )
                _store_edge((person_id, document_id, "contact_evidence"), contact_link)

        seen_sources: set[str] = set()
        for source in row_result.sources:
            if source not in seen_sources:
                seen_sources.add(source)
                _record_source(source, connector=None, note="row_sanity")
        for source in finding.sources:
            if source not in seen_sources:
                seen_sources.add(source)
                _record_source(source, connector=None, note="research_finding")

        for connector_name, connector_evidence in finding.evidence_by_connector.items():
            connector_tag = relationships.ProvenanceTag(
                source=connector_name,
                connector=connector_name,
                retrieved_at=now,
                notes="connector_observation",
            )
            organisations[organisation_id].provenance.add(connector_tag)
            if person_id and person_id in people:
                people[person_id].provenance.add(connector_tag)
            summary = (
                "; ".join(connector_evidence.notes)
                if connector_evidence.notes
                else None
            )
            for source in connector_evidence.sources:
                if source not in seen_sources:
                    seen_sources.add(source)
                _record_source(source, connector=connector_name, note=summary)

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
        compliance_schedule_entries: list[ComplianceScheduleEntry] = []
        row_number_lookup: dict[Hashable, int] = {}
        quality_issues: list[QualityIssue] = []
        rollback_actions: list[RollbackAction] = []
        quality_rejections = 0
        listener = progress or NullPipelineProgressListener()
        relationship_orgs: dict[str, relationships.Organisation] = {}
        relationship_people: dict[str, relationships.Person] = {}
        relationship_sources: dict[str, relationships.SourceDocument] = {}
        relationship_edges: dict[tuple[str, str, str], relationships.EvidenceLink] = {}

        listener.on_start(len(working_frame))

        row_states: list[_RowState] = []
        column_updates: dict[str, dict[Hashable, Any]] = defaultdict(dict)
        cleared_cells: dict[str, set[Hashable]] = defaultdict(set)
        source_metadata: dict[int, Mapping[str, Any]] = {}
        try:
            for entry in working_frame.attrs.get("source_rows", []):
                row_idx = int(entry.get("row", len(source_metadata)))
                source_metadata[row_idx] = entry
        except AttributeError:
            source_metadata = {}
        for position, row in enumerate(working_frame.itertuples(index=True, name=None)):
            idx = row[0]
            row_values = dict(zip(working_frame.columns, row[1:]))
            original_record = SchoolRecord.from_dataframe_row(row_values)
            record = replace(original_record)
            record.province = normalize_province(record.province)
            column_updates["Province"][idx] = record.province
            row_id = position + 2
            row_number_lookup[idx] = row_id
            row_states.append(
                _RowState(
                    position=position,
                    index=idx,
                    row_id=row_id,
                    original_row=row_values,
                    original_record=original_record,
                    working_record=record,
                    source_info=source_metadata.get(position),
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

        for result in lookup_results:
            state = result.state
            position = state.position
            idx = state.index
            row_id = state.row_id
            original_record = state.original_record
            request = RowProcessingRequest(
                row_id=row_id,
                original_row=state.original_row,
                original_record=original_record,
                working_record=replace(state.working_record),
                finding=result.finding,
            )
            row_result = process_row(request, quality_gate=self.quality_gate)

            if row_result.sanity_findings:
                sanity_findings.extend(row_result.sanity_findings)
            if row_result.quality_rejected:
                quality_rejections += 1
            if row_result.quality_issues:
                quality_issues.extend(row_result.quality_issues)
            if row_result.rollback_action:
                rollback_actions.append(row_result.rollback_action)
            if row_result.evidence_record is not None:
                evidence_records.append(row_result.evidence_record)
            if row_result.follow_up_records:
                evidence_records.extend(row_result.follow_up_records)
            if row_result.compliance is not None:
                compliance_schedule_entries.append(
                    ComplianceScheduleEntry(
                        row_id=row_id,
                        organisation=row_result.record.name
                        or state.original_record.name,
                        status=row_result.record.status,
                        last_verified_at=row_result.compliance.last_verified_at,
                        next_review_due=row_result.compliance.next_review_due,
                        mx_failure_count=row_result.compliance.mx_failure_count,
                        tasks=tuple(row_result.compliance.recommended_tasks),
                        lawful_basis=row_result.compliance.lawful_basis,
                        contact_purpose=row_result.compliance.contact_purpose,
                    )
                )
            if row_result.updated and not row_result.quality_rejected:
                enriched_rows += 1

            cleared_for_row = set(row_result.cleared_columns)
            for column in cleared_for_row:
                cleared_cells[column].add(idx)
            record_map = row_result.record.as_dict()
            for column, value in record_map.items():
                if column in cleared_for_row:
                    continue
                if value is not None:
                    column_updates[column][idx] = value

            listener.on_row_processed(position, row_result.updated, row_result.record)
            self._update_relationship_state(
                organisations=relationship_orgs,
                people=relationship_people,
                sources=relationship_sources,
                edges=relationship_edges,
                row_state=state,
                row_result=row_result,
                finding=result.finding,
            )

        if column_updates or cleared_cells:
            touched_columns = set(column_updates) | set(cleared_cells)
            if _PANDAS_AVAILABLE:
                for column in touched_columns:
                    series = working_frame_cast[column]
                    dtype = series.dtype
                    if not (
                        pd.api.types.is_object_dtype(dtype)
                        or pd.api.types.is_string_dtype(dtype)
                    ):
                        working_frame_cast[column] = series.astype("object")
            for column, entries in column_updates.items():
                if not entries:
                    continue
                indices, values = zip(*entries.items())
                working_frame_cast.loc[list(indices), column] = list(values)
            for column, indices in cleared_cells.items():
                if indices:
                    working_frame_cast.loc[list(indices), column] = ""

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
            max(lookup_metrics.queue_latencies)
            if lookup_metrics.queue_latencies
            else 0.0
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
            compliance_schedule=compliance_schedule_entries,
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
                report.graph_semantics = cast(GraphSemanticsReport | None, graph_report)
                if graph_report and getattr(graph_report, "issues", None):
                    metrics["graph_semantics_issues"] = len(
                        getattr(graph_report, "issues", [])
                    )
            builder = self.graph_semantics_toolkit.get("build_relationship_graph")
            if callable(builder) and relationship_orgs:
                try:
                    snapshot = builder(
                        organisations=list(relationship_orgs.values()),
                        people=list(relationship_people.values()),
                        sources=list(relationship_sources.values()),
                        evidence=list(relationship_edges.values()),
                        graphml_path=config.RELATIONSHIPS_GRAPHML,
                        nodes_csv_path=config.RELATIONSHIPS_CSV,
                        edges_csv_path=config.RELATIONSHIPS_EDGES_CSV,
                    )
                except Exception as exc:  # pragma: no cover - defensive guard
                    logger.warning(
                        "Relationship graph export failed: %s", exc, exc_info=exc
                    )
                else:
                    report.relationship_graph = snapshot
                    metrics["relationship_graph_nodes"] = snapshot.node_count
                    metrics["relationship_graph_edges"] = snapshot.edge_count
                    metrics["relationship_anomalies"] = len(snapshot.anomalies)
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
                            "`watercrawl.integrations.telemetry.drift.save_baseline` "
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
                    drift_report = cast(
                        Any,
                        comparator(
                            frame=report.refined_dataframe,
                            baseline=baseline,
                            threshold=config.DRIFT.threshold,
                        ),
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
        input_path: Path | Sequence[Path],
        output_path: Path | None = None,
        *,
        progress: PipelineProgressListener | None = None,
        lineage_context: LineageContext | None = None,
        sheet_map: Mapping[str, str] | None = None,
    ) -> PipelineReport:
        """Asynchronously process a dataset file through the pipeline."""
        dataset = read_dataset(input_path, sheet_map=sheet_map)
        active_context = lineage_context
        if active_context:
            if isinstance(input_path, Path):
                input_uri = input_path.resolve().as_uri()
            else:
                input_uri = ",".join(
                    str(candidate.resolve()) for candidate in input_path
                )
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
        input_path: Path | Sequence[Path],
        output_path: Path | None = None,
        *,
        progress: PipelineProgressListener | None = None,
        lineage_context: LineageContext | None = None,
        sheet_map: Mapping[str, str] | None = None,
    ) -> PipelineReport:
        """Synchronously process a dataset file through the pipeline."""
        dataset = read_dataset(input_path, sheet_map=sheet_map)
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
            # type: ignore
            return pd.DataFrame(list(rows_obj), columns=list(EXPECTED_COLUMNS))
        raise ValueError("Payload must include 'path' or 'rows'")

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


@dataclass
class MultiSourcePipeline(Pipeline):
    """Pipeline variant that consolidates multiple dataset sources."""

    conflict_resolver: ColumnConflictResolver = field(
        default_factory=lambda: ColumnConflictResolver(
            getattr(config, "COLUMN_DESCRIPTORS", ())
        )
    )

    def _prepare_multi_source_frame(
        self,
        input_path: Path | Sequence[Path],
        *,
        sheet_map: Mapping[str, str] | None = None,
    ) -> tuple[pd.DataFrame, dict[str, Any], MergeDuplicatesResult]:
        dataset = read_dataset(input_path, sheet_map=sheet_map)
        original_rows = dataset.attrs.get("source_rows", [])
        original_files = set(dataset.attrs.get("source_files", []))
        merge_result = merge_duplicate_records(
            dataset, key_column="Name of Organisation", resolver=self.conflict_resolver
        )
        metadata_by_index: dict[int, Mapping[str, Any]] = {}
        if isinstance(original_rows, list):
            for entry in original_rows:
                if isinstance(entry, Mapping):
                    row_idx = int(entry.get("row", len(metadata_by_index)))
                    metadata_by_index[row_idx] = entry

        rows_meta: list[dict[str, Any]] = []
        duplicate_groups = 0
        conflict_count = 0
        for new_index, trace in enumerate(merge_result.traces):
            if len(trace.source_indices) > 1:
                duplicate_groups += 1
            conflict_count += len(trace.conflicts)
            sources = [
                dict(metadata_by_index.get(idx, {}))
                for idx in trace.source_indices
                if idx in metadata_by_index
            ]
            rows_meta.append(
                {
                    "row": new_index,
                    "key": trace.key,
                    "sources": sources,
                    "conflicts": [asdict(conflict) for conflict in trace.conflicts],
                }
            )

        merged_frame = merge_result.merged_frame
        merged_frame.attrs.update(dataset.attrs)
        merged_frame.attrs["source_rows"] = rows_meta
        metadata = {
            "files": original_files,
            "rows": rows_meta,
            "duplicate_groups": duplicate_groups,
            "conflict_count": conflict_count,
            "raw_rows": len(original_rows),
        }
        merged_frame.attrs["multi_source"] = metadata
        return merged_frame, metadata, merge_result

    def _apply_multi_source_metadata(
        self, report: PipelineReport, metadata: dict[str, Any], frame: Any
    ) -> None:
        report.metrics["multi_source_files"] = float(len(metadata.get("files", [])))
        report.metrics["multi_source_raw_rows"] = float(metadata.get("raw_rows", 0))
        report.metrics["multi_source_rows"] = float(len(metadata.get("rows", [])))
        report.metrics["multi_source_duplicate_groups"] = float(
            metadata.get("duplicate_groups", 0)
        )
        report.metrics["multi_source_conflicts"] = float(
            metadata.get("conflict_count", 0)
        )
        if hasattr(report.refined_dataframe, "attrs"):
            report.refined_dataframe.attrs.update(frame.attrs)
            report.refined_dataframe.attrs["multi_source"] = metadata

    def run_file(
        self,
        input_path: Path | Sequence[Path],
        output_path: Path | None = None,
        *,
        progress: PipelineProgressListener | None = None,
        lineage_context: LineageContext | None = None,
        sheet_map: Mapping[str, str] | None = None,
    ) -> PipelineReport:
        frame, metadata, _ = self._prepare_multi_source_frame(
            input_path, sheet_map=sheet_map
        )
        report = self.run_dataframe(
            frame, progress=progress, lineage_context=lineage_context
        )
        self._apply_multi_source_metadata(report, metadata, frame)
        if output_path:
            write_dataset(report.refined_dataframe, output_path)
        return report

    async def run_file_async(
        self,
        input_path: Path | Sequence[Path],
        output_path: Path | None = None,
        *,
        progress: PipelineProgressListener | None = None,
        lineage_context: LineageContext | None = None,
        sheet_map: Mapping[str, str] | None = None,
    ) -> PipelineReport:
        frame, metadata, _ = self._prepare_multi_source_frame(
            input_path, sheet_map=sheet_map
        )
        report = await self.run_dataframe_async(
            frame, progress=progress, lineage_context=lineage_context
        )
        self._apply_multi_source_metadata(report, metadata, frame)
        if output_path:
            write_dataset(report.refined_dataframe, output_path)
        return report
