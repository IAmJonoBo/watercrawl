from __future__ import annotations

import logging
import tomllib
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from firecrawl_demo.core import config
from firecrawl_demo.governance.secrets import SecretsProvider

from .core import NullResearchAdapter, ResearchAdapter, _build_firecrawl_adapter

logger = logging.getLogger(__name__)

AdapterFactory = Callable[["AdapterContext"], ResearchAdapter | None]


@dataclass(slots=True)
class AdapterLoaderSettings:
    """Hints used when resolving adapter sequences."""

    provider: SecretsProvider | None = None
    sequence: Sequence[str] | None = None
    env_var: str = "RESEARCH_ADAPTERS"
    file_env_var: str = "RESEARCH_ADAPTERS_FILE"
    # Firecrawl remains opt-in until the production SDK rollout is complete.
    # The default stack therefore favours deterministic, offline-safe adapters
    # and terminates with the null adapter as a guard rail. Firecrawl can still
    # be enabled via feature flags + configuration once the SDK is available.
    default_sequence: Sequence[str] = ("regulator", "press", "ml", "null")


@dataclass(slots=True, frozen=True)
class AdapterContext:
    """Context supplied to adapter factories when constructing pipelines."""

    config: ModuleType
    settings: AdapterLoaderSettings


_ADAPTER_FACTORIES: dict[str, AdapterFactory] = {}


def register_adapter(name: str, factory: AdapterFactory) -> None:
    """Register or replace an adapter factory available to the pipeline."""

    normalized = _normalize_name(name)
    if not normalized:
        raise ValueError("Adapter name must be a non-empty string")
    if not callable(factory):
        raise TypeError("Adapter factory must be callable")

    _ADAPTER_FACTORIES[normalized] = factory
    logger.debug("Registered research adapter: %s", normalized)


def load_enabled_adapters(
    settings: AdapterLoaderSettings | None = None,
) -> list[ResearchAdapter]:
    """Instantiate adapters based on configuration and feature flags."""

    active_settings = settings or AdapterLoaderSettings()
    provider = active_settings.provider or config.SECRETS_PROVIDER

    requested = list(_resolve_sequence(active_settings, provider))

    adapters: list[ResearchAdapter] = []
    context = AdapterContext(config=config, settings=active_settings)
    seen: set[str] = set()

    for name in requested:
        key = _normalize_name(name)
        if not key or key in seen:
            continue
        seen.add(key)

        factory = _ADAPTER_FACTORIES.get(key)
        if factory is None:
            raise ValueError(f"Adapter '{name}' is not registered")

        adapter = factory(context)
        if adapter is None:
            continue
        adapters.append(adapter)

    return adapters


def _resolve_sequence(
    settings: AdapterLoaderSettings, provider: SecretsProvider | None
) -> Iterable[str]:
    if settings.sequence:
        return settings.sequence

    from_env = _sequence_from_env(settings, provider)
    if from_env:
        return from_env

    return settings.default_sequence


def _sequence_from_env(
    settings: AdapterLoaderSettings, provider: SecretsProvider | None
) -> list[str]:
    if provider is None:
        return []

    file_hint = provider.get(settings.file_env_var)
    if file_hint:
        sequence = _read_sequence_from_file(Path(file_hint))
        if sequence:
            return sequence

    value = provider.get(settings.env_var)
    if value:
        return _parse_env_sequence(value)

    return []


def _read_sequence_from_file(path: Path) -> list[str]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - defensive logging
        logger.warning("Unable to read adapter configuration at %s: %s", path, exc)
        return []

    suffix = path.suffix.lower()
    if suffix in {".toml"}:
        return _parse_toml_sequence(raw)
    if suffix in {".yaml", ".yml"}:
        return _parse_yaml_sequence(raw)

    logger.warning(
        "Unsupported adapter configuration format for %s; expected YAML or TOML",
        path,
    )
    return []


def _parse_toml_sequence(raw: str) -> list[str]:
    try:
        data = tomllib.loads(raw)
    except Exception as exc:  # pragma: no cover - parsing guard
        logger.warning("Failed to parse TOML adapter configuration: %s", exc)
        return []
    return _extract_sequence_from_data(data)


def _parse_yaml_sequence(raw: str) -> list[str]:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:  # pragma: no cover - fallback parser
        return _parse_simple_yaml_sequence(raw)

    try:
        data = yaml.safe_load(raw)
    except Exception as exc:  # pragma: no cover - parsing guard
        logger.warning("Failed to parse YAML adapter configuration: %s", exc)
        return []
    return _extract_sequence_from_data(data)


def _parse_simple_yaml_sequence(raw: str) -> list[str]:
    values: list[str] = []
    capture = False
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.endswith(":"):
            key = stripped[:-1].strip().lower()
            capture = key in {"adapters", "research_adapters", "sequence"}
            continue
        if ":" in stripped and "[" in stripped and stripped.endswith("]"):
            key, rest = stripped.split(":", 1)
            if key.strip().lower() in {"adapters", "research_adapters", "sequence"}:
                values.extend(
                    _strip_quotes(item.strip())
                    for item in rest.strip().strip("[]").split(",")
                    if item.strip()
                )
                continue
        if stripped.startswith("-"):
            item = _strip_quotes(stripped.lstrip("-").strip())
            if item:
                values.append(item)
            continue
        if capture:
            item = _strip_quotes(stripped)
            if item:
                values.append(item)
    return values


def _extract_sequence_from_data(data: object) -> list[str]:
    if isinstance(data, dict):
        for key in ("adapters", "research_adapters", "sequence"):
            value = data.get(key)
            sequence = _coerce_to_list(value)
            if sequence:
                return sequence
    return _coerce_to_list(data)


def _coerce_to_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_strip_quotes(value)] if value.strip() else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        result: list[str] = []
        for item in value:
            if item is None:
                stripped = "null"
            elif isinstance(item, str):
                stripped = _strip_quotes(item)
            elif isinstance(item, Sequence) and not isinstance(
                item, (bytes, bytearray)
            ):
                continue
            else:
                stripped = str(item)
            stripped = stripped.strip()
            if stripped:
                result.append(stripped)
        return result
    return []


def _parse_env_sequence(value: str) -> list[str]:
    parts = [part.strip() for part in value.replace("\n", ",").split(",")]
    return [part for part in parts if part]


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _normalize_name(name: str) -> str:
    return name.strip().lower()


def _firecrawl_factory(context: AdapterContext) -> ResearchAdapter | None:
    if not context.config.FEATURE_FLAGS.enable_crawlkit:
        return None
    return _build_firecrawl_adapter()


def _null_factory(_: AdapterContext) -> ResearchAdapter:
    return NullResearchAdapter()


# Register built-in adapters immediately for default behaviour.
register_adapter("firecrawl", _firecrawl_factory)
register_adapter("crawlkit", _firecrawl_factory)
register_adapter("null", _null_factory)

# Ensure exemplar adapters are registered alongside built-ins.
try:  # pragma: no cover - defensive import
    from . import exemplars as _exemplar_adapters  # noqa: F401
except Exception as exc:  # pragma: no cover - defensive logging
    logger.debug("Unable to load exemplar adapters: %s", exc)


__all__ = [
    "AdapterContext",
    "AdapterLoaderSettings",
    "AdapterFactory",
    "load_enabled_adapters",
    "register_adapter",
]
