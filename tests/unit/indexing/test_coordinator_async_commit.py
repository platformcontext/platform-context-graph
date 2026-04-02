"""Tests for async repository snapshot commit with per-batch yielding."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
import pytest_asyncio


def _make_snapshot(file_data: list[dict] | None = None, file_count: int = 0):
    """Build a minimal RepositorySnapshot-like object for testing."""
    snapshot = MagicMock()
    snapshot.repo_path = "/tmp/test-repo"
    snapshot.file_data = file_data if file_data is not None else []
    snapshot.file_count = file_count or len(snapshot.file_data)
    return snapshot


def _make_commit_result(committed_paths: tuple[str, ...] = ()):
    """Build a minimal BatchCommitResult-like object."""
    result = MagicMock()
    result.committed_file_paths = committed_paths
    result.failed_file_paths = ()
    result.entity_totals = {}
    result.content_write_duration_seconds = 0.1
    result.content_batch_count = 1
    return result


class TestAsyncCommitYieldsBetweenBatches:
    """Verify per-batch yielding behavior."""

    @pytest.mark.asyncio
    async def test_multiple_batches_run_in_executor(self):
        """Each batch should be dispatched via run_in_executor."""
        from platform_context_graph.indexing.coordinator_async_commit import (
            commit_repository_snapshot_async,
        )

        file_data = [{"path": f"/tmp/test-repo/file{i}.py"} for i in range(10)]
        snapshot = _make_snapshot(file_data=file_data)

        result = _make_commit_result(
            committed_paths=tuple(f"/tmp/test-repo/file{i}.py" for i in range(5))
        )

        builder = MagicMock()
        builder.commit_file_batch_to_graph = MagicMock(return_value=result)

        with (
            patch(
                "platform_context_graph.indexing.coordinator_async_commit"
                "._sync_setup_repo"
            ),
            patch(
                "platform_context_graph.indexing.adaptive_batch_config"
                ".resolve_batch_config"
            ) as mock_config,
        ):
            cfg = MagicMock()
            cfg.file_batch_size = 5
            cfg.flush_row_threshold = 2000
            cfg.entity_batch_size = 10000
            cfg.tx_file_limit = 5
            cfg.content_upsert_batch_size = 500
            cfg.repo_class = "medium"
            mock_config.return_value = cfg

            timing = await commit_repository_snapshot_async(
                builder,
                snapshot,
                is_dependency=False,
            )

        assert builder.commit_file_batch_to_graph.call_count == 2
        assert timing is not None

    @pytest.mark.asyncio
    async def test_returns_commit_timing_result(self):
        """Should return a CommitTimingResult with accumulated data."""
        from platform_context_graph.indexing.coordinator_async_commit import (
            commit_repository_snapshot_async,
        )
        from platform_context_graph.indexing.commit_timing import CommitTimingResult

        file_data = [{"path": "/tmp/test-repo/a.py"}]
        snapshot = _make_snapshot(file_data=file_data)

        result = _make_commit_result(committed_paths=("/tmp/test-repo/a.py",))
        builder = MagicMock()
        builder.commit_file_batch_to_graph = MagicMock(return_value=result)

        with (
            patch(
                "platform_context_graph.indexing.coordinator_async_commit"
                "._sync_setup_repo"
            ),
            patch(
                "platform_context_graph.indexing.adaptive_batch_config"
                ".resolve_batch_config"
            ) as mock_config,
        ):
            cfg = MagicMock()
            cfg.file_batch_size = 50
            cfg.flush_row_threshold = 2000
            cfg.entity_batch_size = 10000
            cfg.tx_file_limit = 5
            cfg.content_upsert_batch_size = 500
            cfg.repo_class = "medium"
            mock_config.return_value = cfg

            timing = await commit_repository_snapshot_async(
                builder,
                snapshot,
                is_dependency=False,
            )

        assert isinstance(timing, CommitTimingResult)

    @pytest.mark.asyncio
    async def test_ndjson_batch_path_uses_iterator(self):
        """When file_data is empty, should use iter_snapshot_file_data_batches_fn."""
        from platform_context_graph.indexing.coordinator_async_commit import (
            commit_repository_snapshot_async,
        )

        snapshot = _make_snapshot(file_data=[], file_count=3)

        result = _make_commit_result(
            committed_paths=("/tmp/test-repo/a.py", "/tmp/test-repo/b.py")
        )
        builder = MagicMock()
        builder.commit_file_batch_to_graph = MagicMock(return_value=result)

        batch_iter = MagicMock(
            return_value=[
                [{"path": "/tmp/test-repo/a.py"}, {"path": "/tmp/test-repo/b.py"}],
            ]
        )

        with (
            patch(
                "platform_context_graph.indexing.coordinator_async_commit"
                "._sync_setup_repo"
            ),
            patch(
                "platform_context_graph.indexing.adaptive_batch_config"
                ".resolve_batch_config"
            ) as mock_config,
        ):
            cfg = MagicMock()
            cfg.file_batch_size = 50
            cfg.flush_row_threshold = 2000
            cfg.entity_batch_size = 10000
            cfg.tx_file_limit = 5
            cfg.content_upsert_batch_size = 500
            cfg.repo_class = "medium"
            mock_config.return_value = cfg

            timing = await commit_repository_snapshot_async(
                builder,
                snapshot,
                is_dependency=False,
                iter_snapshot_file_data_batches_fn=batch_iter,
            )

        batch_iter.assert_called_once()
        assert builder.commit_file_batch_to_graph.call_count == 1

    @pytest.mark.asyncio
    async def test_failed_files_raise_runtime_error(self):
        """Should raise RuntimeError when batch commit reports failures."""
        from platform_context_graph.indexing.coordinator_async_commit import (
            commit_repository_snapshot_async,
        )

        file_data = [{"path": "/tmp/test-repo/bad.py"}]
        snapshot = _make_snapshot(file_data=file_data)

        result = MagicMock()
        result.committed_file_paths = ()
        result.failed_file_paths = ("/tmp/test-repo/bad.py",)
        result.entity_totals = {}
        result.content_write_duration_seconds = 0.0
        result.content_batch_count = 0

        builder = MagicMock()
        builder.commit_file_batch_to_graph = MagicMock(return_value=result)

        with (
            patch(
                "platform_context_graph.indexing.coordinator_async_commit"
                "._sync_setup_repo"
            ),
            patch(
                "platform_context_graph.indexing.adaptive_batch_config"
                ".resolve_batch_config"
            ) as mock_config,
        ):
            cfg = MagicMock()
            cfg.file_batch_size = 50
            cfg.flush_row_threshold = 2000
            cfg.entity_batch_size = 10000
            cfg.tx_file_limit = 5
            cfg.content_upsert_batch_size = 500
            cfg.repo_class = "medium"
            mock_config.return_value = cfg

            with pytest.raises(RuntimeError, match="Failed to persist"):
                await commit_repository_snapshot_async(
                    builder,
                    snapshot,
                    is_dependency=False,
                )
