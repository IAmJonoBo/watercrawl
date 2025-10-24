#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY_ARGS=("$@")
PIPELINE_EXTRA="pipeline"

_ensure_pipeline_extra() {
        if ! command -v poetry >/dev/null 2>&1; then
                return
        fi

        if poetry run python - <<'PY' >/dev/null 2>&1; then
import importlib
import sys

try:
    importlib.import_module("marshmallow")
except Exception:
    sys.exit(1)
PY
		return
	fi

	echo "Installing Poetry extra '${PIPELINE_EXTRA}' for pipeline tests" >&2
	if poetry install --with dev --extras "${PIPELINE_EXTRA}" --sync >/dev/null 2>&1; then
		return
	fi

        echo "Poetry install failed; attempting vendored install via scripts/ensure_deps.py" >&2
        poetry run python "${REPO_ROOT}/scripts/ensure_deps.py"
}

_ensure_pipeline_extra

_ensure_pipeline_extra_for_interpreter() {
        local python_bin="$1"

        if [[ -z ${python_bin} || ! -x ${python_bin} ]]; then
                return
        fi

        if "${python_bin}" - <<'PY' >/dev/null 2>&1; then
import importlib
import sys

try:
    importlib.import_module("marshmallow")
except Exception:
    sys.exit(1)
PY
                return
        fi

        echo "Installing pipeline dependencies for fallback interpreter '${python_bin}'" >&2
        if command -v uv >/dev/null 2>&1; then
                if uv pip install --python "${python_bin}" --quiet "marshmallow<4" >/dev/null 2>&1; then
                        return
                fi
        fi

        echo "uv pip install failed; attempting vendored install via scripts/ensure_deps.py" >&2
        "${python_bin}" "${REPO_ROOT}/scripts/ensure_deps.py"
}

_run_with_python() {
	local python_bin="$1"
	shift
	if [[ -x ${python_bin} ]]; then
		exec "${python_bin}" -m pytest "$@"
	fi
}

# Prefer the Poetry-managed interpreter for the project (Python 3.13.x)
if command -v poetry >/dev/null 2>&1; then
	if POETRY_ENV_PATH="$(poetry env info --path 2>/dev/null)"; then
		if [[ -n ${POETRY_ENV_PATH} ]]; then
			_run_with_python "${POETRY_ENV_PATH}/bin/python" "${PY_ARGS[@]}"
		fi
	fi
fi

# Fallback to the uv toolchain if Poetry env is not yet provisioned
if command -v uv >/dev/null 2>&1; then
        if UV_PYTHON="$(uv python find 3.13 2>/dev/null)"; then
                if [[ -n ${UV_PYTHON} ]]; then
                        _ensure_pipeline_extra_for_interpreter "${UV_PYTHON}"
                        _run_with_python "${UV_PYTHON}" "${PY_ARGS[@]}"
                fi
        fi
fi

cat <<'EOF' >&2
error: unable to locate a Python 3.13 interpreter for pytest.
Run 'poetry install' (or 'python -m scripts.bootstrap_env') to provision the environment,
then re-run scripts/run_pytest.sh.
EOF
exit 1
