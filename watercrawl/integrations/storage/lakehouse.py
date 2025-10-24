"""Lakehouse storage integration for Watercrawl.

Provides local and Delta Lake-backed snapshotting, manifest generation, and restoration
for curated datasets, supporting modular plugin registration and evidence-backed data lineage.
"""

from __future__ import annotations

import hashlib
import json
import warnings
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:  # pragma: no cover - optional dependency for tests
    import pandas as pd

    _PANDAS_AVAILABLE = True
except ImportError:  # pragma: no cover - fallback when pandas absent
    pd = None  # type: ignore
    _PANDAS_AVAILABLE = False

try:  # pragma: no cover - optional dependency for Delta Lake support
    from deltalake import DeltaTable, write_deltalake  # type: ignore

    _DELTA_AVAILABLE = True
except ImportError:  # pragma: no cover - delta backend optional
    DeltaTable = None  # type: ignore
    write_deltalake = None  # type: ignore
    _DELTA_AVAILABLE = False

from watercrawl.core import config
from watercrawl.integrations.integration_plugins import (
    IntegrationPlugin,
    PluginConfigSchema,
    PluginContext,
    PluginHealthStatus,
    register_plugin,
)

DELTA_BACKEND = {"delta", "deltalake"}
ICEBERG_BACKEND = {"iceberg"}


def _ensure_pandas() -> None:
    if not _PANDAS_AVAILABLE:
        raise RuntimeError(
            "pandas is required for lakehouse snapshot operations. "
            "Install the UI dependency group or add pandas to your environment."
        )


def _normalize_dataframe(dataframe: Any) -> Any:
    if not _PANDAS_AVAILABLE or not hasattr(dataframe, "reset_index"):
        return dataframe
    return dataframe.reset_index(drop=True).reindex(
        sorted(dataframe.columns), axis=1
    )  # type: ignore[attr-defined]


def _fingerprint_dataframe(dataframe: Any) -> str:
    normalized = _normalize_dataframe(dataframe)
    if _PANDAS_AVAILABLE and hasattr(normalized, "to_csv"):
        payload = normalized.to_csv(index=False)  # type: ignore[call-arg]
    else:  # pragma: no cover - defensive guard
        payload = json.dumps(normalized, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
    degraded: bool = False
    remediation: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)


