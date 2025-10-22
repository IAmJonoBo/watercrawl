"""Utilities to ensure optional CLI dependencies are available for hooks."""

from __future__ import annotations

import os
import platform
import shutil
import ssl
import stat
import subprocess
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import BinaryIO

CACHE_ROOT = Path.home() / ".cache" / "watercrawl" / "bin"
# Bundled binaries directory for offline/ephemeral environments
BUNDLED_BIN_ROOT = Path(__file__).parent.parent / "bin"


class BootstrapError(RuntimeError):
    """Raised when a CLI binary cannot be prepared."""


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() != "https":
        raise BootstrapError(f"Refusing to download from non-HTTPS URL: {url}")

    contexts: list[ssl.SSLContext | None] = [None]
    # Use public API to create a context; when skipping SSL verification we
    # create a context with hostname checks disabled. This avoids accessing
    # private members like ssl._create_unverified_context.
    unverified = ssl.create_default_context()
    unverified.check_hostname = False
    unverified.verify_mode = ssl.CERT_NONE
    if os.getenv("WATERCRAWL_BOOTSTRAP_SKIP_SSL"):
        contexts.insert(0, unverified)
    else:
        contexts.append(unverified)

    last_ssl_error: ssl.SSLError | None = None
    for context in contexts:
        try:
            with urllib.request.urlopen(url, context=context) as response:  # nosec B310
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

    # Check for bundled binary first (for offline/ephemeral environments)
    skip_bundled = os.getenv("WATERCRAWL_BOOTSTRAP_SKIP_BUNDLED")
    bundled_path = BUNDLED_BIN_ROOT / binary_name
    if not skip_bundled and bundled_path.exists():
        return bundled_path

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
            binary_name = "actionlint-macos-arm64"
            archive_name = f"actionlint_{version.lstrip('v')}_darwin_arm64.tar.gz"
        else:
            binary_name = "actionlint-macos-x86_64"
            archive_name = f"actionlint_{version.lstrip('v')}_darwin_amd64.tar.gz"
    elif system == "linux":
        if machine == "aarch64":
            binary_name = "actionlint-linux-arm64"
            archive_name = f"actionlint_{version.lstrip('v')}_linux_arm64.tar.gz"
        else:
            binary_name = "actionlint-linux-x86_64"
            archive_name = f"actionlint_{version.lstrip('v')}_linux_amd64.tar.gz"
    else:
        raise BootstrapError(f"Unsupported platform: {system} {machine}")

    # Check for bundled binary first (for offline/ephemeral environments)
    skip_bundled = os.getenv("WATERCRAWL_BOOTSTRAP_SKIP_BUNDLED")
    bundled_path = BUNDLED_BIN_ROOT / binary_name
    if not skip_bundled and bundled_path.exists():
        return bundled_path

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


