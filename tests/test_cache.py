from datetime import datetime, timedelta, timezone

import pytest

from firecrawl_demo.core import cache


def test_cache_set_and_get(monkeypatch):
    frozen = datetime(2025, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(cache, "_now", lambda: frozen)

    c: cache.Cache[str, str] = cache.Cache()
    c.set("key", "value")
    assert c.get("key") == "value"


def test_cache_missing_key():
    c: cache.Cache[str, str] = cache.Cache()
    assert c.get("missing") is None


def test_cache_delete(monkeypatch):
    frozen = datetime(2025, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(cache, "_now", lambda: frozen)

    c: cache.Cache[str, str] = cache.Cache()
    c.set("key", "value")
    c.delete("key")
    assert c.get("key") is None


def test_cache_get_respects_max_age(monkeypatch):
    base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    c: cache.Cache[str, str] = cache.Cache()

    monkeypatch.setattr(cache, "_now", lambda: base_time)
    c.set("key", "value")

    monkeypatch.setattr(cache, "_now", lambda: base_time + timedelta(minutes=30))
    assert c.get("key", max_age=timedelta(hours=1)) == "value"

    monkeypatch.setattr(cache, "_now", lambda: base_time + timedelta(hours=2))
    assert c.get("key", max_age=timedelta(hours=1)) is None


def test_cache_get_rejects_negative_max_age():
    c: cache.Cache[str, str] = cache.Cache()

    with pytest.raises(ValueError):
        c.get("key", max_age=timedelta(hours=-1))


def test_load_respects_max_age_hours(monkeypatch):
    base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(cache, "_cache", cache.Cache())
    monkeypatch.setattr(cache, "_now", lambda: base_time)

    cache.store("key", "value")
    assert cache.load("key", max_age_hours=1) == "value"

    monkeypatch.setattr(cache, "_now", lambda: base_time + timedelta(hours=2))
    assert cache.load("key", max_age_hours=1) is None


def test_load_rejects_invalid_max_age():
    with pytest.raises(ValueError):
        cache.load("key", max_age_hours=-1)

    with pytest.raises(TypeError):
        cache.load("key", max_age_hours="invalid")
