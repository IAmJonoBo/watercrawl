#!/bin/bash
# Aggregate all linter/type errors into problems_report.json for ephemeral runners/Codex
set -e

poetry run python scripts/collect_problems.py
