"""Dependency compatibility survey and provisioning helpers."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

try:  # pragma: no cover - import fallback for Python <3.11
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[assignment]

from packaging.specifiers import SpecifierSet
from packaging.version import Version

LOCK_PATH = Path("poetry.lock")
DEFAULT_CONFIG_PATH = Path("presets/dependency_targets.toml")
DEFAULT_REPORT_PATH = Path("tools/dependency_matrix/report.json")


@dataclass(frozen=True)
class Target:
    python_version: str
    label: str
    require_wheels: bool = True

    @property
    def version(self) -> Version:
        return Version(self.python_version)


@dataclass(frozen=True)
class PackageFile:
    filename: str
    is_wheel: bool
    python_tag: str | None


@dataclass(frozen=True)
class PackageInfo:
    name: str
    version: str
    groups: tuple[str, ...]
    python_spec: str | None
    files: tuple[PackageFile, ...]

    @property
    def specifier(self) -> SpecifierSet | None:
        if not self.python_spec or self.python_spec.strip() == "*":
            return None
        return SpecifierSet(self.python_spec)


@dataclass(frozen=True)
class Issue:
    package: PackageInfo
    reason: str
    details: str

    def as_dict(self) -> dict[str, str]:
        return {
            "package": self.package.name,
            "version": self.package.version,
            "groups": ",".join(self.package.groups),
            "reason": self.reason,
            "details": self.details,
        }


def load_targets(config_path: Path) -> list[Target]:
    if not config_path.exists():
        raise FileNotFoundError(f"Dependency target config not found: {config_path}")
    data = tomllib.loads(config_path.read_text())
    raw_targets = data.get("targets")
    if not raw_targets:
        raise ValueError("No dependency targets defined in configuration.")
    targets: list[Target] = []
    for entry in raw_targets:
        python_version = entry.get("python")
        label = entry.get("label", python_version)
        require_wheels = bool(entry.get("require_wheels", True))
        if not python_version:
            raise ValueError("Each dependency target must specify a python version.")
        targets.append(Target(python_version=python_version, label=label, require_wheels=require_wheels))
    return targets


def parse_package_files(raw_files: Iterable[dict[str, str]]) -> tuple[PackageFile, ...]:
    files: list[PackageFile] = []
    for entry in raw_files:
        filename = entry.get("file")
        if not filename:
            continue
        is_wheel = filename.endswith(".whl")
        python_tag: str | None = None
        if is_wheel:
            parts = filename[:-4].split("-")
            if len(parts) >= 3:
                python_tag = parts[-3]
        files.append(PackageFile(filename=filename, is_wheel=is_wheel, python_tag=python_tag))
    return tuple(files)


def load_packages(lock_path: Path) -> tuple[PackageInfo, ...]:
    if not lock_path.exists():
        raise FileNotFoundError(f"Poetry lock file not found: {lock_path}")
    lock_data = tomllib.loads(lock_path.read_text())
    package_entries = lock_data.get("package", [])
    packages: list[PackageInfo] = []
    for entry in package_entries:
        name = entry.get("name")
        version = entry.get("version")
        groups = tuple(entry.get("groups", ()))
        python_spec = entry.get("python-versions")
        raw_files = entry.get("files", [])
        package_files = parse_package_files(raw_files)
        if not name or not version:
            continue
        packages.append(
            PackageInfo(
                name=name,
                version=version,
                groups=groups,
                python_spec=python_spec,
                files=package_files,
            )
        )
    return tuple(packages)


def python_tag_supports(python_tag: str | None, target: Target) -> bool:
    if not python_tag:
        return False
    tag = python_tag.lower()
    if tag in {"py3", "py2.py3"}:
        return target.version.major == 3
    if tag.startswith(("py", "cp", "pp")):
        digits = "".join(ch for ch in tag[2:] if ch.isdigit())
        if not digits:
            return False
        major = int(digits[0])
        minor = int(digits[1:]) if len(digits) > 1 else 0
        return major == target.version.major and minor == target.version.minor
    return False


def has_compatible_wheel(package: PackageInfo, target: Target) -> bool:
    for file in package.files:
        if not file.is_wheel:
            continue
        if python_tag_supports(file.python_tag, target):
            return True
        if file.python_tag and file.python_tag.lower().startswith("py3") and target.version.major == 3:
            return True
    return False


def evaluate_package(package: PackageInfo, target: Target) -> Issue | None:
    spec = package.specifier
    if spec and not spec.contains(target.version, prereleases=True):
        return Issue(
            package=package,
            reason="python-spec",
            details=f"Requires python '{package.python_spec}'",
        )
    if target.require_wheels and not has_compatible_wheel(package, target):
        return Issue(
            package=package,
            reason="missing-wheel",
            details=f"No wheel compatible with Python {target.python_version}",
        )
    return None


def survey(packages: Iterable[PackageInfo], targets: Iterable[Target]) -> dict[str, list[dict[str, str]]]:
    results: dict[str, list[dict[str, str]]] = {}
    for target in targets:
        issues: list[dict[str, str]] = []
        for package in packages:
            issue = evaluate_package(package, target)
            if issue:
                issues.append(issue.as_dict())
        results[target.python_version] = issues
    return results


def format_summary(results: dict[str, list[dict[str, str]]], targets: Iterable[Target]) -> str:
    lines = []
    for target in targets:
        issues = results.get(target.python_version, [])
        status = "OK" if not issues else f"{len(issues)} blockers"
        lines.append(f"Python {target.python_version} [{target.label}]: {status}")
        for issue in issues:
            lines.append(
                f"  - {issue['package']}=={issue['version']} ({issue['reason']}): {issue['details']}"
            )
    return "\n".join(lines)


def write_report(results: dict[str, list[dict[str, str]]], path: Path, targets: Iterable[Target]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "targets": [
            {
                "python": target.python_version,
                "label": target.label,
                "require_wheels": target.require_wheels,
                "issues": results.get(target.python_version, []),
            }
            for target in targets
        ],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    survey_parser = subparsers.add_parser("survey", help="Collect compatibility issues for configured Python targets.")
    survey_parser.add_argument(
        "--lock",
        type=Path,
        default=LOCK_PATH,
        help=f"Path to poetry.lock (default: {LOCK_PATH})",
    )
    survey_parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Dependency target config (default: {DEFAULT_CONFIG_PATH})",
    )
    survey_parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help=f"Write JSON report to this path (default: {DEFAULT_REPORT_PATH})",
    )
    survey_parser.add_argument(
        "--fail-on-blockers",
        action="store_true",
        help="Exit with status 1 if any blockers are detected.",
    )
    return parser


def handle_survey(args: argparse.Namespace) -> int:
    targets = load_targets(args.config)
    packages = load_packages(args.lock)
    results = survey(packages, targets)
    write_report(results, args.output, targets)
    print(format_summary(results, targets))
    if args.fail_on_blockers and any(results.values()):
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.command == "survey":
        return handle_survey(args)
    parser.print_help()
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
