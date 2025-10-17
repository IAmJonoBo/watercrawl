#!/usr/bin/env python3
"""
Firecrawl Examples - Comprehensive demonstration of all Firecrawl features
Based on the official documentation at https://docs.firecrawl.dev/introduction
"""

from __future__ import annotations

import json
from typing import Any

from firecrawl import Firecrawl  # type: ignore
from pydantic import BaseModel

from firecrawl_demo.core.config import resolve_api_key


def ensure_api_key() -> str:
    """Load FIRECRAWL_API_KEY from the configured secrets provider."""
    try:
        return resolve_api_key()
    except ValueError as exc:
        raise RuntimeError(
            "Set FIRECRAWL_API_KEY in the configured secrets backend before running this script."
        ) from exc


def pretty_print(label: str, obj: Any) -> None:
    """Print a label followed by a formatted representation of obj."""
    print(f"\n{'='*60}")
    print(f"{label}")
    print("=" * 60)

    if isinstance(obj, str):
        print(obj[:500])
        if len(obj) > 500:
            print("... [truncated]")
    elif isinstance(obj, dict):
        print(json.dumps(obj, indent=2)[:800])
        if len(str(obj)) > 800:
            print("... [truncated]")
    else:
        print(str(obj)[:800])
        if len(str(obj)) > 800:
            print("... [truncated]")


class CompanyInfo(BaseModel):
    """Pydantic schema for structured data extraction."""

    company_mission: str
    supports_sso: bool
    is_open_source: bool
    is_in_yc: bool


def demo_scraping(client: Firecrawl) -> None:
    """Demonstrate basic scraping functionality."""
    print("\n🔍 SCRAPING DEMO")

    # Basic scraping with markdown format
    result = client.scrape("https://firecrawl.dev", formats=["markdown"])
    pretty_print("Basic Scrape (Markdown)", result.markdown)

    # Scraping with multiple formats
    result = client.scrape("https://firecrawl.dev", formats=["markdown", "html"])
    pretty_print("Metadata", result.metadata)


def demo_json_mode(client: Firecrawl) -> None:
    """Demonstrate JSON mode with structured data extraction."""
    print("\n📋 JSON MODE DEMO")

    # JSON mode with Pydantic schema
    result = client.scrape(
        "https://firecrawl.dev",
        formats=[{"type": "json", "schema": CompanyInfo}],
        only_main_content=False,
        timeout=120000,
    )
    pretty_print("Structured Data with Schema", result.json)

    # JSON mode with prompt (no schema)
    result = client.scrape(
        "https://firecrawl.dev",
        formats=[
            {
                "type": "json",
                "prompt": "Extract the company mission and key features from the page.",
            }
        ],
        only_main_content=False,
        timeout=120000,
    )
    pretty_print("Structured Data with Prompt", result.json)


def demo_crawling(client: Firecrawl) -> None:
    """Demonstrate crawling functionality."""
    print("\n🕷️ CRAWLING DEMO")

    # Crawl a website (limited to 3 pages for demo)
    docs = client.crawl(url="https://docs.firecrawl.dev", limit=3)
    try:
        # Try to access as a list of documents
        pretty_print("Crawl Results", str(docs)[:500])
    except (AttributeError, TypeError):
        pretty_print("Crawl Results", str(docs)[:500])


def demo_search(client: Firecrawl) -> None:
    """Demonstrate search functionality."""
    print("\n🔎 SEARCH DEMO")

    # Search the web
    results = client.search(
        query="firecrawl web scraping",
        limit=3,
    )
    pretty_print("Search Results", results)


def demo_extract(client: Firecrawl) -> None:
    """Demonstrate extract functionality."""
    print("\n📤 EXTRACT DEMO")

    # Extract information from multiple URLs
    extract_result = client.extract(
        urls=["https://docs.firecrawl.dev/introduction"],
        prompt="Summarize the main features and capabilities of Firecrawl in bullet points.",
    )
    pretty_print("Extract Result", extract_result.data)


def demo_actions(_client: Firecrawl) -> None:
    """Demonstrate page actions before scraping."""
    print("\n⚡ ACTIONS DEMO")

    # Note: Actions require specific action objects in the current SDK
    # This is a simplified example - see official docs for full action syntax
    print("Actions allow you to interact with pages before scraping:")
    print("- wait: Wait for page to load")
    print("- screenshot: Take screenshots")
    print("- click: Click elements")
    print("- write: Input text")
    print("- press: Press keys")
    print("See the official docs for detailed action examples.")


def main() -> None:
    """Run all Firecrawl examples."""
    api_key = ensure_api_key()
    client = Firecrawl(api_key=api_key)

    print("🚀 Firecrawl Examples Demo")
    print("Based on https://docs.firecrawl.dev/introduction")

    try:
        demo_scraping(client)
        demo_json_mode(client)
        demo_extract(client)
        demo_search(client)
        demo_crawling(client)
        demo_actions(client)

        print(f"\n{'='*60}")
        print("✅ All demos completed successfully!")
        print("='*60")

    except (ValueError, RuntimeError, ConnectionError) as e:
        print(f"\n❌ Error: {e}")
        raise


if __name__ == "__main__":
    main()
