"""Unit tests for graph_builder_persistence_worker (child process commit)."""

from __future__ import annotations

import functools
import os
import pickle
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from platform_context_graph.tools.graph_builder_persistence import BatchCommitResult
from platform_context_graph.tools.graph_builder_persistence_worker import (
    commit_batch_in_process,
    get_commit_worker_connection_params,
)

# Reset process-level cached driver between tests to ensure isolation.
import platform_context_graph.tools.graph_builder_persistence_worker as _worker_mod


@pytest.fixture(autouse=True)
def _reset_cached_driver():
    """Clear process-level cached Neo4j driver between tests."""
    _worker_mod._cached_driver = None
    _worker_mod._cached_driver_wrapper = None
    _worker_mod._cached_driver_key = None
    yield
    _worker_mod._cached_driver = None
    _worker_mod._cached_driver_wrapper = None
    _worker_mod._cached_driver_key = None


class TestCommitBatchInProcessPicklability:
    """Verify commit_batch_in_process can be used with ProcessPoolExecutor."""

    def test_commit_batch_in_process_is_picklable(self):
        """Verify functools.partial(commit_batch_in_process, ...) can be pickled.

        ProcessPoolExecutor requires the target function and its arguments
        to be picklable. This test ensures our worker function meets that requirement.
        """
        partial_func = functools.partial(
            commit_batch_in_process,
            neo4j_uri="bolt://localhost:7687",
            neo4j_username="neo4j",
            neo4j_password="test",
            neo4j_database="neo4j",
            postgres_dsn="postgresql://user:pass@localhost/db",
            file_data_list=[{"path": "test.py"}],
            repo_path="/tmp/repo",
        )

        # This should not raise
        pickled = pickle.dumps(partial_func)
        unpickled = pickle.loads(pickled)

        assert callable(unpickled)


class TestCommitBatchInProcessDelegation:
    """Verify commit_batch_in_process creates driver and delegates correctly."""

    @patch(
        "platform_context_graph.tools.graph_builder_persistence_worker.neo4j.GraphDatabase.driver"
    )
    @patch(
        "platform_context_graph.tools.graph_builder_persistence_worker.commit_file_batch_to_graph"
    )
    @patch(
        "platform_context_graph.tools.graph_builder_persistence_worker._init_postgres_content_provider"
    )
    def test_commit_batch_in_process_creates_driver_and_delegates(
        self,
        mock_init_postgres: Mock,
        mock_commit_fn: Mock,
        mock_driver_factory: Mock,
    ):
        """Verify worker creates Neo4j driver, wraps it, and delegates to commit function."""
        # Arrange
        mock_driver = MagicMock()
        mock_driver_factory.return_value = mock_driver

        expected_result = BatchCommitResult(
            committed_file_paths=("test.py",),
            failed_file_paths=(),
            content_write_duration_seconds=1.5,
            graph_write_duration_seconds=2.5,
            entity_totals={"Function": 10, "Class": 5},
        )
        mock_commit_fn.return_value = expected_result

        file_data = [{"path": "test.py", "entities": {"functions": []}}]

        # Act
        result = commit_batch_in_process(
            neo4j_uri="bolt://localhost:7687",
            neo4j_username="neo4j",
            neo4j_password="secret",
            neo4j_database="neo4j",
            postgres_dsn="postgresql://user:pass@localhost/db",
            file_data_list=file_data,
            repo_path="/tmp/repo",
        )

        # Assert - Neo4j driver created
        mock_driver_factory.assert_called_once_with(
            "bolt://localhost:7687",
            auth=("neo4j", "secret"),
        )

        # Assert - Postgres provider initialized
        mock_init_postgres.assert_called_once_with(
            "postgresql://user:pass@localhost/db"
        )

        # Assert - commit function called with builder that has driver
        assert mock_commit_fn.call_count == 1
        call_kwargs = mock_commit_fn.call_args[1]
        builder = mock_commit_fn.call_args[0][0]

        # Verify builder has driver property
        assert hasattr(builder, "driver")
        assert builder.driver is not None

        # Verify call arguments
        assert call_kwargs["file_data_list"] == file_data
        assert str(call_kwargs["repo_path"]) == "/tmp/repo"

        # Assert - result returned correctly
        assert result == expected_result

    @patch(
        "platform_context_graph.tools.graph_builder_persistence_worker.neo4j.GraphDatabase.driver"
    )
    @patch(
        "platform_context_graph.tools.graph_builder_persistence_worker.commit_file_batch_to_graph"
    )
    @patch(
        "platform_context_graph.tools.graph_builder_persistence_worker._init_postgres_content_provider"
    )
    def test_commit_batch_in_process_passes_adaptive_config(
        self,
        mock_init_postgres: Mock,
        mock_commit_fn: Mock,
        mock_driver_factory: Mock,
    ):
        """Verify adaptive batch sizing parameters are forwarded to commit function."""
        # Arrange
        mock_driver = MagicMock()
        mock_driver_factory.return_value = mock_driver
        mock_commit_fn.return_value = BatchCommitResult()

        # Act
        commit_batch_in_process(
            neo4j_uri="bolt://localhost:7687",
            neo4j_username="neo4j",
            neo4j_password="secret",
            neo4j_database="neo4j",
            postgres_dsn=None,
            file_data_list=[{"path": "test.py"}],
            repo_path="/tmp/repo",
            adaptive_flush_threshold=100,
            adaptive_entity_batch_size=50,
            adaptive_tx_file_limit=10,
            adaptive_content_batch_size=25,
        )

        # Assert - adaptive params forwarded
        call_kwargs = mock_commit_fn.call_args[1]
        assert call_kwargs["adaptive_flush_threshold"] == 100
        assert call_kwargs["adaptive_entity_batch_size"] == 50
        assert call_kwargs["adaptive_tx_file_limit"] == 10
        assert call_kwargs["adaptive_content_batch_size"] == 25


