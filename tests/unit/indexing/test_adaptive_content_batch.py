"""Tests for adaptive content batch size wire-up."""

from __future__ import annotations

import inspect

import pytest


class TestContentProviderAcceptsOverride:
    """Verify upsert methods accept entity_batch_size override."""

    def test_upsert_entities_accepts_entity_batch_size(self):
        """upsert_entities should accept an entity_batch_size parameter."""
        from platform_context_graph.content.postgres import PostgresContentProvider

        sig = inspect.signature(PostgresContentProvider.upsert_entities)
        assert "entity_batch_size" in sig.parameters

    def test_upsert_entities_batch_accepts_entity_batch_size(self):
        """upsert_entities_batch should accept an entity_batch_size parameter."""
        from platform_context_graph.content.postgres import PostgresContentProvider

        sig = inspect.signature(PostgresContentProvider.upsert_entities_batch)
        assert "entity_batch_size" in sig.parameters


class TestContentDualWriteAcceptsOverride:
    """Verify content dual-write functions accept batch size override."""

    def test_content_dual_write_batch_accepts_content_batch_size(self):
        """_content_dual_write_batch should accept content_batch_size."""
        from platform_context_graph.tools.graph_builder_persistence import (
            _content_dual_write_batch,
        )

        sig = inspect.signature(_content_dual_write_batch)
        assert "content_batch_size" in sig.parameters
