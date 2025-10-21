"""Tests for crawl policy and RFC 9309 compliance."""

from __future__ import annotations

import time
from datetime import timedelta

import pytest

from firecrawl_demo.integrations.crawl_policy import (
    CrawlConfig,
    CrawlPolicyManager,
    create_default_policy,
)


class TestURLCanonicalization:
    """Test URL canonicalization."""
    
    def test_removes_tracking_params(self) -> None:
        manager = create_default_policy()
        
        url = "https://example.com/page?utm_source=test&id=123&utm_campaign=winter"
        canonical = manager.canonicalize_url(url)
        
        assert "utm_source" not in canonical
        assert "utm_campaign" not in canonical
        assert "id=123" in canonical
    
    def test_removes_trailing_slash(self) -> None:
        manager = create_default_policy()
        
        url = "https://example.com/page/"
        canonical = manager.canonicalize_url(url)
        
        assert canonical == "https://example.com/page"
    
    def test_preserves_root_slash(self) -> None:
        manager = create_default_policy()
        
        url = "https://example.com/"
        canonical = manager.canonicalize_url(url)
        
        assert canonical == "https://example.com/"
    
    def test_canonicalization_disabled(self) -> None:
        config = CrawlConfig(enable_canonicalization=False)
        manager = CrawlPolicyManager(config)
        
        url = "https://example.com/page?utm_source=test"
        canonical = manager.canonicalize_url(url)
        
        assert canonical == url


class TestTrapDetection:
    """Test crawler trap detection."""
    
    def test_detects_calendar_trap(self) -> None:
        manager = create_default_policy()
        
        urls = [
            "https://example.com/calendar/2024/12/25",
            "https://example.com/events?year=2024&month=12",
        ]
        
        for url in urls:
            assert manager.is_trap(url)
    
    def test_detects_faceted_navigation(self) -> None:
        manager = create_default_policy()
        
        # URL with excessive query parameters
        url = "https://example.com/search?a=1&b=2&c=3&d=4&e=5&f=6&g=7"
        assert manager.is_trap(url)
    
    def test_detects_session_ids(self) -> None:
        manager = create_default_policy()
        
        urls = [
            "https://example.com/page?sessionid=abc123",
            "https://example.com/page?PHPSESSID=xyz789",
        ]
        
        for url in urls:
            assert manager.is_trap(url)
    
    def test_normal_url_not_trap(self) -> None:
        manager = create_default_policy()
        
        url = "https://example.com/about-us"
        assert not manager.is_trap(url)
    
    def test_trap_detection_disabled(self) -> None:
        config = CrawlConfig(enable_trap_detection=False)
        manager = CrawlPolicyManager(config)
        
        url = "https://example.com/calendar/2024/12/25"
        assert not manager.is_trap(url)


class TestURLFiltering:
    """Test URL filtering by scheme and host."""
    
    def test_allows_https_scheme(self) -> None:
        manager = create_default_policy()
        
        url = "https://example.com/page"
        assert manager.is_allowed_url(url)
    
    def test_denies_ftp_scheme(self) -> None:
        manager = create_default_policy()
        
        url = "ftp://example.com/file.txt"
        assert not manager.is_allowed_url(url)
    
    def test_respects_denied_hosts(self) -> None:
        config = CrawlConfig(denied_hosts={"blocked.com"})
        manager = CrawlPolicyManager(config)
        
        url = "https://blocked.com/page"
        assert not manager.is_allowed_url(url)
    
    def test_respects_allowed_hosts(self) -> None:
        config = CrawlConfig(allowed_hosts={"allowed.com"})
        manager = CrawlPolicyManager(config)
        
        assert manager.is_allowed_url("https://allowed.com/page")
        assert not manager.is_allowed_url("https://other.com/page")


