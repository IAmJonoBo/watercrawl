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
DEFAULT_BLOCKERS_PATH = Path("presets/dependency_blockers.toml")
DEFAULT_STATUS_PATH = Path("tools/dependency_matrix/status.json")


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


@dataclass(frozen=True)
class BlockerExpectation:
    package: str
    targets: tuple[str, ...]
    owner: str | None = None
    issue: str | None = None
    notes: str | None = None


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


def load_blockers(config_path: Path) -> tuple[BlockerExpectation, ...]:
    if not config_path.exists():
        raise FileNotFoundError(f"Dependency blocker config not found: {config_path}")
    raw_config = tomllib.loads(config_path.read_text())
    raw_blockers = raw_config.get("blockers")
    if not raw_blockers:
        raise ValueError("No dependency blockers defined in configuration.")
    blockers: list[BlockerExpectation] = []
    for entry in raw_blockers:
        package = entry.get("package")
        targets = tuple(entry.get("targets", ()))
        if not package or not targets:
            raise ValueError("Each dependency blocker must define a package and targets.")
        owner = entry.get("owner")
        issue = entry.get("issue")
        notes = entry.get("notes")
        blockers.append(
            BlockerExpectation(
                package=package,
                targets=targets,
                owner=owner,
                issue=issue,
                notes=notes,
            )
        )
    return tuple(blockers)


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


def evaluate_blockers(
    results: dict[str, list[dict[str, str]]],
    blockers: Iterable[BlockerExpectation],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    blocker_status: list[dict[str, object]] = []
    cleared: list[dict[str, object]] = []
    unexpected: list[dict[str, object]] = []
    blockers_by_target: dict[str, set[str]] = {}
    for blocker in blockers:
        for target in blocker.targets:
            blockers_by_target.setdefault(target, set()).add(blocker.package)

    for blocker in blockers:
        target_statuses: list[dict[str, object]] = []
        present = False
        for target in blocker.targets:
            issues = {issue["package"]: issue for issue in results.get(target, [])}
            issue = issues.get(blocker.package)
            if issue:
                present = True
                target_statuses.append(
                    {
                        "python": target,
                        "status": "present",
                        "reason": issue.get("reason"),
                        "details": issue.get("details"),
                    }
                )
            else:
                target_statuses.append(
                    {
                        "python": target,
                        "status": "cleared",
                        "reason": None,
                        "details": None,
                    }
                )
        payload = {
            "package": blocker.package,
            "owner": blocker.owner,
            "issue": blocker.issue,
            "notes": blocker.notes,
            "targets": target_statuses,
        }
        blocker_status.append(payload)
        if not present:
            cleared.append(payload)

    for python_version, issues in results.items():
        allowed = blockers_by_target.get(python_version, set())
        for issue in issues:
            if issue["package"] not in allowed:
                unexpected.append({"python": python_version, **issue})

    return blocker_status, cleared, unexpected


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

    guard_parser = subparsers.add_parser(
        "guard",
        help="Ensure wheel blockers match the curated allow-list and emit status metadata.",
    )
    guard_parser.add_argument(
        "--lock",
        type=Path,
        default=LOCK_PATH,
        help=f"Path to poetry.lock (default: {LOCK_PATH})",
    )
    guard_parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Dependency target config (default: {DEFAULT_CONFIG_PATH})",
    )
    guard_parser.add_argument(
        "--blockers",
        type=Path,
        default=DEFAULT_BLOCKERS_PATH,
        help=f"Dependency blocker allow-list (default: {DEFAULT_BLOCKERS_PATH})",
    )
    guard_parser.add_argument(
        "--status-output",
        type=Path,
        default=DEFAULT_STATUS_PATH,
        help=f"Write blocker status JSON to this path (default: {DEFAULT_STATUS_PATH})",
    )
    guard_parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Fail if an expected blocker clears without updating the allow-list. "
            "When unset, only unexpected blockers trigger a failure."
        ),
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


def handle_guard(args: argparse.Namespace) -> int:
    targets = load_targets(args.config)
    packages = load_packages(args.lock)
    results = survey(packages, targets)
    blockers = load_blockers(args.blockers)
    blocker_status, cleared, unexpected = evaluate_blockers(results, blockers)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "blockers": blocker_status,
        "cleared": cleared,
        "unexpected": unexpected,
    }
    status_path: Path = args.status_output
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    if unexpected:
        print("Unexpected wheel blockers detected:")
        for issue in unexpected:
            print(
                "  - {package} ({python}): {reason} -> {details}".format(
                    package=issue["package"],
                    python=issue["python"],
                    reason=issue.get("reason", "unknown"),
                    details=issue.get("details", ""),
                )
            )
        return 1
    if args.strict and cleared:
        print("Allow-listed blockers have cleared; update the configuration:")
        for entry in cleared:
            print(f"  - {entry['package']}")
        return 1

    for entry in blocker_status:
        target_messages = []
        for status in entry["targets"]:
            message = f"{status['python']}: {status['status']}"
            if status["status"] == "present" and status.get("reason"):
                message += f" ({status['reason']})"
            target_messages.append(message)
        owner = f" [{entry['owner']}]" if entry.get("owner") else ""
        print(f"{entry['package']}{owner} -> {', '.join(target_messages)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.command == "survey":
        return handle_survey(args)
    if args.command == "guard":
        return handle_guard(args)
    parser.print_help()
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
