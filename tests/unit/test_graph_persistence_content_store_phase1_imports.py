"""Phase 1 import-compat tests for graph persistence content-store helpers."""

from __future__ import annotations

import inspect

from platform_context_graph.graph.persistence.content_store import (
    content_dual_write,
    content_dual_write_batch,
)
from platform_context_graph.tools.graph_builder_persistence import (
    _content_dual_write,
    _content_dual_write_batch,
)


def test_content_dual_write_canonical_module_is_graph_persistence() -> None:
    """Canonical content dual-write helper should live under graph.persistence."""

    assert (
        content_dual_write.__module__
        == "platform_context_graph.graph.persistence.content_store"
    )


def test_legacy_content_dual_write_batch_keeps_batch_size_parameter() -> None:
    """Legacy wrapper should preserve the batch-size override parameter."""

    canonical_params = inspect.signature(content_dual_write_batch).parameters
    legacy_params = inspect.signature(_content_dual_write_batch).parameters

    assert "content_batch_size" in canonical_params
    assert "content_batch_size" in legacy_params


def test_legacy_content_dual_write_wrapper_remains_callable() -> None:
    """Legacy tools helper should remain importable during the transition."""

    assert callable(_content_dual_write)
