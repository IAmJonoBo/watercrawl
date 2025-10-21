"""Minimal typing stubs for PyYAML used by the project.

This is a conservative, small fallback so editors and type-checkers can resolve
`import yaml` even when the active interpreter doesn't have types installed.
Prefer installing `types-pyyaml` in your environment; this file is a safety net.
"""

from typing import Any, Iterable

def safe_load(_stream: Any) -> Any: ...
def safe_load_all(_stream: Any) -> Iterable[Any]: ...
def load(_stream: Any) -> Any: ...
def dump(_data: Any, _stream: Any | None = None, **_kwargs: Any) -> str | None: ...
def safe_dump(_data: Any, _stream: Any | None = None, **_kwargs: Any) -> str: ...

Loader = Any
Dumper = Any