def ensure_nodejs(version: str = "v20.10.0") -> Path:
    """Ensure a Node.js binary is available and return its path.

    The function will prefer a bundled binary in `tools/bin/` (for offline use)
    unless `WATERCRAWL_BOOTSTRAP_SKIP_BUNDLED` is set. It caches downloads under
    `~/.cache/watercrawl/bin/node-<version>-<system>-<machine>/bin/node`.
    """

    override = os.getenv("NODEJS_PATH")
    if override:
        return Path(override)

    system = platform.system().lower()
    machine = platform.machine().lower()

    # Map machine to Node distribution arch labels
    if machine in ("x86_64", "amd64"):
        arch = "x64"
    elif machine in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        raise BootstrapError(f"Unsupported architecture for NodeJS: {machine}")

    if system == "darwin":
        platform_label = "darwin"
    elif system == "linux":
        platform_label = "linux"
    else:
        raise BootstrapError(f"Unsupported platform for NodeJS: {system} {machine}")

    # Check for bundled binary first (for offline/ephemeral environments)
    skip_bundled = os.getenv("WATERCRAWL_BOOTSTRAP_SKIP_BUNDLED")
    bundled_dir = BUNDLED_BIN_ROOT
    bundled_node = bundled_dir / f"node-{platform_label}-{arch}"
    # Some projects may include a pre-extracted node binary location
    if not skip_bundled and bundled_node.exists():
        node_path = bundled_node / "bin" / "node"
        if node_path.exists():
            return node_path

    ver = version.lstrip("v")
    archive_name = f"node-v{ver}-{platform_label}-{arch}.tar.xz"
    url = f"https://nodejs.org/dist/v{ver}/{archive_name}"

    target_dir = CACHE_ROOT / f"node-v{ver}-{platform_label}-{arch}"
    node_target = target_dir / "bin" / "node"
    if node_target.exists():
        return node_target

    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        with tempfile.NamedTemporaryFile(suffix=".tar.xz", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        _download(url, tmp_path)
        try:
            # Extract only the node binary from the archive
            with tarfile.open(tmp_path) as archive:
                member = next(
                    (
                        entry
                        for entry in archive.getmembers()
                        if entry.isfile() and entry.name.endswith("/bin/node")
                    ),
                    None,
                )
                if member is None:
                    raise BootstrapError("Node archive did not contain a node binary")

                member_path = Path(member.name)
                if member_path.is_absolute() or any(
                    part == ".." for part in member_path.parts
                ):
                    raise BootstrapError(
                        "Node archive member resolves outside extraction directory"
                    )

                # Extract the member into a temporary location then move into place
                with tempfile.TemporaryDirectory() as td:
                    archive.extract(member, path=td)
                    extracted = Path(td) / member_path
                    final_bin_dir = target_dir / "bin"
                    final_bin_dir.mkdir(parents=True, exist_ok=True)
                    # Some archives include a prefix directory, so ensure correct rename
                    extracted.rename(final_bin_dir / "node")
                    (final_bin_dir / "node").chmod(
                        (final_bin_dir / "node").stat().st_mode | stat.S_IEXEC
                    )
        finally:
            tmp_path.unlink(missing_ok=True)
    except OSError as exc:  # pragma: no cover - network/runtime failures
        raise BootstrapError(f"Failed to download or extract Node.js: {exc}") from exc

    return node_target


def locate_vendor_wheel(package_name: str, version: str) -> Path | None:
    """Return the path to a vendored wheel for package_name==version if present.

    Looks under repository `tools/vendor/<package_name>/<version>/` for a file
    ending with `.whl` and returns the first match. Returns None if not found.
    """
    repo_root = Path(__file__).parent.parent.parent
    vendor_dir = repo_root / "tools" / "vendor" / package_name / version
    if not vendor_dir.exists():
        return None
    for p in vendor_dir.iterdir():
        if p.is_file() and p.suffix == ".whl":
            return p
    return None


def install_wheel_into_env(wheel_path: Path, python_executable: str = "python") -> None:
    """Install a wheel into the specified Python environment using pip.

    This uses subprocess to call `python -m pip install <wheel>` so it's
    compatible with virtual environments. Raises BootstrapError on failure.
    """
    if not wheel_path.exists():
        raise BootstrapError(f"Wheel not found: {wheel_path}")
    cmd = [python_executable, "-m", "pip", "install", "--no-deps", str(wheel_path)]
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError as exc:
        raise BootstrapError(f"Failed to install wheel {wheel_path}: {exc}") from exc


def ensure_python_package(
    package_name: str,
    version: str | None = None,
    python_executable: str = "python",
    allow_network: bool = True,
) -> None:
    """Ensure a python package is available in the current environment.

    Strategy:
    1. If a vendored wheel exists under tools/vendor/<package>/<version>/, install it.
    2. If WHEELHOUSE_URL is set, try to download and extract a wheelhouse archive and use it.
    3. As a last resort (if allow_network=True), call pip install package[==version].

    Raises BootstrapError if the package cannot be installed.
    """
    # 1) Try vendored wheel
    if version:
        wheel = locate_vendor_wheel(package_name, version)
        if wheel is not None:
            install_wheel_into_env(wheel, python_executable=python_executable)
            return

    # 2) Try WHEELHOUSE_URL (expects a tar.gz or zip of a directory containing wheels)
    wheelhouse_url = os.getenv("WHEELHOUSE_URL")
    if wheelhouse_url:
        try:
            # download to cache and extract
            dest = CACHE_ROOT / "external_wheelhouse"
            dest.mkdir(parents=True, exist_ok=True)
            archive = dest / "wheelhouse_archive"
            _download(wheelhouse_url, archive)

            # Try extracting common formats safely
            def _safe_extract_tar(tar_obj: tarfile.TarFile, path: Path) -> None:
                for member in tar_obj.getmembers():
                    member_path = Path(path) / member.name
                    if not str(member_path.resolve()).startswith(str(path.resolve())):
                        raise BootstrapError(
                            "Tar archive contains path outside extraction directory"
                        )
                tar_obj.extractall(path=path)

            def _safe_extract_zip(zf, path: Path) -> None:
                for member in zf.namelist():
                    member_path = Path(path) / member
                    if not str(member_path.resolve()).startswith(str(path.resolve())):
                        raise BootstrapError(
                            "Zip archive contains path outside extraction directory"
                        )
                zf.extractall(path=path)

            try:
                with tarfile.open(archive) as tar:
                    _safe_extract_tar(tar, dest)
            except tarfile.ReadError:
                # try zip
                import zipfile

                with zipfile.ZipFile(archive) as z:
                    _safe_extract_zip(z, dest)

            # Look for wheel
            for p in dest.rglob("*.whl"):
                install_wheel_into_env(p, python_executable=python_executable)
                return
        except Exception as exc:  # pragma: no cover - network/runtime
            # fall through to network install if allowed
            if not allow_network:
                raise BootstrapError(
                    f"Failed to use wheelhouse at {wheelhouse_url}: {exc}"
                ) from exc

    # 3) Fallback to network pip install
    if not allow_network:
        raise BootstrapError(
            f"No vendored wheel found for {package_name}=={version} and network installs are disabled"
        )

    # Build pip install command
    pkg = package_name if not version else f"{package_name}=={version}"
    cmd = [python_executable, "-m", "pip", "install", pkg]
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError as exc:
        raise BootstrapError(f"Failed to pip install {pkg}: {exc}") from exc
