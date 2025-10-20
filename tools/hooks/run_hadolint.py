"""Pre-commit entrypoint that bootstraps hadolint on demand."""

from __future__ import annotations

# Bandit: subprocess usage is limited to the downloaded hadolint binary.
import subprocess  # nosec B404
import sys

from .bootstrap import BootstrapError, ensure_hadolint


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    try:
        binary = ensure_hadolint()
    except BootstrapError as exc:
        print(exc, file=sys.stderr)
        return 1
    completed = subprocess.run([str(binary), *args], check=False)  # nosec B603
    return completed.returncode


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
