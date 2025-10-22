"""Shared dataclasses and serialization helpers for Crawlkit."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Literal, Mapping

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _ensure_utc(value).strftime(ISO_FORMAT)


def _deserialize_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    # Accept both microsecond and second precision timestamps.
    try:
        return datetime.strptime(value, ISO_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.fromisoformat(value).astimezone(timezone.utc)


@dataclass(slots=True)
class FetchPolicy:
    """Policy toggles controlling how pages are retrieved."""

    obey_robots: bool = True
    max_depth: int = 2
    max_pages: int = 200
    concurrent_per_domain: int = 2
    render_js: Literal["auto", "never", "always"] = "auto"
    region: Literal["ZA", "EU", "UK", "US"] = "ZA"
    user_agent: str = "Watercrawl-Crawlkit/1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "obey_robots": self.obey_robots,
            "max_depth": self.max_depth,
            "max_pages": self.max_pages,
            "concurrent_per_domain": self.concurrent_per_domain,
            "render_js": self.render_js,
            "region": self.region,
            "user_agent": self.user_agent,
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "FetchPolicy":
        if not data:
            return cls()
        init_values: dict[str, Any] = {}
        for field_info in fields(cls):
            if not field_info.init:
                continue
            if field_info.name in data:
                init_values[field_info.name] = data[field_info.name]
        return cls(**init_values)


@dataclass(slots=True)
class RobotsDecision:
    """Result of evaluating a robots.txt policy."""

    allowed: bool
    user_agent: str
    rule: str | None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "user_agent": self.user_agent,
            "rule": self.rule,
            "fetched_at": _serialize_datetime(self.fetched_at),
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "RobotsDecision | None":
        if not data:
            return None
        return cls(
            allowed=bool(data.get("allowed", True)),
            user_agent=str(data.get("user_agent", "Watercrawl-Crawlkit/1.0")),
            rule=data.get("rule"),
            fetched_at=_deserialize_datetime(data.get("fetched_at")) or datetime.now(timezone.utc),
        )


@dataclass(slots=True)
class FetchedPage:
    """HTML payload returned from the fetch subsystem."""

    url: str
    html: str
    status: int
    robots_allowed: bool
    fetched_at: datetime
    via: Literal["http", "rendered"]
    metadata: dict[str, Any] = field(default_factory=dict)
    robots: RobotsDecision | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "html": self.html,
            "status": self.status,
            "robots_allowed": self.robots_allowed,
            "fetched_at": _serialize_datetime(self.fetched_at),
            "via": self.via,
            "metadata": self.metadata,
            "robots": self.robots.to_dict() if self.robots else None,
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "FetchedPage":
        return cls(
            url=str(data["url"]),
            html=str(data.get("html", "")),
            status=int(data.get("status", 0)),
            robots_allowed=bool(data.get("robots_allowed", True)),
            fetched_at=_deserialize_datetime(data.get("fetched_at")) or datetime.now(timezone.utc),
            via=data.get("via", "http"),
            metadata=dict(data.get("metadata", {})),
            robots=RobotsDecision.from_mapping(data.get("robots")),
        )


@dataclass(slots=True)
class DistilledDoc:
    """Markdown-focused representation of a page."""

    url: str
    markdown: str
    text: str
    meta: dict[str, Any]
    microdata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "DistilledDoc":
        return cls(
            url=str(data["url"]),
            markdown=str(data.get("markdown", "")),
            text=str(data.get("text", "")),
            meta=dict(data.get("meta", {})),
            microdata=dict(data.get("microdata", {})),
        )


@dataclass(slots=True)
class Entities:
    """Entities extracted from a distilled document."""

    people: list[dict[str, Any]] = field(default_factory=list)
    emails: list[dict[str, Any]] = field(default_factory=list)
    phones: list[dict[str, Any]] = field(default_factory=list)
    org: dict[str, Any] = field(default_factory=dict)
    aviation: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "Entities":
        if data is None:
            return cls()
        return cls(
            people=list(data.get("people", [])),
            emails=list(data.get("emails", [])),
            phones=list(data.get("phones", [])),
            org=dict(data.get("org", {})),
            aviation=data.get("aviation"),
        )


@dataclass(slots=True)
class ComplianceDecision:
    """Compliance decision emitted by the guard."""

    allowed: bool
    reason: str
    region: str
    logged_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "region": self.region,
            "logged_at": _serialize_datetime(self.logged_at),
            "evidence": list(self.evidence),
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ComplianceDecision":
        return cls(
            allowed=bool(data.get("allowed", True)),
            reason=str(data.get("reason", "")),
            region=str(data.get("region", "ZA")),
            logged_at=_deserialize_datetime(data.get("logged_at")) or datetime.now(timezone.utc),
            evidence=list(data.get("evidence", [])),
        )


def serialize_for_celery(value: Any) -> Any:
    """Recursively serialize dataclasses to plain Python types for Celery payloads."""

    if hasattr(value, "to_dict") and callable(getattr(value, "to_dict")):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {key: serialize_for_celery(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize_for_celery(item) for item in value]
    return value


Deserializer = Callable[[Mapping[str, Any]], Any]


def hydrate_list(values: Iterable[Mapping[str, Any]], factory: Deserializer) -> list[Any]:
    """Hydrate a collection of mappings via a factory."""

    return [factory(value) for value in values]
