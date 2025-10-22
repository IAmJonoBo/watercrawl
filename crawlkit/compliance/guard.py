"""Compliance guard implementing region-specific decisions and logging."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from ..types import ComplianceDecision

_ALLOWED_REGIONS = {"ZA", "EU", "UK", "US"}


def _log_path(base_dir: Path | None) -> Path:
    directory = base_dir or Path("data/logs/crawlkit")
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "compliance.log"


@dataclass(slots=True)
class ComplianceGuard:
    region: str = "ZA"
    log_directory: Path | None = None
    _log_path: Path = field(init=False)

    def __post_init__(self) -> None:
        if self.region not in _ALLOWED_REGIONS:
            raise ValueError(f"Unsupported region: {self.region}")
        self._log_path = _log_path(self.log_directory)

    def decide_collection(self, kind: Literal["business_email", "personal_email", "phone"], region: str | None = None) -> ComplianceDecision:
        active_region = region or self.region
        if active_region not in _ALLOWED_REGIONS:
            raise ValueError(f"Unsupported region: {active_region}")

        reason = ""
        allowed = True
        evidence: list[str] = []

        if active_region == "ZA":
            if kind == "personal_email":
                allowed = False
                reason = "POPIA s69 prohibits unsolicited personal email outreach."
            else:
                reason = "POPIA s69 allows B2B outreach with opt-out."
        elif active_region in {"EU", "UK"}:
            if kind == "personal_email":
                allowed = False
                reason = "PECR/GDPR requires prior consent for personal email outreach."
            else:
                reason = "Legitimate interest permitted; record opt-out."
                evidence.append("https://ico.org.uk/for-organisations/pecr/")
        else:  # US
            reason = "CAN-SPAM allows B2B contact with opt-out provisions."

        decision = ComplianceDecision(allowed=allowed, reason=reason, region=active_region, evidence=evidence)
        self._append_log({
            "timestamp": decision.logged_at.isoformat(),
            "region": active_region,
            "kind": kind,
            "allowed": allowed,
            "reason": reason,
        })
        return decision

    def log_provenance(self, source_url: str, rule: str) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_url": source_url,
            "rule": rule,
        }
        self._append_log(payload)

    def _append_log(self, payload: dict[str, object]) -> None:
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload))
            handle.write("\n")


__all__ = ["ComplianceGuard"]
