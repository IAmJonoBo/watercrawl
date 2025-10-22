#!/bin/bash
# Aggregate all linter/type errors into problems_report.json for ephemeral runners/Codex
# Note: The collect_problems.py script now automatically configures MYPYPATH to include
# repository stubs (stubs/ and stubs/third_party/), making it suitable for ephemeral
# runners without requiring manual stub configuration.
set -euo pipefail

# Add --summary by default if no arguments provided or if not already present
if [[ $# -eq 0 ]] || [[ ! "$*" =~ --summary ]]; then
    poetry run python scripts/collect_problems.py "$@" --summary
else
    poetry run python scripts/collect_problems.py "$@"
fi
