from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from firecrawl_demo import config


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


class LocalLakehouseWriter:
    """Persist curated tables locally using Parquet as a Delta-style snapshot."""

    def __init__(self, config: LakehouseConfig | None = None) -> None:
        self._config = config or LakehouseConfig()

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    def write(self, run_id: str, dataframe: pd.DataFrame) -> LakehouseManifest:
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
            )

        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        version = f"{timestamp}-{run_id}"
        table_dir = self._config.root_path / self._config.table_name / version
        table_dir.mkdir(parents=True, exist_ok=True)

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
        )


def build_lakehouse_writer() -> LocalLakehouseWriter | None:
    """Return a configured lakehouse writer when the feature is enabled."""

    settings = LakehouseConfig()
    if not settings.enabled:
        return None
    return LocalLakehouseWriter(settings)


__all__ = [
    "LakehouseConfig",
    "LakehouseManifest",
    "LocalLakehouseWriter",
    "build_lakehouse_writer",
]
