"""Tests for GIL yield points in graph persistence commits."""

from __future__ import annotations

import importlib
import os

import pytest


class TestGilYieldFlag:
    """Verify the GIL yield feature flag is read correctly."""

    def test_gil_yield_enabled_by_default(self, monkeypatch):
        """GIL yield should be enabled when env var is unset."""
        monkeypatch.delenv("PCG_COMMIT_GIL_YIELD_ENABLED", raising=False)
        import platform_context_graph.graph.persistence.commit as mod

        reloaded = importlib.reload(mod)
        assert reloaded._GIL_YIELD_ENABLED is True

    def test_gil_yield_disabled_by_env(self, monkeypatch):
        """GIL yield should be disabled when env var is 'false'."""
        monkeypatch.setenv("PCG_COMMIT_GIL_YIELD_ENABLED", "false")
        import platform_context_graph.graph.persistence.commit as mod

        reloaded = importlib.reload(mod)
        assert reloaded._GIL_YIELD_ENABLED is False

    def test_gil_yield_enabled_by_explicit_true(self, monkeypatch):
        """GIL yield should be enabled when env var is 'true'."""
        monkeypatch.setenv("PCG_COMMIT_GIL_YIELD_ENABLED", "true")
        import platform_context_graph.graph.persistence.commit as mod

        reloaded = importlib.reload(mod)
        assert reloaded._GIL_YIELD_ENABLED is True


class TestGilYieldConfigCatalog:
    """Verify GIL yield config is registered in the config catalog."""

    def test_config_catalog_has_gil_yield_default(self):
        """Config catalog should include PCG_COMMIT_GIL_YIELD_ENABLED."""
        from platform_context_graph.cli.config_catalog import DEFAULT_CONFIG

        assert "PCG_COMMIT_GIL_YIELD_ENABLED" in DEFAULT_CONFIG
        assert DEFAULT_CONFIG["PCG_COMMIT_GIL_YIELD_ENABLED"] == "true"

    def test_config_catalog_has_gil_yield_description(self):
        """Config catalog should describe PCG_COMMIT_GIL_YIELD_ENABLED."""
        from platform_context_graph.cli.config_catalog import CONFIG_DESCRIPTIONS

        assert "PCG_COMMIT_GIL_YIELD_ENABLED" in CONFIG_DESCRIPTIONS

    def test_config_catalog_has_gil_yield_validator(self):
        """Config catalog should validate PCG_COMMIT_GIL_YIELD_ENABLED."""
        from platform_context_graph.cli.config_catalog import CONFIG_VALIDATORS

        assert "PCG_COMMIT_GIL_YIELD_ENABLED" in CONFIG_VALIDATORS
        assert CONFIG_VALIDATORS["PCG_COMMIT_GIL_YIELD_ENABLED"] == [
            "true",
            "false",
        ]
