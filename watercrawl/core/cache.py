# Minimal in-memory Cache for testing
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any, Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


def _now() -> datetime:
    """Return the current UTC timestamp (extracted for monkeypatching in tests)."""

    return datetime.now(timezone.utc)


@dataclass(slots=True)
class CacheEntry(Generic[V]):
    """Container storing cached values together with insertion metadata."""

    value: V
    stored_at: datetime


class Cache(Generic[K, V]):
    """Thread-safe in-memory cache with optional expiry support."""

    def __init__(self) -> None:
        self._store: dict[K, CacheEntry[V]] = {}
        self._lock = RLock()

    def set(self, key: K, value: V) -> None:
        """Store ``value`` under ``key`` and record the insertion timestamp."""

        with self._lock:
            self._store[key] = CacheEntry(value=value, stored_at=_now())

    def get(self, key: K, *, max_age: timedelta | None = None) -> V | None:
        """Return the cached value for ``key`` if present and not expired."""

        if max_age is not None and max_age.total_seconds() < 0:
            raise ValueError("max_age must be non-negative")

        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None

            if max_age is not None:
                if entry.stored_at <= _now() - max_age:
                    # Expired entries are purged eagerly so callers do not need to
                    # issue a separate delete.
                    del self._store[key]
                    return None

            return entry.value

    def delete(self, key: K) -> None:
        """Remove ``key`` from the cache if present."""

        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        """Clear all cached entries (primarily used in tests)."""

        with self._lock:
            self._store.clear()


# Global in-memory cache instance
_cache: Cache[Any, Any] = Cache()


def load(key: K, max_age_hours: float | None = None) -> Any:
    """Load a cached value, respecting ``max_age_hours`` when provided."""

    max_age: timedelta | None
    if max_age_hours is None:
        max_age = None
    else:
        try:
            hours = float(max_age_hours)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive guard
            raise TypeError("max_age_hours must be a numeric value") from exc
        if hours < 0:
            raise ValueError("max_age_hours must be non-negative")
        max_age = timedelta(hours=hours)

    return _cache.get(key, max_age=max_age)


def store(key: K, value: Any) -> None:
    """Store ``value`` in the global cache under ``key``."""

    _cache.set(key, value)
