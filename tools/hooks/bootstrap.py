"""Utilities to ensure optional CLI dependencies are available for hooks."""

from __future__ import annotations

import os
import platform
import shutil
import ssl
import stat
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import BinaryIO

CACHE_ROOT = Path.home() / ".cache" / "watercrawl" / "bin"


class BootstrapError(RuntimeError):
    """Raised when a CLI binary cannot be prepared."""


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    unverified = ssl._create_unverified_context()
    contexts: list[ssl.SSLContext | None] = [None, unverified]
    if os.getenv("WATERCRAWL_BOOTSTRAP_SKIP_SSL"):
        contexts.reverse()

    last_ssl_error: ssl.SSLError | None = None
    for context in contexts:
        try:
            with urllib.request.urlopen(url, context=context) as response:
                _write_response(response, destination)
            return
        except ssl.SSLError as exc:  # pragma: no cover - depends on host configuration
            last_ssl_error = exc
            continue
        except urllib.error.URLError as exc:
            raise BootstrapError(f"Failed to download {url}: {exc.reason}") from exc
        except OSError as exc:
            raise BootstrapError(f"Failed to download {url}: {exc}") from exc
        except Exception as exc:  # pragma: no cover - unexpected runtime failure
            raise BootstrapError(f"Failed to download {url}: {exc}") from exc

    if last_ssl_error is not None:
        raise BootstrapError(
            f"SSL negotiation failed for {url}: {last_ssl_error}"
        ) from last_ssl_error
    raise BootstrapError(f"Failed to download {url}: unknown error")


def _write_response(response: BinaryIO, destination: Path) -> None:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, dir=destination.parent) as tmp:
            temp_path = Path(tmp.name)
            shutil.copyfileobj(response, tmp)
        temp_path.replace(destination)
    except Exception as exc:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise BootstrapError(
            f"Failed to persist download to {destination}: {exc}"
        ) from exc
    else:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def ensure_hadolint(version: str = "v2.14.0") -> Path:
    """Ensure the hadolint binary is available and return its path."""

    override = os.getenv("HADOLINT_PATH")
    if override:
        return Path(override)

    # Detect platform and architecture
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "darwin":
        if machine == "arm64":
            binary_name = "hadolint-macos-arm64"
        else:
            binary_name = "hadolint-macos-x86_64"
    elif system == "linux":
        if machine == "aarch64":
            binary_name = "hadolint-linux-arm64"
        else:
            binary_name = "hadolint-linux-x86_64"
    else:
        raise BootstrapError(f"Unsupported platform: {system} {machine}")

    target = CACHE_ROOT / f"hadolint-{version}-{system}-{machine}"
    if not target.exists():
        url = (
            "https://github.com/hadolint/hadolint/releases/download/"
            f"{version}/{binary_name}"
        )
        try:
            _download(url, target)
        except OSError as exc:  # pragma: no cover - network/runtime failures
            raise BootstrapError(f"Failed to download hadolint: {exc}") from exc
        target.chmod(target.stat().st_mode | stat.S_IEXEC)
    return target


def ensure_actionlint(version: str = "v1.7.1") -> Path:
    """Ensure the actionlint binary is available and return its path."""

    override = os.getenv("ACTIONLINT_PATH")
    if override:
        return Path(override)

    # Detect platform and architecture
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "darwin":
        if machine == "arm64":
            archive_name = f"actionlint_{version.lstrip('v')}_darwin_arm64.tar.gz"
        else:
            archive_name = f"actionlint_{version.lstrip('v')}_darwin_amd64.tar.gz"
    elif system == "linux":
        if machine == "aarch64":
            archive_name = f"actionlint_{version.lstrip('v')}_linux_arm64.tar.gz"
        else:
            archive_name = f"actionlint_{version.lstrip('v')}_linux_amd64.tar.gz"
    else:
        raise BootstrapError(f"Unsupported platform: {system} {machine}")

    archive_url = (
        "https://github.com/rhysd/actionlint/releases/download/"
        f"{version}/{archive_name}"
    )
    extract_dir = CACHE_ROOT / f"actionlint-{version}-{system}-{machine}"
    binary_path = extract_dir / "actionlint"
    if binary_path.exists():
        return binary_path

    extract_dir.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        _download(archive_url, tmp_path)
        try:
            with tarfile.open(tmp_path) as archive:
                member = next(
                    (
                        entry
                        for entry in archive.getmembers()
                        if entry.isfile() and entry.name.endswith("actionlint")
                    ),
                    None,
                )
                if member is None:
                    raise BootstrapError("actionlint archive did not contain a binary")
                member_path = Path(member.name)
                if member_path.is_absolute() or any(
                    part == ".." for part in member_path.parts
                ):
                    raise BootstrapError(
                        "actionlint archive member resolves outside extraction directory"
                    )
                archive.extract(member, path=extract_dir)
                extracted = extract_dir / member_path
                extracted.chmod(extracted.stat().st_mode | stat.S_IEXEC)
                if extracted != binary_path:
                    extracted.rename(binary_path)
        finally:
            tmp_path.unlink(missing_ok=True)
    except OSError as exc:  # pragma: no cover - network/runtime failures
        raise BootstrapError(f"Failed to download actionlint: {exc}") from exc
    return binary_path