class TestRateLimiting:
    """Test rate limiting behavior."""
    
    def test_enforces_minimum_delay(self) -> None:
        config = CrawlConfig(min_delay_seconds=0.1)
        manager = CrawlPolicyManager(config)
        
        host = "example.com"
        
        # First request - no delay
        start = time.time()
        manager.wait_for_rate_limit(host)
        first_duration = time.time() - start
        assert first_duration < 0.05
        
        # Second request - should delay
        start = time.time()
        manager.wait_for_rate_limit(host)
        second_duration = time.time() - start
        assert second_duration >= 0.08  # Allow some margin
    
    def test_exponential_backoff_on_errors(self) -> None:
        config = CrawlConfig(min_delay_seconds=1.0, backoff_factor=2.0)
        manager = CrawlPolicyManager(config)
        
        host = "example.com"
        state = manager.host_states[host]
        
        assert state.current_delay == 1.0
        
        manager.record_error(host)
        assert state.current_delay == 2.0
        
        manager.record_error(host)
        assert state.current_delay == 4.0
    
    def test_resets_delay_on_success(self) -> None:
        config = CrawlConfig(min_delay_seconds=1.0, backoff_factor=2.0)
        manager = CrawlPolicyManager(config)
        
        host = "example.com"
        
        manager.record_error(host)
        manager.record_error(host)
        assert manager.host_states[host].current_delay == 4.0
        
        manager.record_success(host)
        assert manager.host_states[host].current_delay == 1.0
    
    def test_caps_max_delay(self) -> None:
        config = CrawlConfig(
            min_delay_seconds=1.0,
            max_delay_seconds=10.0,
            backoff_factor=5.0
        )
        manager = CrawlPolicyManager(config)
        
        host = "example.com"
        
        for _ in range(5):
            manager.record_error(host)
        
        assert manager.host_states[host].current_delay <= 10.0


class TestDuplicateDetection:
    """Test duplicate URL detection."""
    
    def test_marks_duplicate_urls(self) -> None:
        manager = create_default_policy()
        
        url = "https://example.com/page"
        
        assert not manager.mark_seen(url)  # First time
        assert manager.mark_seen(url)  # Duplicate
    
    def test_canonicalizes_before_checking(self) -> None:
        manager = create_default_policy()
        
        url1 = "https://example.com/page?utm_source=test"
        url2 = "https://example.com/page"
        
        assert not manager.mark_seen(url1)
        assert manager.mark_seen(url2)  # Should be duplicate after canonicalization


class TestCanFetch:
    """Test integrated can_fetch checks."""
    
    def test_allows_valid_url(self) -> None:
        manager = create_default_policy()
        
        url = "https://example.com/about"
        assert manager.can_fetch(url)
    
    def test_rejects_trap_url(self) -> None:
        manager = create_default_policy()
        
        url = "https://example.com/calendar/2024/12/25"
        assert not manager.can_fetch(url)
    
    def test_rejects_disallowed_scheme(self) -> None:
        manager = create_default_policy()
        
        url = "ftp://example.com/file.txt"
        assert not manager.can_fetch(url)
    
    def test_respects_robots_txt_disabled(self) -> None:
        config = CrawlConfig(respect_robots_txt=False)
        manager = CrawlPolicyManager(config)
        
        # Should allow any URL if robots.txt is disabled
        url = "https://example.com/admin"
        assert manager.can_fetch(url)


class TestConfiguration:
    """Test configuration options."""
    
    def test_default_config(self) -> None:
        config = CrawlConfig()
        
        assert config.respect_robots_txt is True
        assert config.min_delay_seconds == 1.0
        assert config.enable_trap_detection is True
        assert "https" in config.allowed_schemes
    
    def test_custom_config(self) -> None:
        config = CrawlConfig(
            user_agent="CustomBot/1.0",
            min_delay_seconds=2.0,
            max_delay_seconds=60.0,
        )
        
        assert config.user_agent == "CustomBot/1.0"
        assert config.min_delay_seconds == 2.0
        assert config.max_delay_seconds == 60.0
