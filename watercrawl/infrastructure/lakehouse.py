from __future__ import annotations

import argparse
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

try:  # pragma: no cover - pandas is an optional runtime dependency
    import pandas as pd
except ImportError as exc:  # pragma: no cover - surface clearer error
    raise RuntimeError(
        "pandas is required to use the lakehouse CLI. "
        "Install it via `poetry install --with ui`."
    ) from exc

from watercrawl.integrations.storage.lakehouse import (
    LakehouseConfig,
    LocalLakehouseWriter,
    build_lakehouse_writer,
    restore_snapshot,
    restore_snapshot_to_path,
)


def _read_dataset(source: Path) -> pd.DataFrame:
    suffix = source.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(source)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(source)
    raise ValueError(f"Unsupported source format '{source.suffix}'. Use CSV or XLSX.")


def _build_writer(
    *,
    backend: str | None = None,
    root_path: Path | None = None,
    table_name: str | None = None,
) -> LocalLakehouseWriter:
    writer = build_lakehouse_writer()
    if backend or root_path or table_name:
        cfg = LakehouseConfig()
        writer = LocalLakehouseWriter(
            LakehouseConfig(
                backend=backend or cfg.backend,
                root_path=(root_path or cfg.root_path).resolve(),
                table_name=table_name or cfg.table_name,
                enabled=cfg.enabled,
            )
        )
    if writer is None or not writer.enabled:
        raise RuntimeError("Lakehouse writer is disabled. Set LAKEHOUSE_ENABLED=1.")
    return writer


def command_snapshot(args: argparse.Namespace) -> None:
    writer = _build_writer(
        backend=args.backend, root_path=args.destination, table_name=args.table
    )
    source_path = Path(args.source).resolve()
    frame = _read_dataset(source_path)
    run_id = (
        args.run_id
        or f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
    )
    manifest = writer.write(run_id=run_id, dataframe=frame)
    print(manifest.manifest_path)


def command_restore(args: argparse.Namespace) -> None:
    output_path = Path(args.output).resolve() if args.output else None
    if output_path is not None:
        restored_path = restore_snapshot_to_path(
            output_path=output_path,
            table_name=args.table,
            version=args.version,
            root_path=args.root,
            backend=args.backend,
        )
        print(restored_path)
        return
    dataframe = restore_snapshot(
        table_name=args.table,
        version=args.version,
        root_path=args.root,
        backend=args.backend,
    )
    dataframe.to_csv(sys.stdout, index=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lakehouse utilities for snapshotting and restoring curated datasets."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot_parser = subparsers.add_parser(
        "snapshot", help="Persist a dataset to the configured lakehouse."
    )
    snapshot_parser.add_argument("source", type=str, help="Path to source CSV/XLSX.")
    snapshot_parser.add_argument(
        "--run-id", type=str, help="Run identifier used in manifests."
    )
    snapshot_parser.add_argument(
        "--destination",
        type=Path,
        help="Override the lakehouse root path.",
        dest="destination",
    )
    snapshot_parser.add_argument(
        "--table",
        type=str,
        help="Override the table name defined in configuration.",
    )
    snapshot_parser.add_argument(
        "--backend",
        type=str,
        help="Override the lakehouse backend (e.g., delta).",
    )
    snapshot_parser.set_defaults(func=command_snapshot)

    restore_parser = subparsers.add_parser(
        "restore", help="Restore a snapshot to stdout or a file."
    )
    restore_parser.add_argument(
        "--version",
        type=str,
        help="Snapshot version to restore. Latest when omitted.",
    )
    restore_parser.add_argument(
        "--output",
        type=str,
        help="Destination file for the restored dataset. Prints to stdout when omitted.",
    )
    restore_parser.add_argument(
        "--table",
        type=str,
        help="Table name to restore (defaults to configuration).",
    )
    restore_parser.add_argument(
        "--root",
        type=Path,
        help="Override lakehouse root path for restore operations.",
    )
    restore_parser.add_argument(
        "--backend",
        type=str,
        help="Override backend for restore (e.g., delta).",
    )
    restore_parser.set_defaults(func=command_restore)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    main()
