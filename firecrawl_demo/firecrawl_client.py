from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
from typing import Any, Callable, Dict, Iterable, Optional

import requests
from firecrawl import Firecrawl  # type: ignore
from firecrawl.v2.utils.error_handler import RateLimitError  # type: ignore

from . import cache, config

logger = logging.getLogger(__name__)


# Error classes
class RateLimitFirecrawlError(Exception):
    def __init__(
        self,
        message: str,
        details: Optional[dict] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.code = "rate_limit"
        self.details = details or {}
        self.__cause__ = cause


class APIFirecrawlError(Exception):
    def __init__(
        self,
        message: str,
        details: Optional[dict] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.code = "api_error"
        self.details = details or {}
        self.__cause__ = cause


class DeferredQueueFirecrawlError(Exception):
    def __init__(
        self,
        message: str,
        details: Optional[dict] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.code = "deferred_queue"
        self.details = details or {}
        self.__cause__ = cause


class FirecrawlError(Exception):
    def __init__(
        self, message: str, code: str = "unknown", details: Optional[dict] = None
    ):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_time: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.failures = 0
        self.last_failure_time = 0
        self.open = False

    def record_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.failure_threshold:
            self.open = True

    def reset(self):
        self.failures = 0
        self.open = False

    def can_attempt(self) -> bool:
        if not self.open:
            return True
        if time.time() - self.last_failure_time > self.recovery_time:
            self.reset()
            return True
        return False


class TelemetryDestination:
    def send(self, event: str, details: dict) -> None:
        raise NotImplementedError()


class TelemetryFile(TelemetryDestination):
    def __init__(self, path: str):
        self.path = path

    def send(self, event: str, details: dict) -> None:
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(
                    f"{time.strftime('%Y-%m-%d %H:%M:%S')} {event}: {json.dumps(details)}\n"
                )
        except (OSError, IOError) as exc:
            logger.error("Telemetry file write failed: %s", exc)


class TelemetryHTTP(TelemetryDestination):
    def __init__(self, url: str):
        self.url = url

    def send(self, event: str, details: dict) -> None:
        try:
            requests.post(
                self.url, json={"event": event, "details": details}, timeout=5
            )
        except requests.RequestException as exc:
            logger.error("Telemetry HTTP send failed: %s", exc)


class TelemetryLogger(TelemetryDestination):
    def send(self, event: str, details: dict) -> None:
        logger.info("[Telemetry] %s: %s", event, details)


class FirecrawlClient:
    async def search_async(self, query: str, *, limit: Optional[int] = None) -> Any:
        """
        Async: Search for the given query using Firecrawl, with optional result limit.
        """
        limit = limit or self._settings.behaviour.search_limit
        cache_key = f"search::{query}::{limit}"
        return await self._call_with_cache_async(
            cache_key, lambda: self._client.search(query=query, limit=limit)
        )

    async def scrape_async(self, url: str, *, formats: Optional[list] = None) -> Any:
        """
        Async: Scrape the specified URL using Firecrawl, with optional formats.
        """
        formats = formats or self._settings.behaviour.scrape_formats
        cache_key = f"scrape::{url}::{formats}"
        return await self._call_with_cache_async(
            cache_key, lambda: self._client.scrape(url=url, formats=formats)
        )

    async def crawl_async(self, url: str, **kwargs: Any) -> Any:
        """
        Async: Crawl the specified URL using Firecrawl, with optional keyword arguments.
        """
        key_bits = [url] + [f"{k}={v}" for k, v in sorted(kwargs.items())]
        cache_key = "crawl::" + "::".join(key_bits)
        return await self._call_with_cache_async(
            cache_key, lambda: self._client.crawl(url=url, **kwargs)
        )

    async def extract_async(self, urls: Iterable[str], prompt: str) -> Any:
        """
        Async: Extract information from the given URLs using the specified prompt.
        """
        urls_tuple = tuple(urls)
        cache_key = f"extract::{urls_tuple}::{prompt}"
        return await self._call_with_cache_async(
            cache_key,
            lambda: self._client.extract(urls=list(urls_tuple), prompt=prompt),
        )

    async def process_deferred_queue_async(self) -> None:
        """Async version: Process deferred requests after circuit breaker closes."""
        if not self._deferred_queue:
            return
        self._log_telemetry(
            "deferred_queue_processing_started", {"count": len(self._deferred_queue)}
        )
        queue_copy = self._deferred_queue[:]
        self._deferred_queue.clear()
        self._save_deferred_queue()
        for item in queue_copy:
            method = getattr(self, item["method"], None)
            if not callable(method):
                logger.error("Deferred method %s not found", item["method"])
                self._log_telemetry("deferred_method_not_found", item)
                continue
            try:
                if hasattr(method, "__call__") and asyncio.iscoroutinefunction(method):
                    await method(*item["args"], **item["kwargs"])
                else:
                    method(*item["args"], **item["kwargs"])
            except (RuntimeError, TypeError, ValueError) as exc:
                logger.error("Deferred Firecrawl request failed: %s", exc)
                await self._enqueue_deferred_async(
                    item["method"], item["args"], item["kwargs"]
                )

    async def _throttle_async(self) -> None:
        """Async version: Sleep if a previous rate limit indicates a future reset window."""
        lock = self._state["lock"]
        if type(lock) is threading.Lock:
            remaining = (
                self._safe_float(self._state["rate_limit_reset"]) - time.monotonic()
            )
            if remaining > 0:
                await asyncio.sleep(remaining)

    async def _enqueue_deferred_async(
        self, method: str, args: Any, kwargs: Any
    ) -> None:
        """Async version: Enqueue a deferred request."""
        deferred_item = {
            "method": method,
            "args": args,
            "kwargs": kwargs,
            "timestamp": time.time(),
        }
        self._deferred_queue.append(deferred_item)
        self._save_deferred_queue()
        self._log_telemetry("deferred_request_enqueued", deferred_item)

    async def _execute_with_retry_async(self, func: Callable[[], Any]) -> Any:
        import random

        attempts = 0
        delay = self._retry_policy.initial_delay
        max_attempts = self._retry_policy.max_attempts
        max_delay = self._retry_policy.max_delay
        backoff_factor = self._retry_policy.backoff_factor
        now = time.monotonic()
        if self._circuit_open_until > now:
            logger.error(
                "Circuit breaker open: blocking Firecrawl calls for %ds",
                int(self._circuit_open_until - now),
            )
            self._log_telemetry(
                "circuit_breaker_open",
                {"open_until": self._circuit_open_until, "now": now},
            )
            if now >= self._circuit_open_until:
                self._log_telemetry("circuit_breaker_closed", {"now": now})
                await self.process_deferred_queue_async()
            raise DeferredQueueFirecrawlError(
                "Firecrawl API temporarily blocked due to repeated failures.",
                details={"open_until": self._circuit_open_until, "now": now},
            ) from None
        while True:
            try:
                await self._throttle_async()
                result = await func()
                self._state["rate_limit_reset"] = 0.0
                self._failure_count = 0
                return result
            except RateLimitError as rate_exc:
                attempts += 1
                self._failure_count += 1
                base_wait = _retry_after_seconds(rate_exc, min(max_delay, 60.0))
                jitter = random.uniform(0, base_wait * 0.2)
                wait_time = base_wait + jitter
                logger.warning(
                    "Firecrawl rate limit encountered, sleeping %.2fs (attempt %d)",
                    wait_time,
                    attempts,
                )
                self._log_telemetry(
                    "rate_limit_retry",
                    {
                        "attempt": attempts,
                        "wait_time": wait_time,
                        "error": str(rate_exc),
                    },
                )
                if self._failure_count >= self._max_failures:
                    self._circuit_open_until = (
                        time.monotonic() + self._circuit_breaker_timeout
                    )
                    logger.critical(
                        "Circuit breaker triggered: %d consecutive rate-limit errors. Blocking for %ds.",
                        self._failure_count,
                        int(self._circuit_breaker_timeout),
                    )
                    self._log_telemetry(
                        "circuit_breaker_triggered",
                        {
                            "failures": self._failure_count,
                            "timeout": self._circuit_breaker_timeout,
                        },
                    )
                    await self._enqueue_deferred_async(func.__name__, [], {})
                    raise RateLimitFirecrawlError(
                        "Circuit breaker: too many rate-limit errors.",
                        details={
                            "failures": self._failure_count,
                            "timeout": self._circuit_breaker_timeout,
                        },
                    ) from rate_exc
                await asyncio.sleep(wait_time)
            except (ConnectionError, TimeoutError) as exc:
                attempts += 1
                self._failure_count += 1
                logger.error("Firecrawl API failure: %s (attempt %d)", exc, attempts)
                self._log_telemetry(
                    "connection_error_retry",
                    {"attempt": attempts, "wait_time": delay, "error": str(exc)},
                )
                if self._failure_count >= self._max_failures:
                    self._circuit_open_until = (
                        time.monotonic() + self._circuit_breaker_timeout
                    )
                    logger.critical(
                        "Circuit breaker triggered: %d consecutive API failures. Blocking for %ds.",
                        self._failure_count,
                        int(self._circuit_breaker_timeout),
                    )
                    self._log_telemetry(
                        "circuit_breaker_triggered",
                        {
                            "failures": self._failure_count,
                            "timeout": self._circuit_breaker_timeout,
                        },
                    )
                    await self._enqueue_deferred_async(func.__name__, [], {})
                    raise APIFirecrawlError(
                        "Circuit breaker: too many API failures.",
                        details={
                            "failures": self._failure_count,
                            "timeout": self._circuit_breaker_timeout,
                        },
                    ) from exc
                if attempts >= max_attempts:
                    raise APIFirecrawlError(
                        f"API error after {attempts} attempts.",
                        details={"error": str(exc), "attempts": attempts},
                    ) from exc
                logger.warning(
                    "Connection error encountered, sleeping %.2fs before retry (attempt %d)",
                    delay,
                    attempts,
                )
                await asyncio.sleep(delay)
                delay = min(delay * backoff_factor, max_delay)

    async def _call_with_cache_async(
        self, cache_key: str, func: Callable[[], Any]
    ) -> Any:
        cached = cache.load(
            cache_key, max_age_hours=self._safe_float(self._state["cache_ttl"])
        )
        if cached is not None:
            return cached
        result = await self._execute_with_retry_async(func)
        cache.store(cache_key, result)
        return result

    def close(self) -> None:
        """Flush and persist any in-memory deferred requests to disk."""
        self._save_deferred_queue()
        self._log_telemetry(
            "shutdown_flush_deferred_queue",
            {"deferred_queue_size": len(self._deferred_queue)},
        )

    def _register_shutdown_hook(self) -> None:
        import atexit

        atexit.register(self.close)

        # Add to __init__ after all attributes are initialized:
        # ...existing code...
        self._register_shutdown_hook()

    def _log_telemetry(self, event: str, details: Optional[dict] = None) -> None:
        details = details or {}
        # _telemetry_destinations is always set in __init__
        for dest in getattr(self, "_telemetry_destinations", []):
            try:
                dest.send(event, details)
            except (OSError, IOError, AttributeError, TypeError, ValueError) as exc:
                logger.error("Telemetry destination failed: %s", exc)

    def _safe_float(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    # Circuit breaker state (class-level)
    _failure_count: int = 0
    _circuit_open_until: float = 0.0
    _max_failures: int = 5
    _circuit_breaker_timeout: float = 300.0  # seconds

    def __init__(
        self,
        api_key: str,
        *,
        settings: config.FirecrawlSettings = config.FIRECRAWL,
    ) -> None:
        self._settings = settings
        # Harden for both dataclass and dummy settings
        if (
            hasattr(settings.retry, "max_attempts")
            and hasattr(settings.retry, "initial_delay")
            and hasattr(settings.retry, "max_delay")
            and hasattr(settings.retry, "backoff_factor")
        ):
            try:
                # Try dataclass-like instantiation
                self._retry_policy = settings.retry.__class__(
                    max_attempts=settings.retry.max_attempts,
                    initial_delay=settings.retry.initial_delay,
                    max_delay=settings.retry.max_delay,
                    backoff_factor=settings.retry.backoff_factor,
                )
            except TypeError:
                # Fallback for dummy class
                self._retry_policy = settings.retry
        else:
            raise ValueError(
                "settings.retry must have max_attempts, initial_delay, max_delay, backoff_factor"
            )
        client_kwargs: Dict[str, Any] = {"api_key": api_key}
        if settings.api_url:
            client_kwargs["api_url"] = settings.api_url
        self._client = Firecrawl(**client_kwargs)
        self._state = {
            "cache_ttl": self._safe_float(getattr(config, "CACHE_TTL_HOURS", 24.0)),
            "min_interval": self._safe_float(
                max(
                    self._safe_float(getattr(settings.throttle, "min_interval", 1.0)),
                    self._safe_float(getattr(config, "REQUEST_DELAY_SECONDS", 1.0)),
                )
            ),
            "lock": threading.Lock(),
            "last_call": 0.0,
            "rate_limit_reset": 0.0,
        }
        # Persistent deferred request queue for rate-limited requests
        self._deferred_queue_path = getattr(
            settings,
            "deferred_queue_path",
            getattr(config, "DEFERRED_QUEUE_PATH", "data/interim/deferred_queue.json"),
        )
        self._deferred_queue = []
        try:
            with open(self._deferred_queue_path, "r", encoding="utf-8") as f:
                self._deferred_queue = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._deferred_queue = []
            # Register shutdown hook to flush deferred queue
            import atexit

            atexit.register(self.close)

    def _save_deferred_queue(self) -> None:
        try:
            with open(self._deferred_queue_path, "w", encoding="utf-8") as f:
                json.dump(self._deferred_queue, f)
        except OSError as exc:
            logger.error("Failed to save deferred queue: %s", exc)

    def _enqueue_deferred(self, method: str, args: Any, kwargs: Any) -> None:
        deferred_item = {
            "method": method,
            "args": args,
            "kwargs": kwargs,
            "timestamp": time.time(),
        }
        self._deferred_queue.append(deferred_item)
        self._save_deferred_queue()
        self._log_telemetry("deferred_request_enqueued", deferred_item)

    def process_deferred_queue(self) -> None:
        """Process deferred requests after circuit breaker closes."""
        if not self._deferred_queue:
            return
        self._log_telemetry(
            "deferred_queue_processing_started", {"count": len(self._deferred_queue)}
        )
        queue_copy = self._deferred_queue[:]
        self._deferred_queue.clear()
        self._save_deferred_queue()
        for item in queue_copy:
            method = getattr(self, item["method"], None)
            if not callable(method):
                logger.error("Deferred method %s not found", item["method"])
                self._log_telemetry("deferred_method_not_found", item)
                continue

            try:
                method(*item["args"], **item["kwargs"])
            except (RuntimeError, TypeError, ValueError) as exc:
                logger.error("Deferred Firecrawl request failed: %s", exc)
                self._enqueue_deferred(item["method"], item["args"], item["kwargs"])

    def await_rate_limit(self) -> None:
        """Sleep if a previous rate limit indicates a future reset window."""
        lock = self._state["lock"]
        if type(lock) is threading.Lock:
            with lock:
                remaining = (
                    self._safe_float(self._state["rate_limit_reset"]) - time.monotonic()
                )
                if remaining > 0:
                    logger.info(
                        "Waiting %.2fs for Firecrawl rate-limit reset", remaining
                    )
                    time.sleep(remaining)

    def set_retry_policy(
        self,
        max_attempts: Optional[int] = None,
        initial_delay: Optional[float] = None,
        max_delay: Optional[float] = None,
        backoff_factor: Optional[float] = None,
    ) -> None:
        """
        Update retry/backoff parameters at runtime.
        Args:
            max_attempts (Optional[int]): Maximum retry attempts.
            initial_delay (Optional[float]): Initial delay in seconds.
            max_delay (Optional[float]): Maximum delay in seconds.
            backoff_factor (Optional[float]): Backoff multiplier.
        Raises:
            ValueError: If any parameter is negative or zero where not allowed.
        """
        rp = self._retry_policy
        if max_attempts is not None and max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if initial_delay is not None and initial_delay < 0:
            raise ValueError("initial_delay must be >= 0")
        if max_delay is not None and max_delay < 0:
            raise ValueError("max_delay must be >= 0")
        if backoff_factor is not None and backoff_factor <= 0:
            raise ValueError("backoff_factor must be > 0")
        self._retry_policy = rp.__class__(
            max_attempts=max_attempts if max_attempts is not None else rp.max_attempts,
            initial_delay=(
                initial_delay if initial_delay is not None else rp.initial_delay
            ),
            max_delay=max_delay if max_delay is not None else rp.max_delay,
            backoff_factor=(
                backoff_factor if backoff_factor is not None else rp.backoff_factor
            ),
        )

    def get_retry_policy(self) -> Dict[str, float]:
        """
        Return current retry/backoff parameters.
        Returns:
            Dict[str, float]: Dictionary of retry policy parameters.
        """
        rp = self._retry_policy
        return {
            "max_attempts": rp.max_attempts,
            "initial_delay": rp.initial_delay,
            "max_delay": rp.max_delay,
            "backoff_factor": rp.backoff_factor,
        }

    def extract(self, urls: Iterable[str], prompt: str) -> Any:
        """
        Extract information from the given URLs using the specified prompt.

        Args:
            urls (Iterable[str]): A collection of URLs to extract data from.
            prompt (str): The prompt to guide extraction.

        Returns:
            Any: The extraction results from Firecrawl, possibly cached.
        """
        urls_tuple = tuple(sorted(urls))
        cache_key = f"extract::{urls_tuple}::{hash(prompt)}"
        return self._call_with_cache(
            cache_key,
            lambda: self._client.extract(urls=list(urls_tuple), prompt=prompt),
        )

    def crawl(self, url: str, **kwargs: Any) -> Any:
        """
        Crawl the specified URL using Firecrawl, with optional keyword arguments.

        Args:
            url (str): The URL to crawl.
            **kwargs (Any): Additional keyword arguments to pass to the Firecrawl client.

        Returns:
            Any: The crawl results from Firecrawl, possibly cached.
        """
        key_bits = [url] + [f"{k}={v}" for k, v in sorted(kwargs.items())]
        cache_key = "crawl::" + "::".join(key_bits)
        return self._call_with_cache(
            cache_key,
            lambda: self._client.crawl(url=url, **kwargs),
        )

    def _call_with_cache(self, cache_key: str, func: Callable[[], Any]) -> Any:
        cached = cache.load(
            cache_key, max_age_hours=self._safe_float(self._state["cache_ttl"])
        )
        if cached is not None:
            return cached
        result = self._execute_with_retry(func)
        cache.store(cache_key, result)
        return result

    def _execute_with_retry(self, func: Callable[[], Any]) -> Any:
        import random

        attempts = 0
        delay = self._retry_policy.initial_delay
        max_attempts = self._retry_policy.max_attempts
        max_delay = self._retry_policy.max_delay
        backoff_factor = self._retry_policy.backoff_factor
        now = time.monotonic()
        if self._circuit_open_until > now:
            logger.error(
                "Circuit breaker open: blocking Firecrawl calls for %ds",
                int(self._circuit_open_until - now),
            )
            self._log_telemetry(
                "circuit_breaker_open",
                {"open_until": self._circuit_open_until, "now": now},
            )
            # After circuit closes, process deferred queue
            if now >= self._circuit_open_until:
                self._log_telemetry("circuit_breaker_closed", {"now": now})
                self.process_deferred_queue()
            raise DeferredQueueFirecrawlError(
                "Firecrawl API temporarily blocked due to repeated failures.",
                details={"open_until": self._circuit_open_until, "now": now},
            ) from None
        while True:
            try:
                self._throttle()
                result = func()
                self._state["rate_limit_reset"] = 0.0
                self._failure_count = 0
                return result
            except RateLimitError as rate_exc:
                attempts += 1
                self._failure_count += 1
                base_wait = _retry_after_seconds(rate_exc, min(max_delay, 60.0))
                jitter = random.uniform(0, base_wait * 0.2)
                wait_time = base_wait + jitter
                logger.warning(
                    "Firecrawl rate limit encountered, sleeping %.2fs (attempt %d)",
                    wait_time,
                    attempts,
                )
                self._log_telemetry(
                    "rate_limit_retry",
                    {
                        "attempt": attempts,
                        "wait_time": wait_time,
                        "error": str(rate_exc),
                    },
                )
                if self._failure_count >= self._max_failures:
                    self._circuit_open_until = (
                        time.monotonic() + self._circuit_breaker_timeout
                    )
                    logger.critical(
                        "Circuit breaker triggered: %d consecutive rate-limit errors. Blocking for %ds.",
                        self._failure_count,
                        int(self._circuit_breaker_timeout),
                    )
                    self._log_telemetry(
                        "circuit_breaker_triggered",
                        {
                            "failures": self._failure_count,
                            "timeout": self._circuit_breaker_timeout,
                        },
                    )
                    self._enqueue_deferred(func.__name__, [], {})
                    raise RateLimitFirecrawlError(
                        "Circuit breaker: too many rate-limit errors.",
                        details={
                            "failures": self._failure_count,
                            "timeout": self._circuit_breaker_timeout,
                        },
                    ) from rate_exc
                time.sleep(wait_time)
            except (ConnectionError, TimeoutError) as exc:
                attempts += 1
                self._failure_count += 1
                logger.error("Firecrawl API failure: %s (attempt %d)", exc, attempts)
                self._log_telemetry(
                    "connection_error_retry",
                    {"attempt": attempts, "wait_time": delay, "error": str(exc)},
                )
                if self._failure_count >= self._max_failures:
                    self._circuit_open_until = (
                        time.monotonic() + self._circuit_breaker_timeout
                    )
                    logger.critical(
                        "Circuit breaker triggered: %d consecutive API failures. Blocking for %ds.",
                        self._failure_count,
                        int(self._circuit_breaker_timeout),
                    )
                    self._log_telemetry(
                        "circuit_breaker_triggered",
                        {
                            "failures": self._failure_count,
                            "timeout": self._circuit_breaker_timeout,
                        },
                    )
                    self._enqueue_deferred(func.__name__, [], {})
                    raise APIFirecrawlError(
                        "Circuit breaker: too many API failures.",
                        details={
                            "failures": self._failure_count,
                            "timeout": self._circuit_breaker_timeout,
                        },
                    ) from exc
                if attempts >= max_attempts:
                    raise APIFirecrawlError(
                        f"API error after {attempts} attempts.",
                        details={"error": str(exc), "attempts": attempts},
                    ) from exc
                logger.warning(
                    "Connection error encountered, sleeping %.2fs before retry (attempt %d)",
                    delay,
                    attempts,
                )
                time.sleep(delay)
                delay = min(delay * backoff_factor, max_delay)

    def _throttle(self) -> None:
        if self._safe_float(self._state["min_interval"]) <= 0:
            return
        now = time.monotonic()
        lock = self._state["lock"]
        if type(lock) is threading.Lock:
            with lock:
                wait_for_reset = self._safe_float(self._state["rate_limit_reset"]) - now
                wait_interval = self._safe_float(self._state["min_interval"]) - (
                    now - self._safe_float(self._state["last_call"])
                )
                wait = max(wait_for_reset, wait_interval)
                if wait > 0:
                    time.sleep(wait)
                    now = time.monotonic()
                self._state["last_call"] = now
            self._state["last_call"] = now


def summarize_extract_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return {}
    json_block = data.get("json")
    if isinstance(json_block, dict):
        return json_block
    if isinstance(json_block, list) and json_block and isinstance(json_block[0], dict):
        return json_block[0]
    return {}


def summarize_scrape_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return {}
    metadata = data.get("metadata")
    markdown = data.get("markdown")
    return {
        "metadata": metadata if isinstance(metadata, dict) else None,
        "markdown": markdown if isinstance(markdown, str) else None,
    }


def _retry_after_seconds(error: RateLimitError, default_wait: float) -> float:
    wait = default_wait
    retry_after = getattr(error, "retry_after", None)
    wait = _coalesce_wait(wait, retry_after)
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if isinstance(headers, dict):
        wait = _coalesce_wait(wait, headers.get("Retry-After"))
    message = str(error)
    match = re.search(r"after\s+(\d+)s", message)
    if match:
        wait = _coalesce_wait(wait, match.group(1))
    return max(wait, default_wait)


def _coalesce_wait(current: float, candidate: Optional[Any]) -> float:
    if candidate is None:
        return current
    try:
        value = float(candidate)
    except (TypeError, ValueError):
        return current
    return max(current, value)
