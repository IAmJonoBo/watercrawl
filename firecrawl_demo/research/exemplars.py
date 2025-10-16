"""Exemplar research adapters for regulator, press, and ML integrations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .. import config
from ..compliance import normalize_phone
from .core import ResearchAdapter, ResearchFinding
from .registry import AdapterContext, register_adapter


def _normalise_name(value: str) -> str:
    return value.strip().lower()


@dataclass(frozen=True)
class RegulatorRecord:
    organisation: str
    website_url: str
    contact_person: str
    contact_email: str
    contact_phone: str
    source_url: str
    alternate_names: tuple[str, ...] = ()
    physical_address: str | None = None

    def to_finding(self) -> ResearchFinding:
        phone, _ = normalize_phone(self.contact_phone)
        return ResearchFinding(
            website_url=self.website_url,
            contact_person=self.contact_person,
            contact_email=self.contact_email,
            contact_phone=phone or self.contact_phone,
            sources=[self.source_url],
            notes=f"Regulator registry corroboration for {self.organisation}",
            confidence=85,
            alternate_names=list(self.alternate_names),
            physical_address=self.physical_address,
        )


@dataclass(frozen=True)
class PressClipping:
    organisation: str
    url: str
    headline: str
    summary: str

    def to_finding(self) -> ResearchFinding:
        return ResearchFinding(
            sources=[self.url],
            notes="Press monitoring coverage located",
            confidence=60,
            investigation_notes=[
                f"Press coverage: {self.headline} — {self.summary}",
            ],
        )


@dataclass(frozen=True)
class MLInference:
    organisation: str
    contact_person: str
    contact_email: str
    contact_phone: str | None
    website_url: str | None
    model_version: str
    provenance_url: str

    def to_finding(self) -> ResearchFinding:
        phone = None
        if self.contact_phone:
            phone, _ = normalize_phone(self.contact_phone)
        return ResearchFinding(
            website_url=self.website_url,
            contact_person=self.contact_person,
            contact_email=self.contact_email,
            contact_phone=phone or self.contact_phone,
            sources=[self.provenance_url],
            notes="ML inference contact recommendation",
            confidence=70,
            investigation_notes=[
                ("ML model {model} recommended {person} as primary contact.").format(
                    model=self.model_version, person=self.contact_person
                )
            ],
        )


_EXEMPLAR_REGULATOR_DATA: Mapping[str, RegulatorRecord] = {
    _normalise_name("Legacy Flight School"): RegulatorRecord(
        organisation="Legacy Flight School",
        website_url="https://legacy-flight.example.za",
        contact_person="Nomsa Jacobs",
        contact_email="nomsa.jacobs@legacy-flight.example.za",
        contact_phone="0215550123",
        source_url="https://regulator.ac.za/operators/legacy-flight-school",
        alternate_names=("Legacy Flight Training",),
        physical_address="Cape Town International Airport",
    )
}


_EXEMPLAR_PRESS_DATA: Mapping[str, PressClipping] = {
    _normalise_name("Legacy Flight School"): PressClipping(
        organisation="Legacy Flight School",
        url="https://press.example.com/legacy-flight-rebrands",
        headline="Legacy Flight School rebrands for 2024 growth",
        summary="South African Civil Aviation Authority confirms refreshed brand.",
    )
}


_EXEMPLAR_ML_DATA: Mapping[str, MLInference] = {
    _normalise_name("Legacy Flight School"): MLInference(
        organisation="Legacy Flight School",
        contact_person="Nomsa Jacobs",
        contact_email="nomsa.jacobs@legacy-flight.example.za",
        contact_phone="0215550123",
        website_url="https://legacy-flight.example.za",
        model_version="contact-v1.2.0",
        provenance_url="https://ml.acesaero.internal/models/contact-v1.2.0",
    )
}


class RegulatorRegistryAdapter(ResearchAdapter):
    """Serve regulator intelligence from a curated exemplar dataset."""

    def __init__(self, dataset: Mapping[str, RegulatorRecord] | None = None) -> None:
        self._dataset = dataset or _EXEMPLAR_REGULATOR_DATA

    def lookup(self, organisation: str, province: str) -> ResearchFinding:
        if not config.FEATURE_FLAGS.enable_regulator_lookup:
            return ResearchFinding(
                notes="Regulator lookup disabled by feature flag.",
            )

        record = self._dataset.get(_normalise_name(organisation))
        if record:
            return record.to_finding()
        return ResearchFinding(
            notes=f"No regulator registry record found for {organisation}",
        )


class PressMonitoringAdapter(ResearchAdapter):
    """Return press coverage snippets from the exemplar dataset."""

    def __init__(self, dataset: Mapping[str, PressClipping] | None = None) -> None:
        self._dataset = dataset or _EXEMPLAR_PRESS_DATA

    def lookup(self, organisation: str, province: str) -> ResearchFinding:
        if not config.FEATURE_FLAGS.enable_press_research:
            return ResearchFinding(
                notes="Press monitoring disabled by feature flag.",
            )

        clipping = self._dataset.get(_normalise_name(organisation))
        if clipping:
            return clipping.to_finding()
        return ResearchFinding(
            notes=f"No press coverage located for {organisation}",
        )


class MLInferenceAdapter(ResearchAdapter):
    """Expose ML-backed contact inference suitable for offline demos."""

    def __init__(self, dataset: Mapping[str, MLInference] | None = None) -> None:
        self._dataset = dataset or _EXEMPLAR_ML_DATA

    def lookup(self, organisation: str, province: str) -> ResearchFinding:
        if not config.FEATURE_FLAGS.enable_ml_inference:
            return ResearchFinding(notes="ML inference disabled by feature flag.")

        inference = self._dataset.get(_normalise_name(organisation))
        if inference:
            return inference.to_finding()
        return ResearchFinding(
            notes=f"ML inference dataset has no recommendation for {organisation}",
        )


def _regulator_factory(context: AdapterContext) -> ResearchAdapter | None:
    if not context.config.FEATURE_FLAGS.enable_regulator_lookup:
        return None
    return RegulatorRegistryAdapter()


def _press_factory(context: AdapterContext) -> ResearchAdapter | None:
    if not context.config.FEATURE_FLAGS.enable_press_research:
        return None
    return PressMonitoringAdapter()


def _ml_factory(context: AdapterContext) -> ResearchAdapter | None:
    if not context.config.FEATURE_FLAGS.enable_ml_inference:
        return None
    return MLInferenceAdapter()


register_adapter("regulator", _regulator_factory)
register_adapter("press", _press_factory)
register_adapter("ml", _ml_factory)


__all__ = [
    "RegulatorRegistryAdapter",
    "PressMonitoringAdapter",
    "MLInferenceAdapter",
]
