"""
Crawl politeness and robots.txt compliance per RFC 9309.

This module implements polite web crawling behavior including:
- Robots.txt parsing and respect (RFC 9309)
- Per-host rate limiting with adaptive backoff
- Trap detection (calendar pages, faceted navigation)
- URL canonicalization
- Host-based request queuing

WC-03 acceptance criteria:
- Zero robots.txt violations on test corpus
- Trap false positive rate < 2%
- Performance impact ±10%
"""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser

logger = logging.getLogger(__name__)


@dataclass
class CrawlConfig:
    """Configuration for polite crawling behavior."""
    
    # RFC 9309 compliance
    user_agent: str = "ACES-Watercrawl/1.0 (+https://github.com/IAmJonoBo/watercrawl)"
    respect_robots_txt: bool = True
    robots_cache_ttl: timedelta = timedelta(hours=24)
    
    # Rate limiting
    min_delay_seconds: float = 1.0  # Minimum delay between requests to same host
    max_delay_seconds: float = 30.0  # Maximum backoff delay
    backoff_factor: float = 2.0  # Exponential backoff multiplier
    
    # Trap detection
    enable_trap_detection: bool = True
    max_depth: int = 10
    max_params: int = 5  # Maximum query parameters before considering faceted nav
    
    # URL filtering
    enable_canonicalization: bool = True
    allowed_schemes: Set[str] = field(default_factory=lambda: {"http", "https"})
    denied_hosts: Set[str] = field(default_factory=set)
    allowed_hosts: Set[str] = field(default_factory=set)


@dataclass
class HostState:
    """State tracking for a single host."""
    
    last_request_time: Optional[datetime] = None
    consecutive_errors: int = 0
    current_delay: float = 1.0
    robots_parser: Optional[RobotFileParser] = None
    robots_fetched_at: Optional[datetime] = None


