"""Dataset versioning helpers for lakehouse automation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from firecrawl_demo.core import config
from firecrawl_demo.integrations.integration_plugins import (
    IntegrationPlugin,
    PluginConfigSchema,
    PluginContext,
    PluginHealthStatus,
    register_plugin,
)

from .lakehouse import LakehouseManifest


def fingerprint_dataframe(dataframe: pd.DataFrame) -> str:
    """Generate a deterministic fingerprint for the provided dataframe."""

    normalized = dataframe.reset_index(drop=True).reindex(
        sorted(dataframe.columns), axis=1
    )
    return hashlib.sha256(normalized.to_csv(index=False).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class VersionInfo:
    """Recorded metadata for a reproducible dataset snapshot."""

    run_id: str
    version: str
    metadata_path: Path
    lakehouse_manifest: Path
    output_fingerprint: str
    input_fingerprint: str
    reproduce_command: tuple[str, ...] = field(default_factory=tuple)
    extras: dict[str, Any] = field(default_factory=dict)


class VersioningManager:
    """Persist version manifests for curated lakehouse outputs."""

    def __init__(
        self,
        metadata_root: Path | None = None,
        *,
        enabled: bool | None = None,
        strategy: str | None = None,
        reproduce_command: tuple[str, ...] | None = None,
    ) -> None:
        settings = config.VERSIONING
        self._metadata_root = metadata_root or settings.metadata_root
        self._enabled = settings.enabled if enabled is None else enabled
        self._strategy = settings.strategy if strategy is None else strategy
        self._reproduce_command = reproduce_command or settings.reproduce_command
        self._dvc_remote = settings.dvc_remote
        self._lakefs_repo = settings.lakefs_repo

    @property
    def enabled(self) -> bool:
        return self._enabled

    def record_snapshot(
        self,
        *,
        run_id: str,
        manifest: LakehouseManifest,
        input_fingerprint: str,
        extras: dict[str, Any] | None = None,
    ) -> VersionInfo:
        """Record a manifest describing the curated dataset snapshot."""

        extras = extras or {}
        if not self.enabled:
            placeholder = self._metadata_root / "disabled" / f"{run_id}.json"
            placeholder.parent.mkdir(parents=True, exist_ok=True)
            disabled_payload = {
                "enabled": False,
                "run_id": run_id,
                "input_fingerprint": input_fingerprint,
                "output_fingerprint": manifest.fingerprint,
                "generated_at": datetime.utcnow().isoformat(),
            }
            placeholder.write_text(
                json.dumps(disabled_payload, indent=2, sort_keys=True)
            )
            return VersionInfo(
                run_id=run_id,
                version="disabled",
                metadata_path=placeholder,
                lakehouse_manifest=manifest.manifest_path,
                output_fingerprint=manifest.fingerprint,
                input_fingerprint=input_fingerprint,
                reproduce_command=self._reproduce_command,
                extras=dict(extras),
            )

        snapshot_dir = self._metadata_root / manifest.version
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = snapshot_dir / "version.json"
        payload: dict[str, Any] = {
            "run_id": run_id,
            "version": manifest.version,
            "created_at": datetime.utcnow().isoformat(),
            "input_fingerprint": input_fingerprint,
            "output_fingerprint": manifest.fingerprint,
            "output_row_count": manifest.row_count,
            "lakehouse_manifest": manifest.manifest_path.as_posix(),
            "table_uri": manifest.table_uri,
            "strategy": self._strategy,
            "reproduce": {
                "command": list(self._reproduce_command),
                "notes": "Invoke the enrichment CLI with the recorded run parameters to reproduce this snapshot.",
            },
            "extras": extras,
        }
        if self._dvc_remote:
            payload["dvc_remote"] = self._dvc_remote
        if self._lakefs_repo:
            payload["lakefs_repo"] = self._lakefs_repo

        metadata_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
        return VersionInfo(
            run_id=run_id,
            version=manifest.version,
            metadata_path=metadata_path,
            lakehouse_manifest=manifest.manifest_path,
            output_fingerprint=manifest.fingerprint,
            input_fingerprint=input_fingerprint,
            reproduce_command=self._reproduce_command,
            extras=dict(extras),
        )


def build_versioning_manager() -> VersioningManager | None:
    """Create a versioning manager when versioning is enabled."""

    if not config.VERSIONING.enabled:
        return None
    return VersioningManager()


def _versioning_health_probe(context: PluginContext) -> PluginHealthStatus:
    settings = config.VERSIONING
    details = {
        "enabled": settings.enabled,
        "metadata_root": str(settings.metadata_root),
        "strategy": settings.strategy,
    }

    if not settings.enabled:
        return PluginHealthStatus(healthy=True, reason="Versioning disabled", details=details)

    if not settings.metadata_root.exists():
        return PluginHealthStatus(
            healthy=False,
            reason="Metadata root does not exist",
            details=details,
        )

    if not settings.metadata_root.is_dir():
        return PluginHealthStatus(
            healthy=False,
            reason="Metadata root is not a directory",
            details=details,
        )

    return PluginHealthStatus(healthy=True, reason="Versioning ready", details=details)


register_plugin(
    IntegrationPlugin(
        name="versioning",
        category="storage",
        factory=lambda ctx: build_versioning_manager(),
        config_schema=PluginConfigSchema(
            feature_flags=("VERSIONING_ENABLED",),
            environment_variables=("VERSIONING_METADATA_ROOT", "VERSIONING_STRATEGY"),
            description="Persist dataset manifests and reproduce commands for curated outputs.",
        ),
        health_probe=_versioning_health_probe,
        summary="Versioning manager for curated datasets",
    )
)


__all__ = [
    "VersionInfo",
    "VersioningManager",
    "build_versioning_manager",
    "fingerprint_dataframe",
]
