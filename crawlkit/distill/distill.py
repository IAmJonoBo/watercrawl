"""Content distillation helpers converting HTML into Markdown."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Literal

from ..types import DistilledDoc

__all__ = ["DistilledDoc", "distill"]


_HEADING_TAGS = {
    "h1": "#",
    "h2": "##",
    "h3": "###",
    "h4": "####",
    "h5": "#####",
    "h6": "######",
}
_BLOCK_TAGS = {"p", "div", "section", "article", "header", "footer", "li"}


class _MarkdownParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._current_tag: str | None = None
        self._list_depth = 0

    def handle_starttag(self, tag: str, attrs):
        tag = tag.lower()
        if tag in _HEADING_TAGS:
            self._chunks.append(f"{_HEADING_TAGS[tag]} ")
            self._current_tag = tag
        elif tag == "li":
            indent = "  " * self._list_depth
            self._chunks.append(f"{indent}- ")
            self._current_tag = tag
        elif tag in {"ul", "ol"}:
            self._list_depth += 1
        elif tag in {"br"}:
            self._chunks.append("\n")
        elif tag in _BLOCK_TAGS:
            self._current_tag = tag

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag in {"ul", "ol"}:
            self._list_depth = max(self._list_depth - 1, 0)
        if tag in _BLOCK_TAGS or tag in _HEADING_TAGS:
            self._chunks.append("\n\n")
        self._current_tag = None

    def handle_data(self, data: str):
        text = data.strip()
        if not text:
            return
        self._chunks.append(text)

    def get_markdown(self) -> str:
        combined = "".join(self._chunks)
        normalized = re.sub(r"\n{3,}", "\n\n", combined)
        return normalized.strip()


_META_SELECTORS = {
    "title": re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL),
    "description": re.compile(
        r'<meta[^>]*name=["\']description["\'][^>]*content=["\'](.*?)["\']',
        re.IGNORECASE | re.DOTALL,
    ),
    "og:title": re.compile(
        r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\'](.*?)["\']',
        re.IGNORECASE | re.DOTALL,
    ),
    "og:description": re.compile(
        r'<meta[^>]*property=["\']og:description["\'][^>]*content=["\'](.*?)["\']',
        re.IGNORECASE | re.DOTALL,
    ),
}


def _extract_json_ld(html: str) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for match in re.finditer(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            results.append(payload)
        elif isinstance(payload, list):
            results.extend(item for item in payload if isinstance(item, dict))
    return results


def _extract_text(html: str) -> str:
    parser = _MarkdownParser()
    parser.feed(html)
    text = parser.get_markdown()
    return text


def _extract_meta(html: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for key, pattern in _META_SELECTORS.items():
        match = pattern.search(html)
        if match:
            metadata[key] = re.sub(r"\s+", " ", match.group(1).strip())
    return metadata


def distill(
    html: str, url: str, profile: Literal["article", "docs", "catalog"] = "article"
) -> DistilledDoc:
    """Distil HTML into markdown, returning a :class:`DistilledDoc`."""

    markdown = _extract_text(html)
    text = re.sub(r"\s+", " ", markdown)
    meta = _extract_meta(html)
    microdata = {"json_ld": _extract_json_ld(html)}
    if profile == "docs":
        meta["profile"] = "docs"
    elif profile == "catalog":
        meta["profile"] = "catalog"
    else:
        meta["profile"] = "article"
    return DistilledDoc(
        url=url, markdown=markdown, text=text, meta=meta, microdata=microdata
    )
