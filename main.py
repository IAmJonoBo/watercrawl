"""Main script for Firecrawl demo: loads API key, scrapes and extracts content from example URLs."""

# mypy: ignore-errors

from __future__ import annotations

from typing import Any

from firecrawl import Firecrawl

from firecrawl_demo.config import resolve_api_key


def ensure_api_key() -> str:
    """Load FIRECRAWL_API_KEY from the configured secrets provider."""
    try:
        return resolve_api_key()
    except ValueError as exc:
        raise RuntimeError(
            "Set FIRECRAWL_API_KEY in the configured secrets backend before running this script."
        ) from exc


def pretty_print(label: str, obj: Any) -> None:
    """Print a label followed by a trimmed representation of obj."""
    print(f"\n{label}:")
    if isinstance(obj, str):
        print(obj[:400])
        if len(obj) > 400:
            print("... [truncated]")
    else:
        print(obj)


def main() -> None:
    api_key = ensure_api_key()
    client = Firecrawl(api_key=api_key)

    # Example: scrape the Firecrawl homepage for markdown content.
    scrape_result = client.scrape("https://firecrawl.dev", formats=["markdown"])
    pretty_print("Scrape result", scrape_result.markdown)

    # Example: extract key details from the docs landing page using a prompt.
    extract_result = client.extract(
        urls=["https://docs.firecrawl.dev/introduction"],
        prompt="Summarize the main sections and purpose of the page in bullet points.",
    )
    pretty_print("Extract result", extract_result.data)


if __name__ == "__main__":
    main()
