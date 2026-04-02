"""Tests for _load_credentials environment variable handling."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest


class TestLoadCredentialsEnvPriority:
    """Verify _load_credentials respects pre-set environment variables."""

    def test_shell_env_not_overwritten_by_config_file(self, monkeypatch, tmp_path):
        """Environment variables set before _load_credentials must survive."""
        from platform_context_graph.cli.main import _load_credentials

        # Pre-set a variable the user would pass via shell
        monkeypatch.setenv("PCG_COMMIT_WORKERS", "2")

        # Create a config file that tries to set the same var to a different value
        env_file = tmp_path / ".env"
        env_file.write_text("PCG_COMMIT_WORKERS=1\n")

        with (
            patch(
                "platform_context_graph.cli.main.get_app_env_file",
                return_value=env_file,
            ),
            patch(
                "platform_context_graph.cli.main.find_dotenv",
                return_value="",
            ),
        ):
            _load_credentials()

        assert os.environ["PCG_COMMIT_WORKERS"] == "2"

    def test_config_file_sets_absent_vars(self, monkeypatch, tmp_path):
        """Config file values should be applied when not already in env."""
        from platform_context_graph.cli.main import _load_credentials

        monkeypatch.delenv("PCG_SOME_NEW_VAR", raising=False)

        env_file = tmp_path / ".env"
        env_file.write_text("PCG_SOME_NEW_VAR=from_config\n")

        with (
            patch(
                "platform_context_graph.cli.main.get_app_env_file",
                return_value=env_file,
            ),
            patch(
                "platform_context_graph.cli.main.find_dotenv",
                return_value="",
            ),
        ):
            _load_credentials()

        assert os.environ.get("PCG_SOME_NEW_VAR") == "from_config"
        # Clean up
        monkeypatch.delenv("PCG_SOME_NEW_VAR", raising=False)

    def test_database_type_shell_preserved(self, monkeypatch, tmp_path):
        """DATABASE_TYPE set in shell must not be overwritten."""
        from platform_context_graph.cli.main import _load_credentials

        monkeypatch.setenv("DATABASE_TYPE", "neo4j")

        env_file = tmp_path / ".env"
        env_file.write_text("DATABASE_TYPE=sqlite\n")

        with (
            patch(
                "platform_context_graph.cli.main.get_app_env_file",
                return_value=env_file,
            ),
            patch(
                "platform_context_graph.cli.main.find_dotenv",
                return_value="",
            ),
        ):
            _load_credentials()

        assert os.environ["DATABASE_TYPE"] == "neo4j"
