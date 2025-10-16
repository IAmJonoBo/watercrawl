"""Simple JSON cache for Firecrawl responses."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, is_dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Optional

from . import config

config.CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(key: str) -> Path:
    safe_key = key.replace("/", "_").replace(" ", "_")
    return config.CACHE_DIR / f"{safe_key}.json"


def load(key: str, *, max_age_hours: Optional[float] = None) -> Optional[Any]:
    path = _cache_path(key)
    if not path.exists():
        return None
    if max_age_hours is not None:
        ttl = max_age_hours * 3600
        if time.time() - path.stat().st_mtime > ttl:
            return None
    with path.open("r", encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except JSONDecodeError:
            return None


def store(key: str, payload: Any) -> None:
    path = _cache_path(key)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(_json_safe(payload), fh, ensure_ascii=False, indent=2)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(value))
    if hasattr(value, "model_dump"):
        try:
            return _json_safe(value.model_dump())  # type: ignore[attr-defined]
        except TypeError:
            pass
    if hasattr(value, "dict"):
        try:
            return _json_safe(value.dict())  # type: ignore[attr-defined]
        except TypeError:
            pass
    if hasattr(value, "__dict__"):
        return _json_safe(vars(value))
    return str(value)