class CrawlPolicyManager:
    """
    Manages crawl politeness and RFC 9309 compliance.
    
    Example:
        >>> config = CrawlConfig(min_delay_seconds=2.0)
        >>> manager = CrawlPolicyManager(config)
        >>> if manager.can_fetch("https://example.com/page"):
        ...     manager.wait_for_rate_limit("example.com")
        ...     # Perform crawl
        ...     manager.record_success("example.com")
    """
    
    def __init__(self, config: Optional[CrawlConfig] = None):
        self.config = config or CrawlConfig()
        self.host_states: Dict[str, HostState] = defaultdict(HostState)
        self._seen_urls: Set[str] = set()
        self._trap_patterns = self._compile_trap_patterns()
        
    def _compile_trap_patterns(self) -> List[re.Pattern]:
        """Compile regex patterns for common crawler traps."""
        patterns = [
            # Calendar pages with infinite date combinations
            re.compile(r'/calendar/\d{4}/\d{1,2}/\d{1,2}'),
            re.compile(r'[?&]year=\d{4}'),
            re.compile(r'[?&]month=\d{1,2}'),
            
            # Faceted navigation with combinatorial explosion
            re.compile(r'[?&]sort='),
            re.compile(r'[?&]filter='),
            re.compile(r'[?&]page=\d+'),
            
            # Session IDs and tracking parameters
            re.compile(r'[?&]session_?id='),
            re.compile(r'[?&]sid='),
            re.compile(r'[?&]PHPSESSID='),
            re.compile(r'[?&]utm_'),
        ]
        return patterns
    
    def canonicalize_url(self, url: str) -> str:
        """
        Canonicalize URL by removing tracking parameters and normalizing.
        
        Args:
            url: The URL to canonicalize
            
        Returns:
            Canonicalized URL
        """
        if not self.config.enable_canonicalization:
            return url
            
        parsed = urlparse(url)
        
        # Remove common tracking parameters
        if parsed.query:
            params = []
            for param in parsed.query.split('&'):
                if not any(tracker in param for tracker in ['utm_', 'fbclid', 'gclid']):
                    params.append(param)
            query = '&'.join(params) if params else ''
        else:
            query = ''
        
        # Reconstruct canonical URL
        canonical = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if query:
            canonical += f"?{query}"
            
        # Remove trailing slash unless it's the root
        if canonical.endswith('/') and parsed.path != '/':
            canonical = canonical.rstrip('/')
            
        return canonical
    
    def is_trap(self, url: str) -> bool:
        """
        Detect if URL is likely a crawler trap.
        
        Args:
            url: URL to check
            
        Returns:
            True if URL appears to be a trap
        """
        if not self.config.enable_trap_detection:
            return False
            
        # Check against trap patterns
        for pattern in self._trap_patterns:
            if pattern.search(url):
                return True
        
        # Check excessive query parameters (faceted navigation)
        parsed = urlparse(url)
        if parsed.query:
            param_count = len(parsed.query.split('&'))
            if param_count > self.config.max_params:
                return True
        
        return False
    
    def is_allowed_url(self, url: str) -> bool:
        """
        Check if URL is allowed by policy (scheme, host filters).
        
        Args:
            url: URL to check
            
        Returns:
            True if URL is allowed
        """
        parsed = urlparse(url)
        
        # Check scheme
        if parsed.scheme not in self.config.allowed_schemes:
            return False
        
        # Check denied hosts
        if self.config.denied_hosts and parsed.netloc in self.config.denied_hosts:
            return False
        
        # Check allowed hosts (if whitelist is defined)
        if self.config.allowed_hosts and parsed.netloc not in self.config.allowed_hosts:
            return False
        
        return True
    
    def _get_robots_parser(self, host: str) -> Optional[RobotFileParser]:
        """
        Get cached or fetch robots.txt parser for host.
        
        Args:
            host: Hostname to get robots.txt for
            
        Returns:
            RobotFileParser instance or None if fetch fails
        """
        state = self.host_states[host]
        
        # Check cache validity
        if state.robots_parser and state.robots_fetched_at:
            age = datetime.now() - state.robots_fetched_at
            if age < self.config.robots_cache_ttl:
                return state.robots_parser
        
        # Fetch robots.txt
        try:
            parser = RobotFileParser()
            parser.set_url(f"https://{host}/robots.txt")
            parser.read()
            
            state.robots_parser = parser
            state.robots_fetched_at = datetime.now()
            
            logger.info(f"Fetched robots.txt for {host}")
            return parser
            
        except Exception as e:
            logger.warning(f"Failed to fetch robots.txt for {host}: {e}")
            # Per RFC 9309, treat as no restrictions if fetch fails
            return None
    
    def can_fetch(self, url: str) -> bool:
        """
        Check if URL can be fetched per robots.txt and policy.
        
        Args:
            url: URL to check
            
        Returns:
            True if URL can be fetched
        """
        # Check basic URL policy
        if not self.is_allowed_url(url):
            return False
        
        # Check for traps
        if self.is_trap(url):
            logger.debug(f"Detected trap URL: {url}")
            return False
        
        # Check robots.txt
        if self.config.respect_robots_txt:
            parsed = urlparse(url)
            parser = self._get_robots_parser(parsed.netloc)
            
            if parser and not parser.can_fetch(self.config.user_agent, url):
                logger.info(f"URL disallowed by robots.txt: {url}")
                return False
        
        return True
    
    def wait_for_rate_limit(self, host: str) -> None:
        """
        Block until rate limit allows request to host.
        
        Args:
            host: Hostname to rate-limit
        """
        state = self.host_states[host]
        
        if state.last_request_time:
            elapsed = (datetime.now() - state.last_request_time).total_seconds()
            wait_time = state.current_delay - elapsed
            
            if wait_time > 0:
                logger.debug(f"Rate limiting {host}: waiting {wait_time:.2f}s")
                time.sleep(wait_time)
        
        state.last_request_time = datetime.now()
    
    def record_success(self, host: str) -> None:
        """
        Record successful request to host, resetting backoff.
        
        Args:
            host: Hostname that succeeded
        """
        state = self.host_states[host]
        state.consecutive_errors = 0
        state.current_delay = self.config.min_delay_seconds
    
    def record_error(self, host: str) -> None:
        """
        Record failed request to host, applying exponential backoff.
        
        Args:
            host: Hostname that failed
        """
        state = self.host_states[host]
        state.consecutive_errors += 1
        
        # Apply exponential backoff
        new_delay = min(
            state.current_delay * self.config.backoff_factor,
            self.config.max_delay_seconds
        )
        state.current_delay = new_delay
        
        logger.warning(
            f"Error for {host} (#{state.consecutive_errors}), "
            f"backing off to {new_delay:.2f}s"
        )
    
    def mark_seen(self, url: str) -> bool:
        """
        Mark URL as seen, returning True if it was already seen.
        
        Args:
            url: URL to mark
            
        Returns:
            True if URL was already seen (duplicate)
        """
        canonical = self.canonicalize_url(url)
        
        if canonical in self._seen_urls:
            return True
        
        self._seen_urls.add(canonical)
        return False


def create_default_policy() -> CrawlPolicyManager:
    """
    Create a CrawlPolicyManager with default configuration.
    
    Returns:
        Configured CrawlPolicyManager instance
    """
    return CrawlPolicyManager(CrawlConfig())
