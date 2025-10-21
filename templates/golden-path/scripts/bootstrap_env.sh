#!/usr/bin/env bash
set -euo pipefail

# Golden-path bootstrap wrapper
python -m scripts.bootstrap_env "$@"
