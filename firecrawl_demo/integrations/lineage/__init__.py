from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, cast

import requests

from firecrawl_demo.core import config, models

ACES_LINEAGE_NS = "https://acesaero.co.za/ns/lineage#"
ACES_CONTEXT_PREFIX = "aces"
CATALOG_CONTACT_EMAIL = "info@acesaero.co.za"
CATALOG_CONTACT_TYPE = "platform-support"


class LineageEmitter(Protocol):
    """Protocol describing emitter implementations for lineage events."""

    def emit(
        self, events: Sequence[dict[str, Any]]
    ) -> None:  # pragma: no cover - interface
        """Publish a batch of OpenLineage events."""


@dataclass(slots=True)
class HttpLineageEmitter:
    """Send OpenLineage events to an HTTP endpoint."""

    url: str
    api_key: str | None = None
    timeout: float = 10.0
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))

    def emit(self, events: Sequence[dict[str, Any]]) -> None:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        for event in events:
            response = requests.post(
                self.url, json=event, headers=headers, timeout=self.timeout
            )
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:  # pragma: no cover - defensive
                self.logger.warning(
                    "openlineage.http_emit_failed status=%s",
                    response.status_code,
                    exc_info=exc,
                )
                raise


@dataclass(slots=True)
class LoggingLineageEmitter:
    """Emit lineage events to application logs (useful for dry runs/tests)."""

    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))

    def emit(self, events: Sequence[dict[str, Any]]) -> None:
        for event in events:
            self.logger.info("openlineage.event %s", event)


@dataclass(slots=True)
class KafkaLineageEmitter:
    """Emit lineage events to a Kafka topic."""

    topic: str
    bootstrap_servers: str
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))
    _producer: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            from kafka import KafkaProducer  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "kafka-python is required for KafkaLineageEmitter"
            ) from exc
        self._producer = KafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda value: json.dumps(value).encode("utf-8"),
        )

    def emit(self, events: Sequence[dict[str, Any]]) -> None:
        for event in events:
            self._producer.send(self.topic, event)
        self._producer.flush()


def _as_uri(value: str | Path | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, Path):
        return value.resolve().as_uri()
    if value.startswith("file://"):
        return value
    return Path(value).resolve().as_uri()


def _extra_uri(value: Any) -> str | None:
    if isinstance(value, (str, Path)):
        return _as_uri(value)
    return None


@dataclass(slots=True)
class LineageContext:
    """Runtime metadata required to emit lineage documents."""

    run_id: str
    namespace: str
    job_name: str
    dataset_name: str
    input_uri: str
    output_uri: str | None = None
    evidence_path: Path | None = None
    dataset_version: str | None = None
    lakehouse_uri: str | None = None
    execution_start: datetime = field(default_factory=lambda: datetime.utcnow())
    extras: dict[str, Any] = field(default_factory=dict)

    def with_lakehouse(
        self,
        uri: str | None,
        version: str | None,
        *,
        manifest_path: Path | None = None,
        fingerprint: str | None = None,
    ) -> LineageContext:
        """Return a new context capturing lakehouse outputs."""

        extras = dict(self.extras)
        if manifest_path is not None:
            extras["lakehouse_manifest"] = manifest_path
        if fingerprint is not None:
            extras["lakehouse_fingerprint"] = fingerprint
        return replace(
            self,
            lakehouse_uri=uri,
            dataset_version=version or self.dataset_version,
            extras=extras,
        )

    def with_version(
        self,
        *,
        version: str | None,
        metadata_path: Path | None = None,
        reproduce_command: Sequence[str] | None = None,
        input_fingerprint: str | None = None,
        output_fingerprint: str | None = None,
        extras: Mapping[str, Any] | None = None,
    ) -> LineageContext:
        """Return a new context enriched with versioning metadata."""

        extras_map = dict(self.extras)
        if metadata_path is not None:
            extras_map["version_metadata"] = metadata_path
        if reproduce_command is not None:
            extras_map["version_reproduce_command"] = tuple(reproduce_command)
        if input_fingerprint is not None:
            extras_map["version_input_fingerprint"] = input_fingerprint
        if output_fingerprint is not None:
            extras_map["version_output_fingerprint"] = output_fingerprint
        if extras:
            extras_map["version_extras"] = dict(extras)
        return replace(
            self,
            dataset_version=version or self.dataset_version,
            extras=extras_map,
        )


