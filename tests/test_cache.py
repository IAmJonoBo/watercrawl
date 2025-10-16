from firecrawl_demo import cache


def test_cache_set_and_get():
    c = cache.Cache()
    c.set("key", "value")
    assert c.get("key") == "value"


def test_cache_missing_key():
    c = cache.Cache()
    assert c.get("missing") is None


def test_cache_delete():
    c = cache.Cache()
    c.set("key", "value")
    c.delete("key")
    assert c.get("key") is None
