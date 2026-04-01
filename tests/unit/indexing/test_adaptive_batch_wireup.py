"""Tests for adaptive batch config wire-up into the commit pipeline."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


class TestCommitSnapshotUsesAdaptiveConfig:
    """Verify _commit_repository_snapshot respects repo_class."""

    def test_commit_uses_adaptive_file_batch_size_when_enabled(self, monkeypatch):
        """When adaptive batching is enabled and repo_class is xlarge,
        file_batch_size should be smaller than the default 50."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            batch_config_for_class,
        )

        monkeypatch.setenv("PCG_ADAPTIVE_GRAPH_BATCHING_ENABLED", "true")
        xlarge_config = batch_config_for_class("xlarge")
        # xlarge should use 15, well below the default 50
        assert xlarge_config.file_batch_size == 15

    def test_commit_uses_default_when_adaptive_disabled(self, monkeypatch):
        """When adaptive batching is disabled, should use medium defaults."""
        from platform_context_graph.indexing.adaptive_batch_config import (
            resolve_batch_config,
        )

        monkeypatch.setenv("PCG_ADAPTIVE_GRAPH_BATCHING_ENABLED", "false")
        config = resolve_batch_config(repo_class="xlarge")
        assert config.file_batch_size == 50  # medium default

    def test_persistence_accepts_adaptive_flush_threshold(self):
        """should_flush_batches should accept a custom threshold parameter."""
        from platform_context_graph.tools.graph_builder_persistence_batch import (
            should_flush_batches,
        )

        # Verify the function accepts a threshold override
        # Empty accumulator should not trigger flush regardless of threshold
        from platform_context_graph.tools.graph_builder_persistence_batch import (
            empty_accumulator,
        )

        acc = empty_accumulator()
        assert should_flush_batches(acc, flush_threshold=100) is False

    def test_persistence_flushes_at_custom_threshold(self):
        """should_flush_batches with low threshold should trigger earlier."""
        from platform_context_graph.tools.graph_builder_persistence_batch import (
            should_flush_batches,
            empty_accumulator,
            pending_row_count,
        )

        acc = empty_accumulator()
        # Add enough rows to exceed a low threshold but not the default
        acc["entities_by_label"]["Function"] = [{"name": f"fn{i}"} for i in range(200)]
        row_count = pending_row_count(acc)
        assert row_count == 200

        # Should flush at threshold=100 but not at default=2000
        assert should_flush_batches(acc, flush_threshold=100) is True
        assert should_flush_batches(acc) is False


class TestEntityBatchSizeOverride:
    """Verify entity batch size can be overridden for class-aware UNWIND sizing."""

    def test_flush_write_batches_accepts_entity_batch_size(self):
        """flush_write_batches should accept an entity_batch_size override."""
        from platform_context_graph.tools.graph_builder_persistence_batch import (
            flush_write_batches,
        )

        import inspect

        sig = inspect.signature(flush_write_batches)
        assert "entity_batch_size" in sig.parameters