@dataclass(frozen=True)
class LineageArtifacts:
    """Paths to stored lineage artefacts for a pipeline run."""

    run_id: str
    openlineage_path: Path
    prov_path: Path
    catalog_path: Path


@dataclass(slots=True)
class LineageManager:
    """Persist lineage artefacts derived from pipeline runs."""

    artifact_root: Path = field(default_factory=lambda: config.LINEAGE.artifact_root)
    namespace: str = field(default_factory=lambda: config.LINEAGE.namespace)
    job_name: str = field(default_factory=lambda: config.LINEAGE.job_name)
    dataset_name: str = field(default_factory=lambda: config.LINEAGE.dataset_name)
    enabled: bool = field(default_factory=lambda: config.LINEAGE.enabled)
    transport: str = field(default_factory=lambda: config.LINEAGE.transport)
    endpoint: str | None = field(default_factory=lambda: config.LINEAGE.endpoint)
    api_key: str | None = field(default_factory=lambda: config.LINEAGE.api_key)
    kafka_topic: str | None = field(default_factory=lambda: config.LINEAGE.kafka_topic)
    kafka_bootstrap_servers: str | None = field(
        default_factory=lambda: config.LINEAGE.kafka_bootstrap_servers
    )
    emitter: LineageEmitter | None = None
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))

    def __post_init__(self) -> None:
        if self.emitter is None:
            self.emitter = self._build_emitter()

    def capture(
        self, report: models.PipelineReport, context: LineageContext
    ) -> LineageArtifacts:
        if not self.enabled:
            artifact_dir = self.artifact_root / "lineage" / context.run_id
            artifact_dir.mkdir(parents=True, exist_ok=True)
            placeholder = artifact_dir / "disabled.json"
            placeholder.write_text(
                json.dumps({"enabled": False, "run_id": context.run_id})
            )
            return LineageArtifacts(
                run_id=context.run_id,
                openlineage_path=placeholder,
                prov_path=placeholder,
                catalog_path=placeholder,
            )

        artifact_dir = self.artifact_root / "lineage" / context.run_id
        artifact_dir.mkdir(parents=True, exist_ok=True)

        completed_at = datetime.utcnow()
        events = build_openlineage_events(report, context, completed_at=completed_at)
        openlineage_path = artifact_dir / "openlineage.json"
        openlineage_path.write_text(json.dumps(events, indent=2, sort_keys=True))

        prov_document = build_prov_document(
            report,
            context,
            artifact_dir=artifact_dir,
            completed_at=completed_at,
        )
        prov_path = artifact_dir / "prov.jsonld"
        prov_path.write_text(json.dumps(prov_document, indent=2, sort_keys=True))

        catalog_entry = build_catalog_entry(
            report,
            context,
            artifact_dir=artifact_dir,
            completed_at=completed_at,
        )
        catalog_path = artifact_dir / "catalog.jsonld"
        catalog_path.write_text(json.dumps(catalog_entry, indent=2, sort_keys=True))

        if self.emitter:
            try:
                self.emitter.emit(events)
            except Exception as exc:  # pragma: no cover - defensive
                self.logger.warning(
                    "openlineage.emit_failed transport=%s",
                    self.transport,
                    exc_info=exc,
                )

        return LineageArtifacts(
            run_id=context.run_id,
            openlineage_path=openlineage_path,
            prov_path=prov_path,
            catalog_path=catalog_path,
        )

    def _build_emitter(self) -> LineageEmitter | None:
        transport = (self.transport or "file").lower()
        if transport in {"file", "disabled", "none"}:
            return None
        if transport == "http":
            if not self.endpoint:
                self.logger.warning("openlineage.http_disabled missing endpoint")
                return None
            return HttpLineageEmitter(
                url=self.endpoint,
                api_key=self.api_key,
                logger=self.logger,
            )
        if transport == "kafka":
            if not self.kafka_topic or not self.kafka_bootstrap_servers:
                self.logger.warning("openlineage.kafka_disabled missing configuration")
                return None
            try:
                return KafkaLineageEmitter(
                    topic=self.kafka_topic,
                    bootstrap_servers=self.kafka_bootstrap_servers,
                    logger=self.logger,
                )
            except RuntimeError as exc:
                self.logger.warning("openlineage.kafka_unavailable", exc_info=exc)
                return None
        if transport == "logging":
            return LoggingLineageEmitter(logger=self.logger)
        self.logger.warning("openlineage.unknown_transport %s", self.transport)
        return None


