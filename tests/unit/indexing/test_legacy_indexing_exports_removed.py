"""Guardrails that keep deleted parser-runtime facades out of public exports."""

from __future__ import annotations

import pytest


def test_indexing_package_no_longer_exports_legacy_execution_entrypoints() -> None:
    """The indexing package should not advertise dead coordinator entrypoints."""

    import platform_context_graph.indexing as indexing

    assert not hasattr(indexing, "execute_index_run")
    assert not hasattr(indexing, "raise_for_failed_index_run")
    assert not hasattr(indexing, "IndexExecutionResult")


def test_git_indexing_package_no_longer_exports_legacy_snapshot_parser() -> None:
    """Git collector indexing should expose discovery helpers, not old parse runtime."""

    from platform_context_graph.collectors.git import indexing

    assert not hasattr(indexing, "parse_repository_snapshot_async")
    with pytest.raises(AttributeError):
        getattr(indexing, "parse_repository_snapshot_async")


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
