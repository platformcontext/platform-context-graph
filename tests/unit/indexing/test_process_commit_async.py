"""Tests for ProcessPoolExecutor integration in coordinator_async_commit.

Tests verify that commit_repository_snapshot_async properly dispatches
batches via commit_batch_in_process when a ProcessPoolExecutor is provided.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, call

import pytest

from platform_context_graph.indexing.coordinator_async_commit import (
    commit_repository_snapshot_async,
)
from platform_context_graph.indexing.coordinator_models import RepositorySnapshot


@pytest.fixture
def mock_builder():
    """Mock GraphBuilder instance."""
    builder = MagicMock()
    builder.commit_file_batch_to_graph = Mock(return_value=None)
    builder.add_repository_to_graph = Mock()
    builder._content_provider = None
    return builder


@pytest.fixture
def mock_snapshot():
    """Mock RepositorySnapshot with in-memory file data."""
    snapshot = RepositorySnapshot(
        repo_path="/tmp/test-repo",
        file_data=[
            {"path": "/tmp/test-repo/file1.py", "content": "# test 1"},
            {"path": "/tmp/test-repo/file2.py", "content": "# test 2"},
        ],
        imports_map={},
        file_count=2,
    )
    return snapshot


@pytest.fixture
def mock_connection_params():
    """Mock connection parameters for child processes."""
    return {
        "neo4j_uri": "bolt://localhost:7687",
        "neo4j_username": "neo4j",
        "neo4j_password": "test-password",
        "neo4j_database": None,
        "postgres_dsn": "postgresql://test@localhost/test",
    }


@pytest.mark.asyncio
@patch(
    "platform_context_graph.indexing.coordinator_async_commit.commit_batch_in_process"
)
@patch("platform_context_graph.indexing.coordinator_async_commit._graph_store_adapter")
@patch("platform_context_graph.indexing.coordinator_async_commit.repository_metadata")
@patch("platform_context_graph.indexing.coordinator_async_commit.git_remote_for_path")
@patch("asyncio.to_thread")
async def test_async_commit_uses_process_executor_when_provided(
    mock_to_thread,
    mock_git_remote,
    mock_repo_metadata,
    mock_graph_store_adapter,
    mock_commit_batch,
    mock_builder,
    mock_snapshot,
    mock_connection_params,
):
    """When process_executor is provided, batches dispatch via commit_batch_in_process."""
    # Setup mocks
    mock_git_remote.return_value = "https://github.com/test/repo.git"
    mock_repo_metadata.return_value = {"id": "test-repo-id", "name": "test-repo"}
    mock_graph_store = MagicMock()
    mock_graph_store_adapter.return_value = mock_graph_store

    # Mock asyncio.to_thread for setup
    async def fake_to_thread(fn, *args):
        fn(*args)

    mock_to_thread.side_effect = fake_to_thread

    # Mock commit_batch_in_process to return a result
    mock_commit_result = MagicMock()
    mock_commit_result.committed_file_paths = ("/tmp/test-repo/file1.py",)
    mock_commit_result.failed_file_paths = ()
    mock_commit_result.entity_totals = {}
    mock_commit_result.content_write_duration_seconds = 0.0
    mock_commit_result.content_batch_count = 0
    mock_commit_batch.return_value = mock_commit_result

    # Create a mock ProcessPoolExecutor that actually works with asyncio
    from concurrent.futures import Future

    process_executor = MagicMock(spec=ProcessPoolExecutor)

    def fake_submit(fn):
        future = Future()
        future.set_result(fn())
        return future

    process_executor.submit = fake_submit

    # Execute
    result = await commit_repository_snapshot_async(
        mock_builder,
        mock_snapshot,
        is_dependency=False,
        process_executor=process_executor,
        connection_params=mock_connection_params,
    )

    # Verify commit_batch_in_process was called with the file batch
    assert mock_commit_batch.called
    call_kwargs = mock_commit_batch.call_args[1]
    assert "file_data_list" in call_kwargs
    assert "repo_path" in call_kwargs
    assert result is not None


@pytest.mark.asyncio
@patch("platform_context_graph.indexing.coordinator_async_commit._graph_store_adapter")
@patch("platform_context_graph.indexing.coordinator_async_commit.repository_metadata")
@patch("platform_context_graph.indexing.coordinator_async_commit.git_remote_for_path")
async def test_async_commit_falls_back_to_thread_pool_without_process_executor(
    mock_git_remote,
    mock_repo_metadata,
    mock_graph_store_adapter,
    mock_builder,
    mock_snapshot,
):
    """Without process_executor, uses ThreadPoolExecutor (backward compat)."""
    # Setup mocks
    mock_git_remote.return_value = "https://github.com/test/repo.git"
    mock_repo_metadata.return_value = {"id": "test-repo-id", "name": "test-repo"}
    mock_graph_store = MagicMock()
    mock_graph_store_adapter.return_value = mock_graph_store

    # Execute without process_executor
    result = await commit_repository_snapshot_async(
        mock_builder,
        mock_snapshot,
        is_dependency=False,
        # No process_executor or connection_params
    )

    # Verify builder.commit_file_batch_to_graph was called (old path)
    assert mock_builder.commit_file_batch_to_graph.called
    assert result is not None


@pytest.mark.asyncio
@patch(
    "platform_context_graph.indexing.coordinator_async_commit.commit_batch_in_process"
)
@patch("platform_context_graph.indexing.coordinator_async_commit._graph_store_adapter")
@patch("platform_context_graph.indexing.coordinator_async_commit.repository_metadata")
@patch("platform_context_graph.indexing.coordinator_async_commit.git_remote_for_path")
@patch("asyncio.to_thread")
async def test_async_commit_passes_connection_params_to_worker(
    mock_to_thread,
    mock_git_remote,
    mock_repo_metadata,
    mock_graph_store_adapter,
    mock_commit_batch,
    mock_builder,
    mock_snapshot,
    mock_connection_params,
):
    """Connection params are properly passed to commit_batch_in_process."""
    # Setup mocks
    mock_git_remote.return_value = "https://github.com/test/repo.git"
    mock_repo_metadata.return_value = {"id": "test-repo-id", "name": "test-repo"}
    mock_graph_store = MagicMock()
    mock_graph_store_adapter.return_value = mock_graph_store

    # Mock asyncio.to_thread for setup
    async def fake_to_thread(fn, *args):
        fn(*args)

    mock_to_thread.side_effect = fake_to_thread

    mock_commit_result = MagicMock()
    mock_commit_result.committed_file_paths = ("/tmp/test-repo/file1.py",)
    mock_commit_result.failed_file_paths = ()
    mock_commit_result.entity_totals = {}
    mock_commit_result.content_write_duration_seconds = 0.0
    mock_commit_result.content_batch_count = 0
    mock_commit_batch.return_value = mock_commit_result

    from concurrent.futures import Future

    process_executor = MagicMock(spec=ProcessPoolExecutor)

    def fake_submit(fn):
        future = Future()
        future.set_result(fn())
        return future

    process_executor.submit = fake_submit

    # Execute
    await commit_repository_snapshot_async(
        mock_builder,
        mock_snapshot,
        is_dependency=False,
        process_executor=process_executor,
        connection_params=mock_connection_params,
    )

    # Verify commit_batch_in_process was called with connection params
    assert mock_commit_batch.called
    call_kwargs = mock_commit_batch.call_args[1]
    assert call_kwargs["neo4j_uri"] == "bolt://localhost:7687"
    assert call_kwargs["neo4j_username"] == "neo4j"
    assert call_kwargs["neo4j_password"] == "test-password"
    assert call_kwargs["postgres_dsn"] == "postgresql://test@localhost/test"


@pytest.mark.asyncio
@patch(
    "platform_context_graph.indexing.coordinator_async_commit.commit_batch_in_process"
)
@patch("platform_context_graph.indexing.coordinator_async_commit._graph_store_adapter")
@patch("platform_context_graph.indexing.coordinator_async_commit.repository_metadata")
@patch("platform_context_graph.indexing.coordinator_async_commit.git_remote_for_path")
@patch("asyncio.to_thread")
async def test_async_commit_repo_setup_uses_thread_not_process(
    mock_to_thread,
    mock_git_remote,
    mock_repo_metadata,
    mock_graph_store_adapter,
    mock_commit_batch,
    mock_builder,
    mock_snapshot,
    mock_connection_params,
):
    """Repository setup (_sync_setup_repo) runs separately from batch commits."""
    # Setup mocks
    mock_git_remote.return_value = "https://github.com/test/repo.git"
    mock_repo_metadata.return_value = {"id": "test-repo-id", "name": "test-repo"}
    mock_graph_store = MagicMock()
    mock_graph_store_adapter.return_value = mock_graph_store

    # Mock asyncio.to_thread for setup
    setup_called = False

    async def fake_to_thread(fn, *args):
        nonlocal setup_called
        setup_called = True
        fn(*args)

    mock_to_thread.side_effect = fake_to_thread

    mock_commit_result = MagicMock()
    mock_commit_result.committed_file_paths = ("/tmp/test-repo/file1.py",)
    mock_commit_result.failed_file_paths = ()
    mock_commit_result.entity_totals = {}
    mock_commit_result.content_write_duration_seconds = 0.0
    mock_commit_result.content_batch_count = 0
    mock_commit_batch.return_value = mock_commit_result

    from concurrent.futures import Future

    process_executor = MagicMock(spec=ProcessPoolExecutor)

    def fake_submit(fn):
        future = Future()
        future.set_result(fn())
        return future

    process_executor.submit = fake_submit

    # Execute
    await commit_repository_snapshot_async(
        mock_builder,
        mock_snapshot,
        is_dependency=False,
        process_executor=process_executor,
        connection_params=mock_connection_params,
    )

    # Verify asyncio.to_thread was called for setup
    assert setup_called
    # Verify batch commits also happened
    assert mock_commit_batch.called
