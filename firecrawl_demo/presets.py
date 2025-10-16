from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from . import config

PRESET_MAP: dict[str, dict[str, Any]] = {}
"""Utilities for working with Firecrawl preset templates."""

_PRESET_FILES = {
    "map": "firecrawl_map.json",
    "scrape": "firecrawl_scrape.json",
    "crawl": "firecrawl_crawl.json",
}


def load_preset_template(name: str) -> dict[str, Any]:
    """Return the raw preset template dictionary from the presets directory."""

    try:
        filename = _PRESET_FILES[name]
    except KeyError as exc:  # pragma: no cover - defensive guard
        raise ValueError(
            f"Unknown preset '{name}'. Expected one of {sorted(_PRESET_FILES)}"
        ) from exc
    path = config.PROJECT_ROOT / "presets" / filename
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def map_payload(domain_url: str, *, limit: int | None = None) -> dict[str, Any]:
    payload = deepcopy(load_preset_template("map"))
    payload["url"] = domain_url
    if limit is not None:
        payload["limit"] = limit
    return payload


def scrape_payload(page_url: str) -> dict[str, Any]:
    payload = deepcopy(load_preset_template("scrape"))
    payload["url"] = page_url
    return payload


def crawl_payload(
    domain_url: str, *, include_paths: list[str] | None = None
) -> dict[str, Any]:
    payload = deepcopy(load_preset_template("crawl"))
    payload["url"] = domain_url
    if include_paths:
        payload["includePaths"] = include_paths
    return payload


def render_curl_command(
    endpoint: str, payload_path: Path, output_path: Path | None = None
) -> str:
    """Return a ready-to-run curl command string for the given preset payload."""

    command = [
        "curl",
        "-sS",
        "-X",
        "POST",
        endpoint,
        "-H",
        "Content-Type: application/json",
        "-d",
        f"@{payload_path}",
    ]
    rendered = " ".join(command)
    if output_path:
        rendered += f" > {output_path}"
    return rendered
