from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace
from time import monotonic
from typing import Callable, Sequence

from watercrawl.core import config

from .connectors import (
    ConnectorEvidence,
    ConnectorObservation,
    ConnectorRequest,
    ConnectorResult,
    CorporateFilingsConnector,
    PressConnector,
    RegulatorConnector,
    ResearchConnector,
    SocialConnector,
)
from .core import ResearchFinding, merge_findings
from .validators import ValidationReport, cross_validate_findings

logger = logging.getLogger(__name__)

_CONFIDENCE_WEIGHTS = {
    "regulator": 80,
    "press": 60,
    "corporate_filings": 55,
    "social": 45,
}

_CONNECTOR_FACTORIES: dict[str, Callable[[], ResearchConnector]] = {
    "regulator": RegulatorConnector,
    "press": PressConnector,
    "corporate_filings": CorporateFilingsConnector,
    "social": SocialConnector,
}


def build_default_connectors() -> list[ResearchConnector]:
    """Instantiate connectors enabled by the active refinement profile."""

    connectors: list[ResearchConnector] = []
    settings_map = getattr(config, "RESEARCH_CONNECTOR_SETTINGS", {})
    for name, factory in _CONNECTOR_FACTORIES.items():
        settings = settings_map.get(name, {})
        if bool(settings.get("enabled", True)):
            try:
                connectors.append(factory())
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.warning("Failed to initialise %s connector: %s", name, exc)
    return connectors


def _confidence_from_result(result: ConnectorResult) -> int:
    if not result.success:
        return 0
    return _CONFIDENCE_WEIGHTS.get(result.connector, 40)


@dataclass
class MultiSourceResearchAdapter:
    """Compose multiple deterministic connectors into a single adapter."""

    connectors: tuple[ResearchConnector, ...] = ()
    validator: Callable[
        [ResearchFinding, Sequence[ConnectorResult]], ValidationReport
    ] = cross_validate_findings

    def __post_init__(self) -> None:
        if not self.connectors:
            self.connectors = tuple(build_default_connectors())

    def lookup(self, organisation: str, province: str) -> ResearchFinding:
        results = self._collect_results(organisation, province)
        finding = self._merge_results(results)
        validation = self.validator(finding, results)
        evidence = {
            result.connector: ConnectorEvidence(
                connector=result.connector,
                sources=list(result.sources),
                notes=list(result.notes) if result.notes else [],
                latency_seconds=result.latency_seconds,
                success=result.success,
                privacy_filtered_fields=result.privacy_filtered_fields,
            )
            for result in results
        }
        return replace(
            finding,
            confidence=validation.final_confidence,
            validation=validation,
            evidence_by_connector=evidence,
        )

    async def lookup_async(self, organisation: str, province: str) -> ResearchFinding:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.lookup, organisation, province)

    def _collect_results(
        self, organisation: str, province: str
    ) -> list[ConnectorResult]:
        results: list[ConnectorResult] = []
        for connector in self.connectors:
            request = self._build_request(connector.name, organisation, province)
            start = monotonic()
            try:
                result = connector.collect(request)
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.warning(
                    "Connector %s failed for %s (%s): %s",
                    connector.name,
                    organisation,
                    province,
                    exc,
                    exc_info=exc,
                )
                result = ConnectorResult(
                    connector=connector.name,
                    observation=ConnectorObservation(),
                    notes=[f"Connector {connector.name} failed: {exc}"],
                    success=False,
                    latency_seconds=monotonic() - start,
                    error=str(exc),
                )
            if result.latency_seconds is None:
                result = replace(result, latency_seconds=monotonic() - start)
            results.append(result)
        return results

    def _merge_results(self, results: Sequence[ConnectorResult]) -> ResearchFinding:
        findings: list[ResearchFinding] = []
        for result in results:
            obs = result.observation
            findings.append(
                ResearchFinding(
                    website_url=obs.website_url,
                    contact_person=obs.contact_person,
                    contact_email=obs.contact_email,
                    contact_phone=obs.contact_phone,
                    sources=list(result.sources),
                    notes="; ".join(result.notes) if result.notes else "",
                    confidence=_confidence_from_result(result),
                    alternate_names=list(obs.alternate_names),
                    investigation_notes=list(obs.notes),
                    physical_address=obs.physical_address,
                )
            )
        merged = merge_findings(*findings) if findings else ResearchFinding()
        base_confidence = max((item.confidence for item in findings), default=0)
        return replace(merged, confidence=base_confidence)

    def _build_request(
        self, connector_name: str, organisation: str, province: str
    ) -> ConnectorRequest:
        settings = config.RESEARCH_CONNECTOR_SETTINGS.get(connector_name, {})
        allow_personal_raw = settings.get("allow_personal_data")
        allow_personal = (
            bool(allow_personal_raw)
            if allow_personal_raw is not None
            else config.RESEARCH_ALLOW_PERSONAL_DATA
        )
        rate_limit_raw = settings.get(
            "rate_limit_seconds", config.RESEARCH_RATE_LIMIT_SECONDS
        )
        try:
            rate_limit_seconds = float(rate_limit_raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            rate_limit_seconds = float(config.RESEARCH_RATE_LIMIT_SECONDS)
        return ConnectorRequest(
            organisation=organisation,
            province=province,
            allow_personal_data=allow_personal,
            rate_limit_delay=rate_limit_seconds,
        )


__all__ = [
    "MultiSourceResearchAdapter",
    "build_default_connectors",
]
