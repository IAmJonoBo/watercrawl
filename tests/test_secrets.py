from __future__ import annotations

import json

from firecrawl_demo import config
from firecrawl_demo.secrets import ChainedSecretsProvider


class DummyProvider:
    def __init__(self, values: dict[str, str | None]) -> None:
        self.values = values
        self.calls: list[str] = []

    def get(self, name: str) -> str | None:  # pragma: no cover - exercised via tests
        self.calls.append(name)
        return self.values.get(name)


def test_chained_provider_prefers_first_non_empty_value() -> None:
    primary = DummyProvider({"SECRET": None})
    fallback = DummyProvider({"SECRET": "secondary"})
    provider = ChainedSecretsProvider((primary, fallback))

    assert provider.get("SECRET") == "secondary"
    assert primary.calls == ["SECRET"]
    assert fallback.calls == ["SECRET"]


def test_configure_uses_supplied_provider() -> None:
    provider = DummyProvider(
        {
            "FIRECRAWL_API_KEY": "test-key",
            "FIRECRAWL_API_URL": "https://api.example.com",
            "FEATURE_ENABLE_FIRECRAWL_SDK": "true",
            "FEATURE_ENABLE_PRESS_RESEARCH": "0",
            "FEATURE_ENABLE_REGULATOR_LOOKUP": "yes",
            "FEATURE_INVESTIGATE_REBRANDS": "false",
            "ALLOW_NETWORK_RESEARCH": "1",
            "FIRECRAWL_SEARCH_LIMIT": "9",
            "FIRECRAWL_MAP_LIMIT": "4",
            "FIRECRAWL_TIMEOUT_SECONDS": "12.5",
            "FIRECRAWL_PROXY_MODE": "advanced",
            "FIRECRAWL_ONLY_MAIN_CONTENT": "false",
            "FIRECRAWL_SCRAPE_FORMATS": json.dumps(["markdown"]),
            "FIRECRAWL_PARSERS": json.dumps(["html"]),
            "FIRECRAWL_RETRY_MAX_ATTEMPTS": "7",
            "FIRECRAWL_RETRY_INITIAL_DELAY": "0.5",
            "FIRECRAWL_RETRY_MAX_DELAY": "5",
            "FIRECRAWL_RETRY_BACKOFF_FACTOR": "1.5",
            "FIRECRAWL_MAX_CONCURRENCY": "6",
            "FIRECRAWL_MIN_INTERVAL_SECONDS": "0.1",
            "FIRECRAWL_CACHE_TTL_HOURS": "6",
            "FIRECRAWL_MX_LOOKUP_TIMEOUT": "1.5",
            "FIRECRAWL_BATCH_SIZE": "11",
            "FIRECRAWL_REQUEST_DELAY_SECONDS": "0.3",
        }
    )

    config.configure(provider)
    try:
        assert config.settings.FIRECRAWL_API_KEY == "test-key"
        assert config.settings.FIRECRAWL_API_URL == "https://api.example.com"
        assert config.FEATURE_FLAGS.enable_firecrawl_sdk is True
        assert config.FEATURE_FLAGS.enable_press_research is False
        assert config.FEATURE_FLAGS.enable_regulator_lookup is True
        assert config.FEATURE_FLAGS.investigate_rebrands is False
        assert config.ALLOW_NETWORK_RESEARCH is True
        assert config.FIRECRAWL.api_key == "test-key"
        assert config.FIRECRAWL.api_url == "https://api.example.com"
        assert config.FIRECRAWL.behaviour.search_limit == 9
        assert config.FIRECRAWL.behaviour.map_limit == 4
        assert config.FIRECRAWL.behaviour.timeout_seconds == 12.5
        assert config.FIRECRAWL.behaviour.proxy_mode == "advanced"
        assert config.FIRECRAWL.behaviour.only_main_content is False
        assert config.FIRECRAWL.behaviour.scrape_formats == ["markdown"]
        assert config.FIRECRAWL.behaviour.parsers == ["html"]
        assert config.RETRY.max_attempts == 7
        assert config.RETRY.initial_delay == 0.5
        assert config.RETRY.max_delay == 5.0
        assert config.RETRY.backoff_factor == 1.5
        assert config.THROTTLE.max_concurrency == 6
        assert config.THROTTLE.min_interval == 0.1
        assert config.CACHE_TTL_HOURS == 6.0
        assert config.MX_LOOKUP_TIMEOUT == 1.5
        assert config.BATCH_SIZE == 11
        assert config.REQUEST_DELAY_SECONDS == 0.3
    finally:
        config.configure()
