"""Utilities to ensure optional CLI dependencies are available for hooks."""

from __future__ import annotations

import os
import ssl
import stat
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional

CACHE_ROOT = Path.home() / ".cache" / "watercrawl" / "bin"


class BootstrapError(RuntimeError):
    """Raised when a CLI binary cannot be prepared."""


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    contexts: list[Optional[ssl.SSLContext]] = [None]
    if os.getenv("WATERCRAWL_BOOTSTRAP_SKIP_SSL"):
        contexts.insert(0, ssl._create_unverified_context())
    for context in contexts:
        try:
            with urllib.request.urlopen(url, context=context) as response, destination.open(
                "wb"
            ) as target:
                target.write(response.read())
            return
        except Exception as exc:  # pragma: no cover - network/runtime failures
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, ssl.SSLError):
                continue
            raise
    with urllib.request.urlopen(url, context=ssl._create_unverified_context()) as response, destination.open(
        "wb"
    ) as target:
        target.write(response.read())


def ensure_hadolint(version: str = "v2.14.0") -> Path:
    """Ensure the hadolint binary is available and return its path."""

    override = os.getenv("HADOLINT_PATH")
    if override:
        return Path(override)

    target = CACHE_ROOT / f"hadolint-{version}"
    if not target.exists():
        url = (
            "https://github.com/hadolint/hadolint/releases/download/"
            f"{version}/hadolint-Linux-x86_64"
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

    tag = version.lstrip("v")
    archive_url = (
        "https://github.com/rhysd/actionlint/releases/download/"
        f"{version}/actionlint_{tag}_linux_amd64.tar.gz"
    )
    extract_dir = CACHE_ROOT / f"actionlint-{version}"
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
                archive.extract(member, path=extract_dir)
                extracted = extract_dir / member.name
                extracted.chmod(extracted.stat().st_mode | stat.S_IEXEC)
                if extracted != binary_path:
                    extracted.rename(binary_path)
        finally:
            tmp_path.unlink(missing_ok=True)
    except OSError as exc:  # pragma: no cover - network/runtime failures
        raise BootstrapError(f"Failed to download actionlint: {exc}") from exc
    return binary_path
