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
