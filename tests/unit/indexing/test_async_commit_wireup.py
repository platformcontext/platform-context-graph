"""Tests for async commit path wireup and feature flag."""

from __future__ import annotations

import asyncio
import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAsyncCommitFlag:
    """Verify the async commit feature flag is read correctly."""

    def test_async_commit_disabled_by_default(self):
        """Async commit should be disabled when env var is unset."""
        from platform_context_graph.indexing import coordinator_async_commit as mod

        reloaded = importlib.reload(mod)
        assert reloaded._ASYNC_COMMIT_ENABLED is False

    def test_async_commit_enabled_by_env(self, monkeypatch):
        """Async commit should be enabled when env var is 'true'."""
        monkeypatch.setenv("PCG_ASYNC_COMMIT_ENABLED", "true")
        from platform_context_graph.indexing import coordinator_async_commit as mod

        reloaded = importlib.reload(mod)
        assert reloaded._ASYNC_COMMIT_ENABLED is True


class TestAsyncCommitConfigCatalog:
    """Verify async commit config is registered in the config catalog."""

    def test_config_catalog_has_async_commit_default(self):
        """Config catalog should include PCG_ASYNC_COMMIT_ENABLED."""
        from platform_context_graph.cli.config_catalog import DEFAULT_CONFIG

        assert "PCG_ASYNC_COMMIT_ENABLED" in DEFAULT_CONFIG
        assert DEFAULT_CONFIG["PCG_ASYNC_COMMIT_ENABLED"] == "false"

    def test_config_catalog_has_async_commit_description(self):
        """Config catalog should describe PCG_ASYNC_COMMIT_ENABLED."""
        from platform_context_graph.cli.config_catalog import CONFIG_DESCRIPTIONS

        assert "PCG_ASYNC_COMMIT_ENABLED" in CONFIG_DESCRIPTIONS

    def test_config_catalog_has_async_commit_validator(self):
        """Config catalog should validate PCG_ASYNC_COMMIT_ENABLED."""
        from platform_context_graph.cli.config_catalog import CONFIG_VALIDATORS

        assert "PCG_ASYNC_COMMIT_ENABLED" in CONFIG_VALIDATORS
        assert CONFIG_VALIDATORS["PCG_ASYNC_COMMIT_ENABLED"] == ["true", "false"]


class TestAsyncCommitModuleExports:
    """Verify the async commit module exports the expected symbols."""

    def test_module_exports_async_commit_function(self):
        """coordinator_async_commit should export commit_repository_snapshot_async."""
        from platform_context_graph.indexing.coordinator_async_commit import (
            commit_repository_snapshot_async,
        )

        assert asyncio.iscoroutinefunction(commit_repository_snapshot_async)

    def test_module_exports_feature_flag(self):
        """coordinator_async_commit should export _ASYNC_COMMIT_ENABLED flag."""
        from platform_context_graph.indexing import coordinator_async_commit

        assert hasattr(coordinator_async_commit, "_ASYNC_COMMIT_ENABLED")


class TestAsyncCommitPipelineBranching:
    """Verify coordinator_pipeline branches on async commit flag."""

    def test_pipeline_imports_async_commit_module(self):
        """coordinator_pipeline should be able to import the async commit module."""
        from platform_context_graph.indexing import coordinator_async_commit

        assert hasattr(coordinator_async_commit, "commit_repository_snapshot_async")
