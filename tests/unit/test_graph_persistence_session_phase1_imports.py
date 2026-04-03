"""Phase 1 import-compat tests for graph persistence session helpers."""

from __future__ import annotations

from platform_context_graph.graph.persistence.session import begin_transaction
from platform_context_graph.tools.graph_builder_persistence import _begin_transaction


def test_begin_transaction_canonical_module_is_graph_persistence() -> None:
    """Canonical transaction helper should live under graph.persistence."""

    assert (
        begin_transaction.__module__
        == "platform_context_graph.graph.persistence.session"
    )


def test_legacy_begin_transaction_aliases_canonical_helper() -> None:
    """Legacy import path should keep resolving to the canonical helper."""

    assert _begin_transaction is begin_transaction
