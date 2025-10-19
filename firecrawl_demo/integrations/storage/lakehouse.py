from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import pandas as pd

    _PANDAS_AVAILABLE = True
except ImportError:
    pd = None  # type: ignore
    _PANDAS_AVAILABLE = False

from firecrawl_demo.core import config
from firecrawl_demo.integrations.integration_plugins import (
    IntegrationPlugin,
    PluginConfigSchema,
    PluginContext,
    PluginHealthStatus,
    register_plugin,
)


@dataclass(slots=True)
class LakehouseConfig:
    """Configuration for persisting curated tables to the lakehouse."""

    backend: str = field(default_factory=lambda: config.LAKEHOUSE.backend)
    root_path: Path = field(default_factory=lambda: config.LAKEHOUSE.root_path)
    table_name: str = field(default_factory=lambda: config.LAKEHOUSE.table_name)
    enabled: bool = field(default_factory=lambda: config.LAKEHOUSE.enabled)


@dataclass(frozen=True)
class LakehouseManifest:
    """Metadata describing a lakehouse snapshot."""

    table_uri: str
    table_path: Path
    manifest_path: Path
    format: str
    version: str
    fingerprint: str
    row_count: int


class LocalLakehouseWriter:
    """Persist curated tables locally using Parquet as a Delta-style snapshot."""

    def __init__(self, config: LakehouseConfig | None = None) -> None:
        self._config = config or LakehouseConfig()

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    def write(self, run_id: str, dataframe: Any) -> LakehouseManifest:
        if not self.enabled:
            table_dir = self._config.root_path / "disabled"
            table_dir.mkdir(parents=True, exist_ok=True)
            manifest_path = table_dir / "manifest.json"
            manifest_path.write_text(
                json.dumps({"enabled": False, "run_id": run_id}, indent=2)
            )
            return LakehouseManifest(
                table_uri=f"{self._config.backend}://disabled",
                table_path=table_dir,
                manifest_path=manifest_path,
                format=self._config.backend,
                version="disabled",
                fingerprint="",
                row_count=0,
            )

        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        version = f"{timestamp}-{run_id}"
        table_dir = self._config.root_path / self._config.table_name / version
        table_dir.mkdir(parents=True, exist_ok=True)

        normalized = dataframe.reset_index(drop=True).reindex(
            sorted(dataframe.columns), axis=1
        )
        fingerprint = hashlib.sha256(
            normalized.to_csv(index=False).encode("utf-8")
        ).hexdigest()
        row_count = int(len(dataframe))
        schema = {column: str(dtype) for column, dtype in dataframe.dtypes.items()}

        data_path = table_dir / "data.parquet"
        dataframe.to_parquet(data_path, index=False)

        manifest: dict[str, Any] = {
            "backend": self._config.backend,
            "table": self._config.table_name,
            "version": version,
            "run_id": run_id,
            "artifacts": {
                "data": data_path.name,
            },
            "created_at": datetime.utcnow().isoformat(),
            "fingerprint": fingerprint,
            "row_count": row_count,
            "schema": schema,
            "environment": {
                "profile": config.DEPLOYMENT.profile,
                "codex_enabled": config.DEPLOYMENT.codex_enabled,
                "crawler_mode": config.DEPLOYMENT.crawler_mode,
            },
            "versioning": {
                "enabled": config.VERSIONING.enabled,
                "strategy": config.VERSIONING.strategy,
                "metadata_root": str(config.VERSIONING.metadata_root),
            },
        }
        manifest_path = table_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))

        table_uri = f"{self._config.backend}://{table_dir.resolve().as_posix()}"
        return LakehouseManifest(
            table_uri=table_uri,
            table_path=table_dir,
            manifest_path=manifest_path,
            format=self._config.backend,
            version=version,
            fingerprint=fingerprint,
            row_count=row_count,
        )


def build_lakehouse_writer() -> LocalLakehouseWriter | None:
    """Return a configured lakehouse writer when the feature is enabled."""

    settings = LakehouseConfig()
    if not settings.enabled:
        return None
    return LocalLakehouseWriter(settings)


def _lakehouse_health_probe(context: PluginContext) -> PluginHealthStatus:
    settings = LakehouseConfig()
    details = {
        "enabled": settings.enabled,
        "backend": settings.backend,
        "root_path": str(settings.root_path),
    }

    if not settings.enabled:
        return PluginHealthStatus(
            healthy=True, reason="Lakehouse disabled", details=details
        )

    if not settings.root_path.exists():
        return PluginHealthStatus(
            healthy=False,
            reason="Lakehouse root path does not exist",
            details=details,
        )

    if not settings.root_path.is_dir():
        return PluginHealthStatus(
            healthy=False,
            reason="Lakehouse root path is not a directory",
            details=details,
        )

    return PluginHealthStatus(healthy=True, reason="Lakehouse ready", details=details)


register_plugin(
    IntegrationPlugin(
        name="lakehouse",
        category="storage",
        factory=lambda ctx: build_lakehouse_writer(),
        config_schema=PluginConfigSchema(
            feature_flags=("LAKEHOUSE_ENABLED",),
            environment_variables=("LAKEHOUSE_ROOT", "LAKEHOUSE_TABLE_NAME"),
            optional_dependencies=("pandas",),
            description=(
                "Persist curated datasets to local lakehouse storage when enabled."
            ),
        ),
        health_probe=_lakehouse_health_probe,
        summary="Local Parquet lakehouse writer",
    )
)


__all__ = [
    "LakehouseConfig",
    "LakehouseManifest",
    "LocalLakehouseWriter",
    "build_lakehouse_writer",
]