def _metrics_facet(metrics: dict[str, int]) -> dict[str, Any]:
    return {
        "acesMetrics": {"metrics": metrics},
    }


def _dataset_facets(context: LineageContext, metrics: dict[str, int]) -> dict[str, Any]:
    facets: dict[str, Any] = _metrics_facet(metrics)
    if context.dataset_version:
        facets["datasetVersion"] = {"version": context.dataset_version}
    evidence_uri = _as_uri(context.evidence_path)
    if evidence_uri:
        facets["evidenceLog"] = {"uri": evidence_uri}
    manifest_path = context.extras.get("lakehouse_manifest")
    if manifest_path:
        facets["lakehouseManifest"] = {"uri": _as_uri(manifest_path)}
    if context.lakehouse_uri:
        lakehouse_facet: dict[str, Any] = {"uri": context.lakehouse_uri}
        fingerprint = context.extras.get("lakehouse_fingerprint")
        if fingerprint:
            lakehouse_facet["fingerprint"] = fingerprint
        facets["lakehouse"] = lakehouse_facet
    version_metadata = context.extras.get("version_metadata")
    if version_metadata:
        facets["versionMetadata"] = {"uri": _as_uri(cast(str | Path, version_metadata))}
    reproduce_command = context.extras.get("version_reproduce_command")
    if reproduce_command:
        facets["versionReproduce"] = {"command": list(reproduce_command)}
    versioning_facet: dict[str, Any] = {}
    input_fingerprint = context.extras.get("version_input_fingerprint")
    output_fingerprint = context.extras.get("version_output_fingerprint")
    if input_fingerprint:
        versioning_facet["inputFingerprint"] = input_fingerprint
    if output_fingerprint:
        versioning_facet["outputFingerprint"] = output_fingerprint
    if versioning_facet:
        facets["versioning"] = versioning_facet
    version_extras = context.extras.get("version_extras")
    if isinstance(version_extras, dict) and version_extras:
        facets["versionExtras"] = version_extras
    return facets


