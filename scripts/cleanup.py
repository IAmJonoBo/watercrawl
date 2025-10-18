"""Automation helpers for cleaning repository artefacts.

This module centralises removal of build and QA artefacts so local runs mirror
CI behaviour. It guards against accidental deletion outside the repository
root and supports dry runs for safety-critical environments.
"""

from __future__ import annotations

import argparse
import shutil
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from firecrawl_demo.core import config

# Default paths that routinely accumulate during local QA runs. Paths are
# expressed relative to the repository root.
_DEFAULT_TARGETS: tuple[str, ...] = (
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "artifacts",
    "data/contracts",
    "data/versioning",
    "dist",
)


@dataclass(frozen=True)
class CleanupResult:
    """Summary of the cleanup operation."""

    removed: tuple[Path, ...]
    skipped: tuple[Path, ...]
    dry_run: bool


def _normalise_target(root: Path, target: str) -> Path:
    """Resolve *target* under *root* and reject paths that escape the repo."""

    candidate = (root / target).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:  # pragma: no cover - defensive path
        raise ValueError(
            f"Cleanup target {candidate} is outside project root {root}"  # noqa: EM102
        ) from exc
    return candidate


def cleanup(
    *,
    project_root: Path | None = None,
    include: Iterable[str] | None = None,
    dry_run: bool = False,
) -> CleanupResult:
    """Remove QA artefacts under *project_root*.

    Parameters
    ----------
    project_root:
        Repository root. Defaults to :data:`config.PROJECT_ROOT`.
    include:
        Optional iterable of additional relative paths to remove.
    dry_run:
        When ``True`` the function only reports what *would* be removed.
    """

    root = (project_root or config.PROJECT_ROOT).resolve()
    targets = list(_DEFAULT_TARGETS)
    if include:
        targets.extend(include)

    removed: list[Path] = []
    skipped: list[Path] = []

    for target in dict.fromkeys(targets):
        path = _normalise_target(root, target)
        if not path.exists():
            skipped.append(path)
            continue
        removed.append(path)
        if dry_run:
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    return CleanupResult(tuple(removed), tuple(skipped), dry_run)


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Clean QA artefacts from the repo")
    parser.add_argument(
        "--include",
        nargs="*",
        default=(),
        help="Additional relative paths to remove",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print targets without deleting them",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_argument_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    result = cleanup(include=args.include, dry_run=args.dry_run)
    for path in result.removed:
        action = "would remove" if result.dry_run else "removed"
        print(f"{action}: {path.relative_to(config.PROJECT_ROOT)}")
    for path in result.skipped:
        print(f"skipped (missing): {path.relative_to(config.PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
