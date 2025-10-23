"""Audit PyPI wheels for tracked dependency blockers."""

from __future__ import annotations

import argparse
import atexit
import json
import os
import ssl
import sys
import tempfile
import time
import tomllib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import certifi
import requests
from packaging.specifiers import SpecifierSet
from requests.adapters import HTTPAdapter
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning

DEFAULT_BLOCKERS_PATH = Path("presets/dependency_blockers.toml")
DEFAULT_OUTPUT_PATH = Path("tools/dependency_matrix/wheel_status.json")
PYPI_URL_TEMPLATE = "https://pypi.org/pypi/{package}/json"
REQUEST_TIMEOUT = 15


def _build_trust_store() -> tuple[ssl.SSLContext, str | None]:
    candidates = [
        os.environ.get("PIP_CERT"),
        os.environ.get("REQUESTS_CA_BUNDLE"),
        os.environ.get("SSL_CERT_FILE"),
        certifi.where(),
    ]
    paths: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        try:
            if not path.exists():
                continue
        except OSError:
            continue
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)

    if not paths:
        context = ssl.create_default_context()
        return context, None
    if len(paths) == 1:
        cafile = str(paths[0])
        return ssl.create_default_context(cafile=cafile), cafile

    handle = tempfile.NamedTemporaryFile(delete=False, suffix="-wheel-status-ca.pem")
    with handle as merged:
        for ca_path in paths:
            data = ca_path.read_bytes()
            merged.write(data)
            if not data.endswith(b"\n"):
                merged.write(b"\n")
    merged_path = Path(handle.name)
    atexit.register(lambda path=merged_path: path.unlink(missing_ok=True))
    return ssl.create_default_context(cafile=handle.name), handle.name


class TLSAdapter(HTTPAdapter):
    """HTTPAdapter that enforces the custom SSL context."""

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        pool_kwargs["ssl_context"] = SSL_CONTEXT
        super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)


SSL_CONTEXT, CA_BUNDLE = _build_trust_store()
SESSION = requests.Session()
SESSION.mount("https://", TLSAdapter())


@dataclass(frozen=True)
class Blocker:
    package: str
    targets: tuple[str, ...]
    owner: str | None
    issue: str | None
    notes: str | None


@dataclass(frozen=True)
class WheelCheck:
    status: str
    message: str


def load_blockers(path: Path) -> tuple[Blocker, ...]:
    if not path.exists():
        raise FileNotFoundError(f"Dependency blocker file not found: {path}")
    data = tomllib.loads(path.read_text())
    raw_blockers = data.get("blockers")
    if not isinstance(raw_blockers, Iterable):
        raise ValueError(
            "Dependency blocker configuration must contain a 'blockers' array"
        )
    blockers: list[Blocker] = []
    for entry in raw_blockers:
        if not isinstance(entry, Mapping):
            continue
        package = entry.get("package")
        if not isinstance(package, str):
            continue
        targets_raw = entry.get("targets", ())
        if not isinstance(targets_raw, Iterable):
            continue
        targets = tuple(str(target) for target in targets_raw)
        if not targets:
            continue
        blockers.append(
            Blocker(
                package=package,
                targets=targets,
                owner=str(entry.get("owner")) if entry.get("owner") else None,
                issue=str(entry.get("issue")) if entry.get("issue") else None,
                notes=str(entry.get("notes")) if entry.get("notes") else None,
            )
        )
    return tuple(blockers)


def fetch_package_metadata(package: str) -> tuple[dict[str, Any], bool]:
    url = PYPI_URL_TEMPLATE.format(package=package)
    used_insecure = False
    try:
        response = SESSION.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.text
    except requests.exceptions.SSLError:
        used_insecure = True
        disable_warnings(InsecureRequestWarning)
        insecure_response = requests.get(url, timeout=REQUEST_TIMEOUT, verify=False)
        insecure_response.raise_for_status()
        payload = insecure_response.text
    except requests.HTTPError as exc:  # pragma: no cover - network failure
        raise RuntimeError(
            f"Failed to fetch metadata for {package}: HTTP {exc.response.status_code}"
        ) from exc
    except requests.RequestException as exc:  # pragma: no cover - network failure
        raise RuntimeError(
            f"Failed to fetch metadata for {package}: {exc}. "
            "If this is a TLS error, ensure certifi is installed and reachable."
        ) from exc
    return json.loads(payload), used_insecure


