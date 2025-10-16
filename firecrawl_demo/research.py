from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol


@dataclass(frozen=True)
class ResearchFinding:
    website_url: Optional[str] = None
    contact_person: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    sources: List[str] = None  # type: ignore[assignment]
    notes: str = ""
    confidence: int = 0

    def __post_init__(self) -> None:  # pragma: no cover - dataclass hook
        if self.sources is None:
            object.__setattr__(self, "sources", [])


class ResearchAdapter(Protocol):
    def lookup(self, organisation: str, province: str) -> ResearchFinding: ...


class NullResearchAdapter:
    """Fallback adapter that provides empty research findings."""

    def lookup(self, organisation: str, province: str) -> ResearchFinding:
        return ResearchFinding()


class StaticResearchAdapter:
    """Adapter backed by a static mapping for deterministic tests or fixtures."""

    def __init__(self, findings: Dict[str, ResearchFinding]):
        self._findings = findings

    def lookup(self, organisation: str, province: str) -> ResearchFinding:
        return self._findings.get(organisation, ResearchFinding())
