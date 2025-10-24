#!/usr/bin/env python3
"""Crawlkit Examples — demonstrations of fetch, distill, and entity extraction flows."""

from __future__ import annotations

from typing import Any

from crawlkit.adapter.firecrawl_compat import fetch_markdown


def pretty_print(label: str, value: Any) -> None:
    """Render labelled output with truncation for readability."""
    print(f"\n{'=' * 60}")
    print(label)
    print("=" * 60)
    text = value if isinstance(value, str) else str(value)
    print(text[:800])
    if len(text) > 800:
        print("... [truncated]")


def demo_markdown(url: str) -> None:
    """Fetch Markdown for a single URL using Crawlkit."""
    bundle = fetch_markdown(url)
    pretty_print("Markdown", bundle.get("markdown", ""))
    pretty_print("Entities", bundle.get("entities", []))
    pretty_print("Metadata", bundle.get("metadata", {}))


def demo_depth(url: str) -> None:
    """Demonstrate depth and subpath crawling via fetch_many semantics."""
    bundle = fetch_markdown(url, depth=2, include_subpaths=True)
    for item in bundle.get("items", []):
        pretty_print(f"Markdown ({item.get('url', '')})", item.get("markdown", ""))


def main() -> None:
    print("🚀 Crawlkit Examples")
    demo_markdown("https://example.com")
    demo_depth("https://example.com/docs")
    print(
        (
            "\nTip: `uvicorn watercrawl.interfaces.cli:create_app --factory` exposes /crawlkit/crawl,"
            " /crawlkit/markdown, and /crawlkit/entities for automation harnesses."
        )
    )


if __name__ == "__main__":
    main()
