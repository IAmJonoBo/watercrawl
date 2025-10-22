# Linting and Formatting Pipeline Improvements

This document describes the recent improvements to the linting and formatting pipeline in the watercrawl repository.

## Overview

The problems reporting and autofix pipeline has been significantly enhanced to provide:
- Better handling of missing tools in ephemeral environments
- Improved performance through early availability detection
- Actionable autofix commands for supported tools
- Human-readable summary output
- Dedicated autofix helper script

## Key Improvements

### 1. Tool Availability Detection

The `collect_problems.py` script now checks if tools are available before attempting to run them:

```python
def _check_tool_available(tool_name: str) -> bool:
    """Check if a tool is available in PATH or as a Python module."""
```

This provides:
- Faster execution by skipping unavailable tools early
- Clear error messages indicating which tools need installation
- Setup guidance in the problems report

### 2. Enhanced Problems Report

The problems report now includes:

- **Setup Guidance**: Clear instructions for installing missing tools
- **Performance Metrics**: Execution time for each tool and total duration
- **Tools Status**: Lists of tools run successfully, not available, or missing
- **Actionable Autofix Commands**: Pre-formatted commands for fixing issues

Example summary output:

```
======================================================================
PROBLEMS REPORT SUMMARY
======================================================================

Issues found: 0

Tools executed successfully: yamllint, biome

Tools not available (need installation): ruff, mypy, bandit

Optional tools missing: black, isort, trunk

----------------------------------------------------------------------
SETUP GUIDANCE
----------------------------------------------------------------------

Issue: Required QA tools not available
Tools affected: ruff, mypy, bandit
Solution: Install dependencies with: poetry install --no-root --with dev
Alternative: Or use Python directly: python3 -m pip install ruff mypy black isort bandit yamllint

Total execution time: 1.88s

======================================================================
Full report: problems_report.json
======================================================================
```

### 3. New Autofix Helper Script

A dedicated autofix script (`scripts/autofix.py`) simplifies running autofix commands:

```bash
# Run all autofix tools
python3 scripts/autofix.py

# Run a specific tool
python3 scripts/autofix.py ruff

# Use poetry prefix for tools
python3 scripts/autofix.py --poetry

# Dry run to see what would be executed
python3 scripts/autofix.py --dry-run
```

Supported tools:
- `ruff`: Fix auto-fixable linting issues
- `black`: Format code
- `isort`: Sort imports
- `biome`: Fix JavaScript/TypeScript issues
- `trunk`: Format code with trunk
- `all`: Run all available tools (default)

### 4. New Parsers

Added parsers for `black` and `isort` to properly detect formatting issues:

- `parse_black_output()`: Detects files that need reformatting
- `parse_isort_output()`: Detects files with unsorted imports

### 5. Enhanced Autofix Support

All Python formatting tools now have multiple autofix command variants:
- Poetry-prefixed commands for managed environments
- Direct commands for system installations

Example:
```python
autofix=(
    ("poetry", "run", "black", "."),
    ("black", "."),
)
```

## Usage

### Running the Problems Collector

```bash
# Basic usage (works without Poetry)
python3 scripts/collect_problems.py

# With summary output
python3 scripts/collect_problems.py --summary

# With Poetry
poetry run python scripts/collect_problems.py --summary

# Using the shell wrapper (adds --summary by default)
./scripts/collect_problems.sh
```

### Running Autofixes

```bash
# Check what would be fixed (dry run)
python3 scripts/autofix.py --dry-run

# Fix all issues with available tools
python3 scripts/autofix.py

# Fix issues with a specific tool
python3 scripts/autofix.py ruff

# Use Poetry-managed tools
python3 scripts/autofix.py --poetry
```

### Integration with CI/CD

The improved pipeline is designed to work well in both local and ephemeral CI environments:

1. Tools are checked for availability before execution
2. Missing tools don't cause hard failures for optional tools
3. Performance metrics help identify bottlenecks
4. Clear setup guidance helps developers get started quickly

## Testing

New test coverage includes:

- Tool availability checking (`test_check_tool_available`)
- Black and isort parsers (`test_black_parser_*`, `test_isort_parser_*`)
- Tools not available tracking (`test_summary_includes_tools_not_available`)
- Autofix script functionality (`tests/test_autofix.py`)

Run tests with:
```bash
poetry run pytest tests/test_collect_problems.py tests/test_autofix.py -v
```

## Files Modified

- `scripts/collect_problems.py`: Enhanced with availability checking, new parsers, and summary output
- `scripts/collect_problems.sh`: Updated to show summary by default
- `docker-compose.yml`: Fixed trailing spaces (yamllint)
- `mkdocs.yml`: Fixed trailing spaces (yamllint)
- `.github/copilot-instructions.md`: Updated with new commands and workflow

## Files Added

- `scripts/autofix.py`: New autofix helper script
- `scripts/autofix.sh`: Shell wrapper for autofix script
- `tests/test_autofix.py`: Tests for autofix functionality

## Benefits

1. **Faster Development**: Quick identification and fixing of issues
2. **Better CI Experience**: Clear guidance when tools are missing
3. **Improved Performance**: Early detection of unavailable tools
4. **Better Documentation**: Human-readable summaries and clear error messages
5. **Easier Onboarding**: Setup guidance helps new developers get started

## Future Enhancements

Potential improvements for future iterations:

- Add autofix support for yamllint
- Parallel execution of independent tools
- Caching of tool availability checks
- Integration with pre-commit hooks
- IDE-specific output formats