class TestDriverCaching:
    """Verify Neo4j driver is cached across batches in the same process."""

    @patch(
        "platform_context_graph.tools.graph_builder_persistence_worker.neo4j.GraphDatabase.driver"
    )
    @patch(
        "platform_context_graph.tools.graph_builder_persistence_worker.commit_file_batch_to_graph"
    )
    def test_driver_cached_across_batches(
        self,
        mock_commit_fn: Mock,
        mock_driver_factory: Mock,
    ):
        """Calling commit_batch_in_process twice should create driver only once."""
        mock_driver = MagicMock()
        mock_driver_factory.return_value = mock_driver
        mock_commit_fn.return_value = BatchCommitResult()

        conn_kwargs = dict(
            neo4j_uri="bolt://localhost:7687",
            neo4j_username="neo4j",
            neo4j_password="secret",
            neo4j_database="neo4j",
            postgres_dsn=None,
            file_data_list=[{"path": "test.py"}],
            repo_path="/tmp/repo",
        )

        # First call — creates driver
        commit_batch_in_process(**conn_kwargs)
        assert mock_driver_factory.call_count == 1

        # Second call — reuses cached driver
        commit_batch_in_process(**conn_kwargs)
        assert mock_driver_factory.call_count == 1

        # Driver not closed (cached for process lifetime)
        mock_driver.close.assert_not_called()

    @patch(
        "platform_context_graph.tools.graph_builder_persistence_worker.neo4j.GraphDatabase.driver"
    )
    @patch(
        "platform_context_graph.tools.graph_builder_persistence_worker.commit_file_batch_to_graph"
    )
    def test_driver_not_closed_on_error(
        self,
        mock_commit_fn: Mock,
        mock_driver_factory: Mock,
    ):
        """Driver stays cached even if a batch commit raises an exception."""
        mock_driver = MagicMock()
        mock_driver_factory.return_value = mock_driver
        mock_commit_fn.side_effect = RuntimeError("Commit failed")

        with pytest.raises(RuntimeError, match="Commit failed"):
            commit_batch_in_process(
                neo4j_uri="bolt://localhost:7687",
                neo4j_username="neo4j",
                neo4j_password="secret",
                neo4j_database="neo4j",
                postgres_dsn=None,
                file_data_list=[{"path": "test.py"}],
                repo_path="/tmp/repo",
            )

        # Driver stays cached — not closed per batch
        mock_driver.close.assert_not_called()
        assert _worker_mod._cached_driver is mock_driver


class TestGetConnectionParams:
    """Verify get_commit_worker_connection_params reads environment correctly."""

    def test_get_connection_params_reads_env(self, monkeypatch):
        """Verify function reads connection params from environment variables."""
        monkeypatch.setenv("NEO4J_URI", "bolt://neo4j:7687")
        monkeypatch.setenv("NEO4J_USERNAME", "testuser")
        monkeypatch.setenv("NEO4J_PASSWORD", "testpass")
        monkeypatch.setenv("NEO4J_DATABASE", "testdb")
        monkeypatch.setenv("PCG_CONTENT_STORE_DSN", "postgresql://pg:pass@host/db")

        params = get_commit_worker_connection_params()

        assert params["neo4j_uri"] == "bolt://neo4j:7687"
        assert params["neo4j_username"] == "testuser"
        assert params["neo4j_password"] == "testpass"
        assert params["neo4j_database"] == "testdb"
        assert params["postgres_dsn"] == "postgresql://pg:pass@host/db"

    def test_get_connection_params_raises_without_neo4j_uri(self, monkeypatch):
        """Verify ValueError when NEO4J_URI is not set."""
        monkeypatch.delenv("NEO4J_URI", raising=False)
        monkeypatch.delenv("NEO4J_USERNAME", raising=False)
        monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
        monkeypatch.delenv("NEO4J_DATABASE", raising=False)
        monkeypatch.delenv("PCG_CONTENT_STORE_DSN", raising=False)
        monkeypatch.delenv("PCG_POSTGRES_DSN", raising=False)

        with pytest.raises(ValueError, match="NEO4J_URI"):
            get_commit_worker_connection_params()

    def test_get_connection_params_prefers_content_store_dsn(self, monkeypatch):
        """Verify PCG_CONTENT_STORE_DSN takes precedence over PCG_POSTGRES_DSN."""
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setenv("PCG_CONTENT_STORE_DSN", "postgresql://content:pass@host/db")
        monkeypatch.setenv("PCG_POSTGRES_DSN", "postgresql://postgres:pass@host/db")

        params = get_commit_worker_connection_params()

        assert params["postgres_dsn"] == "postgresql://content:pass@host/db"

    def test_get_connection_params_fallback_to_postgres_dsn(self, monkeypatch):
        """Verify PCG_POSTGRES_DSN used when PCG_CONTENT_STORE_DSN not set."""
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.delenv("PCG_CONTENT_STORE_DSN", raising=False)
        monkeypatch.setenv("PCG_POSTGRES_DSN", "postgresql://postgres:pass@host/db")

        params = get_commit_worker_connection_params()

        assert params["postgres_dsn"] == "postgresql://postgres:pass@host/db"
