"""Guardrails that keep deleted parser-runtime facades out of public imports."""

from __future__ import annotations

import importlib

import pytest


def test_indexing_package_no_longer_exports_legacy_execution_entrypoints() -> None:
    """The indexing package should not advertise dead coordinator entrypoints."""

    import platform_context_graph.indexing as indexing

    assert not hasattr(indexing, "execute_index_run")
    assert not hasattr(indexing, "raise_for_failed_index_run")
    assert not hasattr(indexing, "IndexExecutionResult")


def test_git_indexing_package_is_deleted_after_go_cutover() -> None:
    """The old Git indexing shim should disappear once Go owns the path."""

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("platform_context_graph.collectors.git.indexing")


def test_config_catalog_no_longer_advertises_async_commit_toggle() -> None:
    """The Python async-commit feature flag should disappear with the legacy path."""

    from platform_context_graph.cli.config_catalog import (
        CONFIG_DESCRIPTIONS,
        CONFIG_VALIDATORS,
        DEFAULT_CONFIG,
    )

    assert "PCG_ASYNC_COMMIT_ENABLED" not in DEFAULT_CONFIG
    assert "PCG_ASYNC_COMMIT_ENABLED" not in CONFIG_DESCRIPTIONS
    assert "PCG_ASYNC_COMMIT_ENABLED" not in CONFIG_VALIDATORS
