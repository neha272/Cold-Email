"""Tests for CLI interface."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from cold_emailer.cli import app

runner = CliRunner()


def test_cli_help() -> None:
    """Test that CLI help command works."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "cold-emailer" in result.stdout.lower()


def test_cli_init_db() -> None:
    """Test init-db command."""
    result = runner.invoke(app, ["init-db"])
    # Should exit with 0 (even though not implemented yet)
    assert result.exit_code == 0


def test_cli_ingest_missing_file() -> None:
    """Test ingest command with missing file."""
    result = runner.invoke(app, ["ingest", "--file", "nonexistent.csv"])
    # Should fail because file doesn't exist
    assert result.exit_code != 0


def test_cli_status() -> None:
    """Test status command."""
    result = runner.invoke(app, ["status", "--limit", "10"])
    # Should exit with 0 (even though not implemented yet)
    assert result.exit_code == 0
