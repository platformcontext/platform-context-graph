"""Tests for fact-store connection pooling."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

import platform_context_graph.facts.storage.postgres as store_mod
from platform_context_graph.facts.storage.postgres import PostgresFactStore


def test_fact_store_uses_connection_pool_when_available(monkeypatch) -> None:
    """The fact store should initialize a psycopg pool when available."""

    mock_pool = MagicMock()
    mock_pool_class = MagicMock(return_value=mock_pool)

    monkeypatch.setattr(store_mod, "_ConnectionPool", mock_pool_class)

    store = PostgresFactStore("postgresql://example")

    assert store._pool is mock_pool
    assert store._conn is None
    mock_pool_class.assert_called_once()


def test_fact_store_close_closes_pool_when_present(monkeypatch) -> None:
    """Closing the fact store should close its connection pool."""

    mock_pool = MagicMock()
    mock_pool_class = MagicMock(return_value=mock_pool)

    monkeypatch.setattr(store_mod, "_ConnectionPool", mock_pool_class)

    store = PostgresFactStore("postgresql://example")
    store.close()

    mock_pool.close.assert_called_once()
    assert store._pool is None


def test_fact_store_cursor_uses_pool_connection(monkeypatch) -> None:
    """The fact store should borrow a pooled connection for cursor work."""

    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_pool.connection.return_value.__exit__ = MagicMock(return_value=False)
    mock_pool_class = MagicMock(return_value=mock_pool)

    monkeypatch.setattr(store_mod, "_ConnectionPool", mock_pool_class)

    store = PostgresFactStore("postgresql://example")

    @contextmanager
    def _ensure_schema(_conn):
        yield None

    monkeypatch.setattr(store, "_ensure_schema", lambda conn: None)

    with store._cursor() as cursor:
        assert cursor is mock_cursor

    mock_pool.connection.assert_called_once()