def _supports_python(spec: str | None, target: str) -> bool:
    if not spec:
        return True
    try:
        spec_set = SpecifierSet(spec)
    except ValueError:
        return True
    return spec_set.contains(target, prereleases=True)


def _wheel_matches(file_info: Mapping[str, Any], target: str) -> bool:
    if file_info.get("packagetype") != "bdist_wheel":
        return False
    if file_info.get("yanked"):
        return False
    python_tag = file_info.get("python_version")
    if not isinstance(python_tag, str):
        return False
    major, _, minor = target.partition(".")
    cp_tag = f"cp{major}{minor}"
    if python_tag == "py3" or python_tag.startswith("py3"):
        return True
    if python_tag.startswith(f"py{major}"):
        return True
    if python_tag.startswith(cp_tag):
        return True
    if python_tag.startswith("cp3") and python_tag.endswith("abi3"):
        # abi3 wheels are compatible across minor versions >= the compiled version.
        compiled_minor = python_tag[4:]
        if compiled_minor.isdigit() and int(compiled_minor) <= int(minor):
            return True
    return False


def evaluate_package(
    package: Blocker,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    info = metadata.get("info", {})
    version = info.get("version") or "unknown"
    requires_python = info.get("requires_python")
    releases = metadata.get("releases", {})
    release_files = releases.get(version, []) if isinstance(releases, Mapping) else []
    results: dict[str, WheelCheck] = {}
    for target in package.targets:
        if not _supports_python(requires_python, target):
            results[target] = WheelCheck(
                status="python-spec",
                message=f"Requires-Python '{requires_python}' excludes {target}",
            )
            continue
        supported = any(
            isinstance(entry, Mapping) and _wheel_matches(entry, target)
            for entry in release_files
        )
        if supported:
            results[target] = WheelCheck(status="ok", message="Wheel available")
        else:
            results[target] = WheelCheck(
                status="missing-wheel", message=f"No wheel for Python {target}"
            )
    resolved = all(check.status == "ok" for check in results.values())
    return {
        "package": package.package,
        "owner": package.owner,
        "issue": package.issue,
        "notes": package.notes,
        "latest_version": version,
        "requires_python": requires_python,
        "targets": {target: check.__dict__ for target, check in results.items()},
        "resolved": resolved,
    }


def generate_status(
    blockers: Iterable[Blocker],
    fetcher: Callable[[str], Mapping[str, Any]],
) -> dict[str, Any]:
    packages = []
    unresolved = 0
    for blocker in blockers:
        metadata, insecure = fetcher(blocker.package)
        record = evaluate_package(blocker, metadata)
        if insecure:
            record["tls_warning"] = True
        if not record["resolved"]:
            unresolved += 1
        packages.append(record)
        time.sleep(0.1)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "packages": packages,
        "unresolved_count": unresolved,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report wheel availability for dependency blockers."
    )
    parser.add_argument(
        "--blockers",
        type=Path,
        default=DEFAULT_BLOCKERS_PATH,
        help="Path to dependency blockers TOML (default: presets/dependency_blockers.toml)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Where to write the status JSON (default: tools/dependency_matrix/wheel_status.json)",
    )
    parser.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="Return non-zero when unresolved blockers remain.",
    )
    args = parser.parse_args(argv)

    blockers = load_blockers(args.blockers)

    def _fetch(pkg: str) -> Mapping[str, Any]:
        return fetch_package_metadata(pkg)

    status = generate_status(blockers, _fetch)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(status, indent=2, sort_keys=True), encoding="utf-8"
    )

    if args.fail_on_missing and status.get("unresolved_count"):
        print(
            f"[wheel-status] {status['unresolved_count']} blocker(s) still missing wheels",  # type: ignore[index]
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
