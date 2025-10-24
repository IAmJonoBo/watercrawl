"""Example script showcasing Crawlkit fetch and distillation helpers."""

from __future__ import annotations

from typing import Any, Mapping

from crawlkit.adapter.firecrawl_compat import fetch_markdown


def pretty_print(label: str, obj: Any) -> None:
    """Print a label followed by a trimmed representation of obj."""
    print(f"\n{label}:")
    if isinstance(obj, str):
        print(obj[:400])
        if len(obj) > 400:
            print("... [truncated]")
    else:
        print(obj)


def main(
    url: str = "https://example.com", policy: Mapping[str, Any] | None = None
) -> None:
    """Fetch Markdown, text, and entities for the provided URL via Crawlkit."""

    bundle = fetch_markdown(url, policy=policy)
    if "items" in bundle:
        for item in bundle["items"]:
            pretty_print("Markdown", item.get("markdown", ""))
            pretty_print("Entities", item.get("entities", []))
    else:
        pretty_print("Markdown", bundle.get("markdown", ""))
        pretty_print("Entities", bundle.get("entities", []))
        pretty_print("Metadata", bundle.get("metadata", {}))

    print(
        (
            "\nTip: run `uvicorn watercrawl.interfaces.cli:create_app --factory` to serve the"
            " /crawlkit/crawl, /crawlkit/markdown, and /crawlkit/entities endpoints backed by"
            " the same adapters."
        )
    )


if __name__ == "__main__":
    main()
