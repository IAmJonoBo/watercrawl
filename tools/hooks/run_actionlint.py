"""Pre-commit entrypoint that bootstraps actionlint on demand."""

from __future__ import annotations

import subprocess
import sys

from .bootstrap import BootstrapError, ensure_actionlint


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    try:
        binary = ensure_actionlint()
    except BootstrapError as exc:
        print(exc, file=sys.stderr)
        return 1
    completed = subprocess.run([str(binary), *args], check=False)
    return completed.returncode


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
