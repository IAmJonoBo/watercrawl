"""Provision a Python toolchain compatible with the Watercrawl QA suite."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

DEFAULT_VERSION = "3.14.0"


class BootstrapError(RuntimeError):
    """Raised when provisioning the requested interpreter fails."""


def _run(command: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=check, capture_output=True, text=True)


def _ensure_uv(*, auto_install: bool) -> Path:
    uv_path = shutil.which("uv")
    if uv_path:
        return Path(uv_path)
    if not auto_install:
        raise BootstrapError(
            "The 'uv' CLI is required. Install it with 'pip install uv' or rerun with --install-uv."
        )
    install_cmd = [sys.executable, "-m", "pip", "install", "--user", "uv"]
    result = _run(install_cmd, check=False)
    if result.returncode != 0:
        raise BootstrapError(
            "Failed to install the 'uv' CLI."
            f"\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )
    uv_path = shutil.which("uv")
    if not uv_path:
        raise BootstrapError("The 'uv' CLI could not be located after installation.")
    return Path(uv_path)


def _install_python(uv_path: Path, version: str) -> Path:
    install_cmd = [str(uv_path), "python", "install", version]
    install_result = _run(install_cmd, check=False)
    if install_result.returncode != 0:
        raise BootstrapError(
            "uv failed to install the requested Python interpreter."
            f"\nSTDOUT: {install_result.stdout}\nSTDERR: {install_result.stderr}"
        )
    find_cmd = [str(uv_path), "python", "find", version]
    find_result = _run(find_cmd, check=False)
    if find_result.returncode != 0:
        raise BootstrapError(
            "uv could not locate the installed interpreter."
            f"\nSTDOUT: {find_result.stdout}\nSTDERR: {find_result.stderr}"
        )
    interpreter = Path(find_result.stdout.strip())
    if not interpreter.exists():
        raise BootstrapError(
            f"uv reported interpreter path {interpreter!s}, but the file does not exist."
        )
    return interpreter


def _pin_poetry(interpreter: Path) -> None:
    poetry_cmd = shutil.which("poetry")
    if not poetry_cmd:
        raise BootstrapError("Poetry is required to pin the interpreter but was not found in PATH.")
    result = _run([poetry_cmd, "env", "use", interpreter.as_posix()], check=False)
    if result.returncode != 0:
        raise BootstrapError(
            "Poetry failed to select the uv provisioned interpreter."
            f"\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        default=DEFAULT_VERSION,
        help="Python version to install via uv (default: %(default)s)",
    )
    parser.add_argument(
        "--poetry",
        action="store_true",
        help="Pin Poetry to the installed interpreter for the current project.",
    )
    parser.add_argument(
        "--install-uv",
        action="store_true",
        help="Automatically install the 'uv' CLI using the active Python interpreter.",
    )
    args = parser.parse_args(argv)

    try:
        uv_path = _ensure_uv(auto_install=args.install_uv)
        interpreter = _install_python(uv_path, args.version)
        print(f"uv provisioned Python interpreter at {interpreter}")
        if args.poetry:
            _pin_poetry(interpreter)
            print("Poetry environment pinned to the uv provisioned interpreter.")
    except BootstrapError as exc:  # pragma: no cover - CLI error surface
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
