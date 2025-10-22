#!/bin/bash
# Convenience wrapper for autofix.py script
set -euo pipefail

python3 scripts/autofix.py "$@"
