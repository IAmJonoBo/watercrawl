#!/usr/bin/env bash
# Helper to run dev tools with local stubs available via MYPYPATH
# Usage: ./scripts/run_with_stubs.sh [--] <command> [args...]

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STUBS_PATH="${REPO_ROOT}/stubs"

if [[ ! -d $STUBS_PATH ]]; then
	echo "No stubs directory found at $STUBS_PATH" >&2
	exit 1
fi

usage() {
	cat <<'USAGE'
Usage: run_with_stubs.sh [--] <command> [args...]

If no command is provided the script runs:
  poetry run mypy . --show-error-codes --no-error-summary

Examples:
  ./scripts/run_with_stubs.sh poetry run pytest -q
  ./scripts/run_with_stubs.sh -- python -m scripts.vscode_problems_helper --help

This script prepends the repository-local `stubs/` directory to MYPYPATH so
that type-checkers and language servers can see fallback type stubs.
USAGE
}

# Print usage on -h/--help
if [ "${1-}" = "-h" ] || [ "${1-}" = "--help" ]; then
	usage
	exit 0
fi

# allow an explicit `--` to separate flags from the command
if [ "${1-}" = "--" ]; then
	shift
fi

# Prepend stubs to MYPYPATH so type-checkers and language servers can find them
export MYPYPATH="$STUBS_PATH${MYPYPATH:+:$MYPYPATH}"

if [ "$#" -eq 0 ]; then
	# default: run mypy via poetry
	echo "Running: poetry run mypy . (with MYPYPATH=$MYPYPATH)"
	exec poetry run mypy . --show-error-codes --no-error-summary
else
	echo "Running: $* (with MYPYPATH=$MYPYPATH)"
	exec "$@"
fi
