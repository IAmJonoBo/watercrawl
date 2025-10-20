"""Offline-friendly dependency audit using the Safety DB JSON."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version


@dataclass(frozen=True)
class RequirementPin:
    """A parsed requirement line with an exact version pin."""

    name: str
    version: Version
    source: Path
    original_line: str


@dataclass(frozen=True)
class Vulnerability:
    """Description of an offline Safety DB match."""

    requirement: RequirementPin
    spec: str
    advisory: str
    identifier: str
    cve: str | None


def _find_safety_db() -> Path:
    for entry in map(Path, sys.path):
        candidate = entry / "safety_db" / "insecure_full.json"
        if candidate.exists():
            return candidate
    msg = "Unable to locate safety_db/insecure_full.json on sys.path. Ensure `safety-db` is installed."
    raise FileNotFoundError(msg)


def _iter_requirement_entries(path: Path) -> Iterable[str]:
    """Yield pip-compatible requirement strings without hash continuation lines."""

    for raw in path.read_text().splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("--hash"):
            continue
        if stripped.endswith("\\"):
            stripped = stripped[:-1].strip()
        yield stripped


def _parse_requirements(path: Path) -> list[RequirementPin]:
    pins: list[RequirementPin] = []
    for entry in _iter_requirement_entries(path):
        try:
            requirement = Requirement(entry)
        except Exception:  # pragma: no cover - packaging raises varied errors
            raise ValueError(
                f"Unable to parse requirement line '{entry}' in {path}."
            ) from None
        exact_spec = next(
            (spec for spec in requirement.specifier if spec.operator == "=="), None
        )
        if not exact_spec:
            continue
        try:
            version = Version(exact_spec.version)
        except InvalidVersion as exc:  # pragma: no cover - surface to caller
            raise ValueError(
                f"Invalid version pin '{exact_spec.version}' for requirement '{requirement.name}' in {path}."
            ) from exc
        pins.append(
            RequirementPin(
                name=requirement.name.lower(),
                version=version,
                source=path,
                original_line=entry,
            )
        )
    return pins


def _load_vulnerability_index(
    path: Path,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    raw_data: Any = json.loads(path.read_text())
    if not isinstance(raw_data, dict):  # pragma: no cover - guards corrupted downloads
        raise TypeError("Expected Safety DB payload to be a JSON object.")
    meta_raw = raw_data.pop("$meta", {}) if "$meta" in raw_data else {}
    meta: dict[str, Any] = meta_raw if isinstance(meta_raw, dict) else {}
    index: dict[str, list[dict[str, Any]]] = {}
    for name, entries in raw_data.items():
        bucket: list[dict[str, Any]] = []
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict):
                    bucket.append(entry)
        index[name.lower()] = bucket
    return index, meta


def _match_vulnerabilities(
    pins: Sequence[RequirementPin],
    index: dict[str, list[dict[str, Any]]],
) -> list[Vulnerability]:
    matches: list[Vulnerability] = []
    for pin in pins:
        candidates = index.get(pin.name, [])
        for payload in candidates:
            specs = payload.get("specs", []) or []
            if isinstance(specs, str):
                specs = [specs]
            advisory = str(payload.get("advisory", ""))
            identifier = str(payload.get("id", ""))
            cve = payload.get("cve")
            for spec in specs:
                try:
                    specifier = SpecifierSet(spec)
                except (
                    Exception
                ):  # pragma: no cover - guard corrupted DB entries  # nosec B112
                    continue
                if pin.version in specifier:
                    matches.append(
                        Vulnerability(
                            requirement=pin,
                            spec=spec,
                            advisory=advisory,
                            identifier=identifier,
                            cve=str(cve) if cve else None,
                        )
                    )
                    break
    return matches


def audit(requirement_paths: Sequence[Path]) -> int:
    db_path = _find_safety_db()
    index, meta = _load_vulnerability_index(db_path)
    pins: list[RequirementPin] = []
    skipped: list[tuple[Path, str]] = []
    for req_path in requirement_paths:
        for pin in _parse_requirements(req_path):
            pins.append(pin)
        # Track skipped lines for observability
        for entry in _iter_requirement_entries(req_path):
            requirement = Requirement(entry)
            if not any(spec.operator == "==" for spec in requirement.specifier):
                skipped.append((req_path, entry))
    matches = _match_vulnerabilities(pins, index)

    timestamp = meta.get("timestamp")
    header = "Offline Safety DB" + (f" snapshot {timestamp}" if timestamp else "")
    print(f"Loaded {header} from {db_path}.")
    print(
        f"Scanned {len(pins)} pinned requirements from {len(requirement_paths)} manifest(s)."
    )
    if skipped:
        print("Skipped the following unpinned or VCS requirements:")
        for req_path, raw in skipped:
            print(f"  - {req_path}: {raw}")
    if not matches:
        print("No known vulnerabilities detected.")
        return 0

    print("Detected the following vulnerabilities:")
    for match in matches:
        ident = match.cve or match.identifier or "UNKNOWN"
        print(
            f"  - {match.requirement.name}=={match.requirement.version} "
            f"(affected by {ident}, spec {match.spec})\n"
            f"    Source: {match.requirement.source} :: {match.requirement.original_line}\n"
            f"    Advisory: {match.advisory}"
        )
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline Safety vulnerability scan")
    parser.add_argument(
        "--requirements",
        dest="requirements",
        action="append",
        type=Path,
        required=True,
        help="Path to a requirements file to audit (can be passed multiple times).",
    )
    args = parser.parse_args(argv)
    for path in args.requirements:
        if not path.exists():
            parser.error(f"Requirements file {path} does not exist.")
    return audit(args.requirements)


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
