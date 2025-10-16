import pytest
import time
from firecrawl_demo.firecrawl_client import FirecrawlClient

class DummySettings:
    class throttle:
        min_interval = 0.01
    class retry:
        initial_delay = 0.01
        max_delay = 0.1
        backoff_factor = 2.0
        max_attempts = 3
    behaviour = type('behaviour', (), {'search_limit': 1, 'scrape_formats': [], 'map_limit': 1})
    api_url = None

def test_circuit_breaker_triggers_and_resets(monkeypatch):
    client = FirecrawlClient(api_key="dummy", settings=DummySettings())
    # Patch RateLimitError to a dummy error for testing
    import firecrawl_demo.firecrawl_client as fc_mod
    class DummyRateLimitError(Exception):
        pass
    monkeypatch.setattr(fc_mod, "RateLimitError", DummyRateLimitError)
    def always_fail():
        raise DummyRateLimitError()
    client._failure_count = client._max_failures - 1
    # Should trigger circuit breaker
    with pytest.raises(RuntimeError):
        client._execute_with_retry(always_fail)
    # Simulate circuit breaker reset
    client._circuit_open_until = time.monotonic() - 1
    client._failure_count = 0
    # Should not raise now
    try:
        client._execute_with_retry(lambda: 'ok')
    except Exception:
        pytest.fail("Should not raise after circuit breaker reset")

def test_deferred_queue_enqueue_and_process():
    client = FirecrawlClient(api_key="dummy", settings=DummySettings())
    called = {}
    def dummy_method():
        called['ok'] = True
    client._enqueue_deferred('dummy_method', [], {})
    setattr(client, 'dummy_method', dummy_method)
    client.process_deferred_queue()
    assert called.get('ok')

def test_rate_limit_backoff(monkeypatch):
    client = FirecrawlClient(api_key="dummy", settings=DummySettings())
    # Patch RateLimitError to a dummy error for testing
    import firecrawl_demo.firecrawl_client as fc_mod
    class DummyRateLimitError(Exception):
        pass
    monkeypatch.setattr(fc_mod, "RateLimitError", DummyRateLimitError)
    attempts = []
    def fail_then_succeed():
        if len(attempts) < 2:
            attempts.append('fail')
            raise DummyRateLimitError()
        return 'success'
    monkeypatch.setattr(client, "_throttle", lambda: None)
    result = client._execute_with_retry(fail_then_succeed)
    assert result == 'success'
