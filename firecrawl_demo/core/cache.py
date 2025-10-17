# Minimal in-memory Cache for testing
from __future__ import annotations


class Cache:
    """Minimal in-memory cache for testing."""

    def __init__(self):
        self._store = {}

    def set(self, key, value):
        self._store[key] = value

    def get(self, key):
        return self._store.get(key)

    def delete(self, key):
        if key in self._store:
            del self._store[key]


# Global in-memory cache instance
_cache = Cache()


def load(key, max_age_hours=None):
    """Load value from cache by key. Ignores max_age_hours for in-memory cache."""
    return _cache.get(key)


def store(key, value):
    """Store value in cache by key."""
    _cache.set(key, value)
