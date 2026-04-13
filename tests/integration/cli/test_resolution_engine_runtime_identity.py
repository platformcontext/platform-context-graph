"""CLI regression coverage for removed Python resolution-engine ownership."""

from __future__ import annotations

from typer.testing import CliRunner

from platform_context_graph.cli.main import app

runner = CliRunner()


def test_internal_resolution_engine_command_is_removed_from_python_cli() -> None:
    """The Python CLI must not expose the resolution-engine service command."""
    result = runner.invoke(app, ["internal", "resolution-engine"])

    assert result.exit_code == 2


def test_internal_help_omits_removed_resolution_engine_command() -> None:
    """Hidden Python help output should no longer list the removed service."""
    result = runner.invoke(app, ["internal", "--help"])

    assert result.exit_code == 0
    assert "resolution-engine" not in result.stdout
