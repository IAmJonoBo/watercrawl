from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from collections.abc import Iterable

from .config import settings

try:  # pragma: no cover - optional dependency
    from firecrawl import Firecrawl  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - graceful degradation
    Firecrawl = None  # type: ignore[assignment]


@dataclass
class FirecrawlClient:
    """Thin wrapper around the Firecrawl SDK with safe fallbacks for tests."""

    api_key: str | None = None
    api_url: str | None = None

    def _client(self) -> Firecrawl:
        if Firecrawl is None:
            raise RuntimeError("Firecrawl SDK is not installed")
        key = self.api_key or getattr(settings, "FIRECRAWL_API_KEY", None)
        if not key:
            raise RuntimeError("FIRECRAWL_API_KEY is not configured")
        return Firecrawl(
            api_key=key,
            api_url=self.api_url or getattr(settings, "FIRECRAWL_API_URL", None),
        )

    def scrape(
        self, url: str, *, formats: Iterable[str] | None = None
    ) -> dict[str, Any]:
        client = self._client()
        result = client.scrape(url=url, formats=list(formats or ["markdown"]))
        return getattr(result, "data", result)

    def extract(self, urls: Iterable[str], prompt: str) -> dict[str, Any]:
        client = self._client()
        result = client.extract(urls=list(urls), prompt=prompt)
        return getattr(result, "data", result)

    def search(self, query: str, *, limit: int = 5) -> dict[str, Any]:
        client = self._client()
        result = client.search(query=query, limit=limit)
        return getattr(result, "data", result)


def summarize_extract_payload(payload: dict[str, Any]) -> dict[str, str | None]:
    """Normalize Firecrawl extract payload into simple contact dict."""

    data: Any = payload or {}
    if isinstance(data, dict) and "data" in data:
        data = data.get("data")
    if isinstance(data, dict) and "attributes" in data:
        data = data.get("attributes")

    if not isinstance(data, dict):
        return {}

    fields = {
        "contact_person": data.get("contact_person") or data.get("contactPerson"),
        "contact_email": data.get("contact_email") or data.get("contactEmail"),
        "contact_phone": data.get("contact_phone") or data.get("contactPhone"),
        "physical_address": data.get("physical_address") or data.get("address"),
        "accreditation": data.get("accreditation"),
        "fleet_overview": data.get("fleet_overview") or data.get("fleet"),
        "website_url": data.get("website_url") or data.get("website"),
        "linkedin_url": data.get("linkedin_url") or data.get("linkedin"),
        "facebook_url": data.get("facebook_url") or data.get("facebook"),
    }
    return {
        key: (value.strip() if isinstance(value, str) else value)
        for key, value in fields.items()
        if value
    }
