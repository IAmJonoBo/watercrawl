"""Utility for validating wheel contents against the Poetry exclude list."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class PackagingRules:
    """Captured wheel expectations derived from ``pyproject.toml``."""

    disallowed_prefixes: tuple[str, ...]
    disallowed_files: tuple[str, ...]


@dataclass(frozen=True)
class ProjectMetadata:
    """Lightweight view over Poetry project metadata."""

    name: str
    version: str
    package_dirs: tuple[str, ...]

    @property
    def distribution_name(self) -> str:
        return self.name.replace("-", "_")

    @property
    def dist_info_directory(self) -> str:
        return f"{self.distribution_name}-{self.version}.dist-info"


def _load_pyproject() -> dict[str, object]:
    pyproject = PROJECT_ROOT / "pyproject.toml"
    with pyproject.open("rb") as handle:
        return tomllib.load(handle)


def _extract_project_metadata(data: dict[str, object]) -> ProjectMetadata:
    poetry = data["tool"]["poetry"]  # type: ignore[index]
    packages = tuple(
        str(entry["include"])  # type: ignore[index]
        for entry in poetry.get("packages", ())  # type: ignore[call-arg]
        if "include" in entry
    )
    if not packages:
        raise SystemExit(
            "pyproject.toml must declare at least one Poetry package include"
        )
    return ProjectMetadata(
        name=str(poetry["name"]),
        version=str(poetry["version"]),
        package_dirs=packages,
    )


def _normalise_exclude(entry: str) -> str:
    return entry.replace("\\", "/").lstrip("./")


def _extract_packaging_rules(data: dict[str, object]) -> PackagingRules:
    poetry = data["tool"]["poetry"]  # type: ignore[index]
    excludes = tuple(_normalise_exclude(str(item)) for item in poetry.get("exclude", ()))  # type: ignore[call-arg]

    prefixes: list[str] = []
    files: list[str] = []

    for raw in excludes:
        candidate = PROJECT_ROOT / raw
        if candidate.exists():
            if candidate.is_dir():
                prefixes.append(f"{raw.rstrip('/')}/")
            else:
                files.append(raw)
            continue

        suffix = Path(raw).suffix
        if suffix:
            files.append(raw)
        else:
            prefixes.append(f"{raw.rstrip('/')}/")

    unique_prefixes = tuple(dict.fromkeys(sorted(prefixes)))
    unique_files = tuple(dict.fromkeys(sorted(files)))
    return PackagingRules(unique_prefixes, unique_files)


PROJECT_DATA = _load_pyproject()
PROJECT_METADATA = _extract_project_metadata(PROJECT_DATA)
PACKAGING_RULES = _extract_packaging_rules(PROJECT_DATA)

ALLOWED_ROOT_NAMES: tuple[str, ...] = (
    *PROJECT_METADATA.package_dirs,
    PROJECT_METADATA.dist_info_directory,
)


def _build_wheel(destination: Path) -> Path:
    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                str(PROJECT_ROOT),
                "-w",
                str(destination),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (
        subprocess.CalledProcessError
    ) as error:  # pragma: no cover - depends on toolchain
        message = error.stderr or error.stdout or "unknown build failure"
        raise SystemExit(f"Wheel build failed: {message.strip()}") from error
    wheels = list(destination.glob("*.whl"))
    if not wheels:
        raise RuntimeError("Wheel build produced no artifacts")
    return wheels[0]


def _wheel_members(wheel_path: Path) -> tuple[str, ...]:
    with ZipFile(wheel_path) as archive:
        return tuple(archive.namelist())


def collect_wheel_members() -> tuple[str, ...]:
    with tempfile.TemporaryDirectory() as tmp:
        wheel_path = _build_wheel(Path(tmp))
        return _wheel_members(wheel_path)


def find_offending_entries(
    members: Iterable[str], rules: PackagingRules | None = None
) -> set[str]:
    selected_rules = rules or PACKAGING_RULES
    offending = {
        name
        for name in members
        if any(name.startswith(prefix) for prefix in selected_rules.disallowed_prefixes)
    }
    offending.update(
        name for name in members if name in selected_rules.disallowed_files
    )
    return offending


def find_offending_members(wheel_path: Path) -> set[str]:
    members = _wheel_members(wheel_path)
    return find_offending_entries(members)


def validate_wheel() -> set[str]:
    members = collect_wheel_members()
    return find_offending_entries(members)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    offending = validate_wheel()
    if offending:
        formatted = "\n".join(sorted(offending))
        raise SystemExit(
            "Non-packaged directories leaked into the wheel:\n" f"{formatted}"
        )


if __name__ == "__main__":
    main()