def build_openlineage_events(
    report: models.PipelineReport,
    context: LineageContext,
    *,
    completed_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Serialise OpenLineage start/complete events for the run."""

    run = {
        "runId": context.run_id,
    }
    job = {
        "namespace": context.namespace,
        "name": context.job_name,
    }

    inputs = [
        {
            "namespace": context.namespace,
            "name": context.dataset_name,
            "facets": {
                "dataset": {"uri": context.input_uri},
            },
        }
    ]
    outputs = [
        {
            "namespace": context.namespace,
            "name": context.dataset_name,
            "facets": _dataset_facets(context, report.metrics),
        }
    ]

    start_event = {
        "eventType": "START",
        "eventTime": context.execution_start.isoformat(),
        "run": run,
        "job": job,
        "inputs": inputs,
    }
    complete_event = {
        "eventType": "COMPLETE",
        "eventTime": (completed_at or datetime.utcnow()).isoformat(),
        "run": run,
        "job": job,
        "inputs": inputs,
        "outputs": outputs,
    }
    return [start_event, complete_event]


def build_prov_document(
    report: models.PipelineReport,
    context: LineageContext,
    *,
    artifact_dir: Path | None = None,
    completed_at: datetime | None = None,
) -> dict[str, Any]:
    """Generate a PROV-O JSON-LD document capturing the run."""

    completed = (completed_at or datetime.utcnow()).isoformat()
    activity_id = f"urn:uuid:{context.run_id}"
    agent_id = f"urn:aces:agent:{context.job_name}"

    used_entities: list[dict[str, Any]] = [
        {
            "@id": context.input_uri,
            "@type": "prov:Entity",
            "dct:title": context.dataset_name,
            "dct:identifier": f"urn:aces:dataset:{context.dataset_name}",
        }
    ]
    if context.evidence_path:
        used_entities.append(
            {
                "@id": _as_uri(context.evidence_path),
                "@type": "prov:Entity",
                "dct:title": "Evidence Log",
                f"{ACES_CONTEXT_PREFIX}:evidenceCount": len(report.evidence_log),
            }
        )

    generated_entities: list[dict[str, Any]] = []
    output_entity: dict[str, Any] | None = None
    if context.output_uri:
        output_entity = {
            "@id": context.output_uri,
            "@type": "prov:Entity",
            "dct:title": f"{context.dataset_name} (enriched)",
            "prov:wasDerivedFrom": context.input_uri,
            f"{ACES_CONTEXT_PREFIX}:metrics": report.metrics,
        }
        if context.dataset_version:
            output_entity["dct:identifier"] = (
                f"urn:aces:dataset-version:{context.dataset_version}"
            )
        generated_entities.append(output_entity)
    if context.lakehouse_uri:
        generated_entities.append(
            {
                "@id": context.lakehouse_uri,
                "@type": "prov:Entity",
                "dct:title": f"{context.dataset_name} Lakehouse Table",
                "dct:format": f"application/{config.LAKEHOUSE.backend}",
            }
        )

    manifest_uri = _extra_uri(context.extras.get("lakehouse_manifest"))
    if manifest_uri:
        generated_entities.append(
            {
                "@id": manifest_uri,
                "@type": "prov:Entity",
                "dct:title": "Lakehouse Manifest",
            }
        )
    version_uri = _extra_uri(context.extras.get("version_metadata"))
    if version_uri:
        generated_entities.append(
            {
                "@id": version_uri,
                "@type": "prov:Entity",
                "dct:title": "Version Manifest",
            }
        )
    if artifact_dir:
        generated_entities.append(
            {
                "@id": artifact_dir.resolve().as_uri(),
                "@type": "prov:Entity",
                "dct:title": "Lineage Artefact Bundle",
            }
        )

    agent = {
        "@id": agent_id,
        "@type": "prov:Agent",
        "prov:type": "prov:SoftwareAgent",
        "dct:title": f"{context.job_name} pipeline",
    }

    activity = {
        "@id": activity_id,
        "@type": "prov:Activity",
        "prov:startedAtTime": context.execution_start.isoformat(),
        "prov:endedAtTime": completed,
        "prov:used": [entity["@id"] for entity in used_entities],
        "prov:generated": [entity["@id"] for entity in generated_entities],
        "prov:wasAssociatedWith": agent_id,
        f"{ACES_CONTEXT_PREFIX}:metrics": report.metrics,
        f"{ACES_CONTEXT_PREFIX}:qualityIssues": len(report.quality_issues),
        f"{ACES_CONTEXT_PREFIX}:sanityFindings": len(report.sanity_findings),
    }

    if output_entity is not None and report.quality_issues:
        output_entity[f"{ACES_CONTEXT_PREFIX}:qualityIssueCodes"] = sorted(
            {issue.code for issue in report.quality_issues}
        )
    if output_entity is not None and report.rollback_plan:
        output_entity[f"{ACES_CONTEXT_PREFIX}:rollbackPlan"] = (
            report.rollback_plan.as_dict()
        )

    graph: list[dict[str, Any]] = [activity, agent, *used_entities, *generated_entities]
    return {
        "@context": {
            "prov": "http://www.w3.org/ns/prov#",
            "dct": "http://purl.org/dc/terms/",
            ACES_CONTEXT_PREFIX: ACES_LINEAGE_NS,
        },
        "@graph": graph,
    }


def build_catalog_entry(
    report: models.PipelineReport,
    context: LineageContext,
    *,
    artifact_dir: Path | None = None,
    completed_at: datetime | None = None,
) -> dict[str, Any]:
    """Produce a DCAT dataset entry enriched with provenance metadata."""

    completed = (completed_at or datetime.utcnow()).isoformat()
    identifier = context.dataset_version or context.run_id
    run_uri = f"urn:uuid:{context.run_id}"
    distributions: list[dict[str, Any]] = []
    dataset: dict[str, Any] = {
        "@context": {
            "dcat": "http://www.w3.org/ns/dcat#",
            "dct": "http://purl.org/dc/terms/",
            "prov": "http://www.w3.org/ns/prov#",
            "schema": "http://schema.org/",
            "dqv": "http://www.w3.org/ns/dqv#",
            ACES_CONTEXT_PREFIX: ACES_LINEAGE_NS,
        },
        "@type": "dcat:Dataset",
        "dct:title": f"{context.dataset_name} enrichment",
        "dct:description": (
            "Evidence-backed enrichment run with lineage, quality, and "
            "reproducibility metadata."
        ),
        "dct:identifier": f"urn:aces:{identifier}",
        "dct:isVersionOf": context.dataset_name,
        "dct:issued": context.execution_start.date().isoformat(),
        "dct:modified": completed,
        "dct:language": "en",
        "dct:source": context.input_uri,
        "dct:creator": "ACES Aerodynamics Platform Team",
        "dct:publisher": "ACES Aerodynamics",
        "dct:accrualPeriodicity": "irregular",
        "dct:temporal": {
            "@type": "dct:PeriodOfTime",
            "dct:start": context.execution_start.isoformat(),
            "dct:end": completed,
        },
        "prov:wasGeneratedBy": run_uri,
        "dcat:keyword": [
            "enrichment",
            "flight-schools",
            "evidence",
            "provenance",
        ],
        "dcat:distribution": distributions,
        "dcat:contactPoint": {
            "@type": "schema:ContactPoint",
            "schema:email": CATALOG_CONTACT_EMAIL,
            "schema:contactType": CATALOG_CONTACT_TYPE,
        },
        "dct:conformsTo": [
            {"@id": "https://openlineage.io/spec/1-0-0"},
            {"@id": "https://www.w3.org/TR/vocab-dcat-3/"},
        ],
        f"{ACES_CONTEXT_PREFIX}:evidenceCount": len(report.evidence_log),
        f"{ACES_CONTEXT_PREFIX}:qualityIssues": len(report.quality_issues),
    }

    measurements = [
        {
            "@type": "dqv:QualityMeasurement",
            "dqv:isMeasurementOf": {
                "@id": f"{ACES_LINEAGE_NS}metric/{metric}",
            },
            "dqv:value": value,
            "dqv:computedOn": context.output_uri or context.input_uri,
        }
        for metric, value in sorted(report.metrics.items())
    ]
    if measurements:
        dataset["dqv:hasQualityMeasurement"] = measurements

    notes: dict[str, Any] = cast(dict[str, Any], dataset.setdefault("notes", {}))

    if context.output_uri:
        distributions.append(
            {
                "@type": "dcat:Distribution",
                "dcat:accessURL": context.output_uri,
                "dct:format": "text/csv",
                "dct:description": "Curated enrichment output",
            }
        )
    if context.lakehouse_uri:
        distributions.append(
            {
                "@type": "dcat:Distribution",
                "dcat:accessURL": context.lakehouse_uri,
                "dct:format": f"application/{config.LAKEHOUSE.backend}",
                "dct:description": "Lakehouse table reference",
            }
        )
    evidence_uri = _as_uri(context.evidence_path)
    if evidence_uri:
        distributions.append(
            {
                "@type": "dcat:Distribution",
                "dcat:accessURL": evidence_uri,
                "dct:format": "text/csv",
                "dct:description": "Evidence log entries supporting enrichment decisions",
            }
        )
        notes["evidenceLog"] = evidence_uri

    manifest_uri = _extra_uri(context.extras.get("lakehouse_manifest"))
    if manifest_uri:
        distributions.append(
            {
                "@type": "dcat:Distribution",
                "dcat:accessURL": manifest_uri,
                "dct:format": "application/json",
                "dct:description": "Lakehouse manifest metadata",
            }
        )
        notes["lakehouseManifest"] = manifest_uri

    version_uri = _extra_uri(context.extras.get("version_metadata"))
    if version_uri:
        distributions.append(
            {
                "@type": "dcat:Distribution",
                "dcat:accessURL": version_uri,
                "dct:format": "application/json",
                "dct:description": "Version manifest and reproducibility metadata",
            }
        )
        notes["versionMetadata"] = version_uri

    if artifact_dir:
        distributions.append(
            {
                "@type": "dcat:Distribution",
                "dcat:accessURL": artifact_dir.resolve().as_uri(),
                "dct:format": "application/ld+json",
                "dct:description": "Lineage artefacts (OpenLineage, PROV-O, DCAT)",
            }
        )

    reproduce_command = context.extras.get("version_reproduce_command")
    if reproduce_command:
        notes["reproduceCommand"] = list(reproduce_command)
    version_extras = context.extras.get("version_extras")
    if isinstance(version_extras, dict) and version_extras:
        notes["versionExtras"] = version_extras

    return dataset


__all__ = [
    "LineageContext",
    "LineageArtifacts",
    "LineageManager",
    "LineageEmitter",
    "HttpLineageEmitter",
    "KafkaLineageEmitter",
    "LoggingLineageEmitter",
    "build_openlineage_events",
    "build_prov_document",
    "build_catalog_entry",
]
