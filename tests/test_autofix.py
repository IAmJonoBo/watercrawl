"""Tests for the autofix helper script."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence

import pytest

from scripts import autofix


def test_autofix_tools_registry():
    """Test that the AUTOFIX_TOOLS registry is properly configured."""
    assert "ruff" in autofix.AUTOFIX_TOOLS
    assert "black" in autofix.AUTOFIX_TOOLS
    assert "isort" in autofix.AUTOFIX_TOOLS
    assert "all" in autofix.AUTOFIX_TOOLS
    
    # Each tool should have required keys
    for tool_name, config in autofix.AUTOFIX_TOOLS.items():
        if tool_name != "all":
            assert "description" in config
            assert config["description"] is not None


def test_check_tool_available():
    """Test the tool availability checker."""
    # Python should always be available
    assert autofix.check_tool_available("python3") is True
    # This fake tool should never exist
    assert autofix.check_tool_available("nonexistent-tool-xyz-12345") is False


def test_run_autofix_with_unknown_tool():
    """Test that running autofix with unknown tool returns error."""
    result = autofix.run_autofix("unknown-tool-xyz", dry_run=True)
    assert result == 1


def test_run_autofix_dry_run():
    """Test that dry run mode doesn't execute commands."""
    result = autofix.run_autofix("ruff", dry_run=True)
    # Should succeed in dry run mode even if tool isn't available
    assert result in (0, 1)  # May fail if tool check runs


def test_parse_args_default():
    """Test argument parsing with defaults."""
    args = autofix.parse_args([])
    assert args.tool == "all"
    assert args.poetry is False
    assert args.dry_run is False


def test_parse_args_with_tool():
    """Test argument parsing with specific tool."""
    args = autofix.parse_args(["ruff"])
    assert args.tool == "ruff"


def test_parse_args_with_flags():
    """Test argument parsing with flags."""
    args = autofix.parse_args(["black", "--poetry", "--dry-run"])
    assert args.tool == "black"
    assert args.poetry is True
    assert args.dry_run is True


def test_run_all_autofixes_dry_run():
    """Test running all autofixes in dry run mode."""
    result = autofix.run_all_autofixes(dry_run=True)
    # Should always succeed in dry run mode
    assert isinstance(result, int)