class LocalLakehouseWriter:
    """Persist curated tables locally, supporting Delta-style commits when available."""

    def __init__(self, config_: LakehouseConfig | None = None) -> None:
        self._config = config_ or LakehouseConfig()

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
                degraded=False,
                remediation=None,
            )

        backend = self._config.backend.lower()
        if backend in DELTA_BACKEND:
            if _DELTA_AVAILABLE:
                return self._write_delta_snapshot(run_id=run_id, dataframe=dataframe)
            warnings.warn(
                "Lakehouse backend 'delta' selected but the 'deltalake' package is not "
                "installed. Falling back to filesystem snapshots.",
                stacklevel=2,
            )
            return self._write_filesystem_snapshot(
                run_id=run_id,
                dataframe=dataframe,
                degrade_reason="delta_engine_missing",
                remediation=(
                    "Install the lakehouse dependency group "
                    "(`poetry install --with lakehouse`) to enable native Delta Lake snapshots."
                ),
            )

        if backend in ICEBERG_BACKEND:
            warnings.warn(
                "Iceberg backend selected but no Iceberg engine is available. "
                "Falling back to filesystem snapshots.",
                stacklevel=2,
            )
            return self._write_filesystem_snapshot(
                run_id=run_id,
                dataframe=dataframe,
                degrade_reason="iceberg_engine_missing",
                remediation="Provide a PyIceberg-compatible runtime to enable Iceberg snapshots.",
            )

        return self._write_filesystem_snapshot(run_id=run_id, dataframe=dataframe)

    def _table_directory(self) -> Path:
        return self._config.root_path / self._config.table_name

    def _write_delta_snapshot(self, run_id: str, dataframe: Any) -> LakehouseManifest:
        _ensure_pandas()
        table_root = self._table_directory()
        table_root.mkdir(parents=True, exist_ok=True)

        normalized = _normalize_dataframe(dataframe)
        fingerprint = _fingerprint_dataframe(normalized)
        row_count = int(len(normalized)) if _PANDAS_AVAILABLE else 0

        write_deltalake(  # type: ignore[misc]
            table_root.as_posix(),
            normalized,
            mode="overwrite",
            schema_mode="overwrite",
        )
        table = DeltaTable(table_root.as_posix())  # type: ignore[misc]
        version_number = table.version()
        version_str = str(version_number)
        history_entries = table.history(1)
        history_entry = history_entries[0] if history_entries else {}
        history_payload = json.loads(json.dumps(history_entry, default=str))

        manifest_payload = {
            "backend": "delta",
            "table": self._config.table_name,
            "version": version_str,
            "run_id": run_id,
            "artifacts": {
                "data": "_delta_log",
                "format": "delta",
            },
            "created_at": datetime.now(UTC).isoformat(),
            "fingerprint": fingerprint,
            "row_count": row_count,
            "delta": {
                "table_path": table_root.as_posix(),
                "version": version_number,
                "history": history_payload,
            },
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

        manifest_path = table_root / f"manifest_v{version_str}.json"
        manifest_path.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True))

        table_uri = f"delta://{table_root.resolve().as_posix()}"
        extras = {
            "delta_version": version_number,
            "delta_table": table_root.resolve().as_posix(),
            "delta_commit": history_payload,
        }
        return LakehouseManifest(
            table_uri=table_uri,
            table_path=table_root,
            manifest_path=manifest_path,
            format="delta",
            version=version_str,
            fingerprint=fingerprint,
            row_count=row_count,
            degraded=False,
            remediation=None,
            extras=extras,
        )

    def _write_filesystem_snapshot(
        self,
        *,
        run_id: str,
        dataframe: Any,
        degrade_reason: str | None = None,
        remediation: str | None = None,
    ) -> LakehouseManifest:
        _ensure_pandas()

        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        version = f"{timestamp}-{run_id}"
        table_dir = self._table_directory() / version
        table_dir.mkdir(parents=True, exist_ok=True)

        normalized = _normalize_dataframe(dataframe)
        fingerprint = _fingerprint_dataframe(normalized)
        row_count = int(len(normalized)) if _PANDAS_AVAILABLE else 0

        storage_format = "parquet"
        data_path = table_dir / "data.parquet"
        degraded = False
        parquet_error: Exception | None = None
        try:
            normalized.to_parquet(data_path, index=False)  # type: ignore[call-arg]
        except (ImportError, ValueError) as error:
            degraded = True
            storage_format = "csv"
            parquet_error = error
            data_path = table_dir / "data.csv"
            csv_message = (
                "Parquet export requires an installed pandas parquet engine such as "
                "'pyarrow' or 'fastparquet'. Falling back to CSV output at "
                f"{data_path.name}."
            )
            warnings.warn(csv_message, stacklevel=2)
            normalized.to_csv(data_path, index=False)  # type: ignore[call-arg]
            if remediation is None:
                remediation = csv_message

        manifest_payload: dict[str, Any] = {
            "backend": self._config.backend,
            "table": self._config.table_name,
            "version": version,
            "run_id": run_id,
            "artifacts": {
                "data": data_path.name,
                "format": storage_format,
            },
            "created_at": datetime.now(UTC).isoformat(),
            "fingerprint": fingerprint,
            "row_count": row_count,
            "schema": (
                {column: str(dtype) for column, dtype in normalized.dtypes.items()}
                if _PANDAS_AVAILABLE
                else {}
            ),
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

        if degraded or degrade_reason:
            reason = degrade_reason or "parquet_engine_missing"
            remediation_msg = remediation or (
                "Install 'pyarrow' or 'fastparquet' and rerun the lakehouse writer "
                "to generate parquet snapshots."
            )
            manifest_payload.setdefault("warnings", []).append(remediation_msg)
            manifest_payload["artifacts"]["degraded"] = {
                "reason": reason,
                "remediation": remediation_msg,
                "fallback_artifact": data_path.name,
            }
            if parquet_error is not None:
                manifest_payload["artifacts"]["degraded"]["exception"] = str(
                    parquet_error
                )

        manifest_path = table_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True))

        table_uri = f"{self._config.backend}://{table_dir.resolve().as_posix()}"
        extras: dict[str, Any] = {}
        if degrade_reason:
            extras["degraded_reason"] = degrade_reason
        return LakehouseManifest(
            table_uri=table_uri,
            table_path=table_dir,
            manifest_path=manifest_path,
            format=storage_format,
            version=version,
            fingerprint=fingerprint,
            row_count=row_count,
            degraded=bool(degrade_reason or degraded),
            remediation=remediation,
            extras=extras,
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

    if settings.backend.lower() in DELTA_BACKEND and not _DELTA_AVAILABLE:
        return PluginHealthStatus(
            healthy=False,
            reason="Delta backend requested but 'deltalake' package is missing",
            details=details,
        )

    return PluginHealthStatus(healthy=True, reason="Lakehouse ready", details=details)


def _resolve_table_path(
    *,
    table_name: str,
    root_path: Path | None = None,
    backend: str | None = None,
) -> tuple[str, Path, str]:
    cfg = LakehouseConfig()
    resolved_backend = (backend or cfg.backend).lower()
    resolved_root = (root_path or cfg.root_path).resolve()
    table_root = resolved_root / table_name
    if resolved_backend in DELTA_BACKEND:
        return resolved_backend, table_root, f"delta://{table_root.as_posix()}"
    return resolved_backend, table_root, f"{resolved_backend}://{table_root.as_posix()}"


def restore_snapshot(
    *,
    table_name: str | None = None,
    version: str | int | None = None,
    root_path: Path | None = None,
    backend: str | None = None,
) -> Any:
    """Return a dataframe for the requested snapshot (latest when version is None)."""

    table = table_name or LakehouseConfig().table_name
    resolved_backend, table_root, _ = _resolve_table_path(
        table_name=table, root_path=root_path, backend=backend
    )

    if resolved_backend in DELTA_BACKEND:
        if not _DELTA_AVAILABLE:
            raise RuntimeError(
                "Delta Lake support requires the 'deltalake' package. "
                "Install it with `poetry install --with lakehouse`."
            )
        _ensure_pandas()
        kwargs: dict[str, Any] = {}
        if version is not None:
            kwargs["version"] = int(version)
        table_instance = DeltaTable(table_root.as_posix(), **kwargs)  # type: ignore[misc]
        return table_instance.to_pandas()  # type: ignore[no-any-return]

    snapshot_dir: Path
    if version is None:
        if not table_root.exists():
            raise FileNotFoundError(
                f"No snapshots found for table '{table}'. Expected directory {table_root}."
            )
        candidates = sorted(
            (path for path in table_root.iterdir() if path.is_dir()),
            key=lambda item: item.name,
        )
        if not candidates:
            raise FileNotFoundError(
                f"No snapshots found for table '{table}'. Expected directory {table_root}."
            )
        snapshot_dir = candidates[-1]
    else:
        snapshot_dir = table_root / str(version)
        if not snapshot_dir.exists():
            raise FileNotFoundError(
                f"Snapshot '{version}' not found for table '{table}'. "
                f"Checked {snapshot_dir}."
            )

    _ensure_pandas()
    parquet_path = snapshot_dir / "data.parquet"
    if parquet_path.exists():
        return pd.read_parquet(parquet_path)  # type: ignore[no-any-return]
    csv_path = snapshot_dir / "data.csv"
    if csv_path.exists():
        return pd.read_csv(csv_path)  # type: ignore[no-any-return]
    raise FileNotFoundError(
        f"No data artifact found for snapshot '{snapshot_dir}'. "
        "Expected 'data.parquet' or 'data.csv'."
    )


def restore_snapshot_to_path(
    *,
    output_path: Path,
    table_name: str | None = None,
    version: str | int | None = None,
    root_path: Path | None = None,
    backend: str | None = None,
) -> Path:
    """Restore a snapshot and persist it to *output_path*."""

    dataframe = restore_snapshot(
        table_name=table_name, version=version, root_path=root_path, backend=backend
    )
    _ensure_pandas()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() == ".parquet":
        dataframe.to_parquet(output_path, index=False)  # type: ignore[call-arg]
    else:
        dataframe.to_csv(output_path, index=False)  # type: ignore[call-arg]
    return output_path


register_plugin(
    IntegrationPlugin(
        name="lakehouse",
        category="storage",
        factory=lambda ctx: build_lakehouse_writer(),
        config_schema=PluginConfigSchema(
            feature_flags=("LAKEHOUSE_ENABLED",),
            environment_variables=(
                "LAKEHOUSE_ROOT",
                "LAKEHOUSE_TABLE_NAME",
                "LAKEHOUSE_BACKEND",
            ),
            optional_dependencies=("pandas", "deltalake"),
            description=(
                "Persist curated datasets to local lakehouse storage with optional "
                "Delta Lake support."
            ),
        ),
        health_probe=_lakehouse_health_probe,
        summary="Lakehouse writer supporting filesystem or Delta backends",
    )
)


__all__ = [
    "LakehouseConfig",
    "LakehouseManifest",
    "LocalLakehouseWriter",
    "build_lakehouse_writer",
    "restore_snapshot",
    "restore_snapshot_to_path",
]
