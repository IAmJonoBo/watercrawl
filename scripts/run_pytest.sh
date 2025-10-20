#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY_ARGS=("$@")

_run_with_python() {
	local python_bin="$1"
	shift
	if [[ -x $python_bin ]]; then
		exec "$python_bin" -m pytest "$@"
	fi
}

# Prefer the Poetry-managed interpreter for the project (Python 3.14.x)
if command -v poetry >/dev/null 2>&1; then
	if POETRY_ENV_PATH="$(poetry env info --path 2>/dev/null)"; then
		if [[ -n $POETRY_ENV_PATH ]]; then
			_run_with_python "$POETRY_ENV_PATH/bin/python" "${PY_ARGS[@]}"
		fi
	fi
fi

# Fallback to the uv toolchain if Poetry env is not yet provisioned
if command -v uv >/dev/null 2>&1; then
	if UV_PYTHON="$(uv python find 3.14 2>/dev/null)"; then
		if [[ -n $UV_PYTHON ]]; then
			_run_with_python "$UV_PYTHON" "${PY_ARGS[@]}"
		fi
	fi
fi

cat <<'EOF' >&2
error: unable to locate a Python 3.14 interpreter for pytest.
Run 'poetry install' (or 'python -m scripts.bootstrap_env') to provision the environment,
then re-run scripts/run_pytest.sh.
EOF
exit 1
