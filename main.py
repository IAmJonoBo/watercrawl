"""Main script for Firecrawl demo: loads API key, scrapes and extracts content from example URLs."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from firecrawl import Firecrawl


def ensure_api_key() -> str:
    """Load FIRECRAWL_API_KEY from .env or the environment."""
    env_path = Path(__file__).with_name(".env")
    if env_path.exists():
        load_dotenv(env_path)
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Set FIRECRAWL_API_KEY in firecrawl-demo/.env before running this script."
        )
    return api_key


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
