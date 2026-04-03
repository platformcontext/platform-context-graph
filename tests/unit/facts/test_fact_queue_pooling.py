"""Tests for fact-queue connection pooling."""

from __future__ import annotations

from unittest.mock import MagicMock

import platform_context_graph.facts.work_queue.postgres as queue_mod
from platform_context_graph.facts.work_queue.postgres import PostgresFactWorkQueue


def test_fact_queue_uses_connection_pool_when_available(monkeypatch) -> None:
    """The fact work queue should initialize a psycopg pool when available."""

    mock_pool = MagicMock()
    mock_pool_class = MagicMock(return_value=mock_pool)

    monkeypatch.setattr(queue_mod, "_ConnectionPool", mock_pool_class)

    queue = PostgresFactWorkQueue("postgresql://example")

    assert queue._pool is mock_pool
    assert queue._conn is None
    mock_pool_class.assert_called_once()


def test_fact_queue_close_closes_pool_when_present(monkeypatch) -> None:
    """Closing the queue should close its connection pool."""

    mock_pool = MagicMock()
    mock_pool_class = MagicMock(return_value=mock_pool)

    monkeypatch.setattr(queue_mod, "_ConnectionPool", mock_pool_class)

    queue = PostgresFactWorkQueue("postgresql://example")
    queue.close()

    mock_pool.close.assert_called_once()
    assert queue._pool is None
