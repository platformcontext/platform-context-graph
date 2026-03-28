"""Unit tests for checkpointed coordinator execution."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import importlib
import pytest

from platform_context_graph.indexing.coordinator import execute_index_run
from platform_context_graph.indexing.coordinator_models import RepositorySnapshot
from platform_context_graph.tools.graph_builder_persistence import BatchCommitResult


def test_execute_index_run_parses_multiple_repositories_concurrently(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A stalled first parse should not block the second repository from starting."""

    repo_a = tmp_path / "payments-api"
    repo_b = tmp_path / "orders-api"
    repo_a.mkdir()
    repo_b.mkdir()
    (repo_a / "main.py").write_text("print('a')\n", encoding="utf-8")
    (repo_b / "main.py").write_text("print('b')\n", encoding="utf-8")

    monkeypatch.setattr(
        "platform_context_graph.indexing.coordinator_storage.get_app_home",
        lambda: tmp_path / ".pcg-home",
    )
    monkeypatch.setattr(
        "platform_context_graph.indexing.coordinator.resolve_repository_file_sets",
        lambda *_args, **_kwargs: {
            repo_a.resolve(): [repo_a / "main.py"],
            repo_b.resolve(): [repo_b / "main.py"],
        },
    )

    second_started = asyncio.Event()
    parse_order: list[str] = []
    committed: list[str] = []

    async def fake_parse_repository_snapshot_async(
        _builder,
        repo_path,
        repo_files,
        *,
        is_dependency,
        job_id,
        asyncio_module,
        info_logger_fn,
        progress_callback=None,
        parse_executor=None,
        component=None,
        mode=None,
        source=None,
        parse_workers=1,
    ) -> RepositorySnapshot:
        del (
            is_dependency,
            job_id,
            asyncio_module,
            info_logger_fn,
            progress_callback,
            parse_executor,
            component,
            mode,
            source,
            parse_workers,
        )
        parse_order.append(repo_path.name)
        if len(parse_order) == 1:
            await asyncio.wait_for(second_started.wait(), timeout=0.5)
        else:
            second_started.set()
        return RepositorySnapshot(
            repo_path=str(repo_path.resolve()),
            file_count=len(repo_files),
            imports_map={repo_path.name: [str(repo_files[0].resolve())]},
            file_data=[{"path": str(repo_files[0].resolve())}],
        )

    monkeypatch.setattr(
        "platform_context_graph.indexing.coordinator.parse_repository_snapshot_async",
        fake_parse_repository_snapshot_async,
    )
    monkeypatch.setattr(
        "platform_context_graph.indexing.coordinator._commit_repository_snapshot",
        lambda _builder, snapshot, *, is_dependency, progress_callback=None, iter_snapshot_file_data_batches_fn=None: committed.append(
            snapshot.repo_path
        ),
    )
    monkeypatch.setattr(
        "platform_context_graph.indexing.coordinator.publish_run_repository_coverage",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "platform_context_graph.indexing.coordinator.finalize_index_batch",
        lambda *_args, **_kwargs: None,
    )

    @contextmanager
    def _index_run_scope(**_kwargs):
        yield SimpleNamespace(status=None, finalization_status=None)

    @contextmanager
    def _span_scope(*_args, **_kwargs):
        yield SimpleNamespace(record_exception=lambda _exc: None)

    telemetry = SimpleNamespace(
        index_run=_index_run_scope,
        start_span=_span_scope,
        record_index_repositories=lambda **_kwargs: None,
        record_index_repository_duration=lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "platform_context_graph.indexing.coordinator.get_observability",
        lambda: telemetry,
    )

    builder = SimpleNamespace(
        job_manager=SimpleNamespace(update_job=lambda *_args, **_kwargs: None)
    )

    result = asyncio.run(
        execute_index_run(
            builder,
            tmp_path,
            is_dependency=False,
            job_id=None,
            selected_repositories=[repo_a, repo_b],
            family="index",
            source="manual",
            force=False,
            component="cli",
            asyncio_module=asyncio,
            datetime_cls=SimpleNamespace(now=lambda: None),
            info_logger_fn=lambda *_args, **_kwargs: None,
            warning_logger_fn=lambda *_args, **_kwargs: None,
            error_logger_fn=lambda *_args, **_kwargs: None,
            job_status_enum=SimpleNamespace(COMPLETED="completed", FAILED="failed"),
            pathspec_module=SimpleNamespace(),
        )
    )

    assert set(parse_order) == {"payments-api", "orders-api"}
    assert committed == [str(repo_a.resolve()), str(repo_b.resolve())] or committed == [
        str(repo_b.resolve()),
        str(repo_a.resolve()),
    ]
    assert result.status == "completed"


def test_multiprocess_start_method_defaults_to_spawn(monkeypatch) -> None:
    """The parse worker pool should default to the safest cross-platform mode."""

    coordinator = importlib.import_module("platform_context_graph.indexing.coordinator")
    monkeypatch.delenv("PCG_MULTIPROCESS_START_METHOD", raising=False)

    assert coordinator._multiprocess_start_method() == "spawn"


def test_multiprocess_start_method_honors_explicit_override(monkeypatch) -> None:
    """Operators may still force a specific multiprocessing start method."""

    coordinator = importlib.import_module("platform_context_graph.indexing.coordinator")
    monkeypatch.setenv("PCG_MULTIPROCESS_START_METHOD", "forkserver")

    assert coordinator._multiprocess_start_method() == "forkserver"


def test_commit_repository_snapshot_deletes_by_canonical_repo_id(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Coordinator commits should clear old graph state via canonical repo ids."""

    coordinator = importlib.import_module("platform_context_graph.indexing.coordinator")
    snapshot = RepositorySnapshot(
        repo_path=str(tmp_path / "payments-api"),
        file_count=1,
        imports_map={},
        file_data=[{"path": str(tmp_path / "payments-api" / "main.py")}],
    )

    delete_calls: list[str] = []
    monkeypatch.setattr(
        coordinator,
        "_graph_store_adapter",
        lambda _builder: SimpleNamespace(
            delete_repository=lambda repo_identifier: delete_calls.append(
                repo_identifier
            )
        ),
    )
    monkeypatch.setattr(
        coordinator,
        "repository_metadata",
        lambda **_kwargs: {"id": "repository:r_12345678"},
    )
    monkeypatch.setattr(coordinator, "git_remote_for_path", lambda _path: None)

    builder = SimpleNamespace(
        _content_provider=SimpleNamespace(enabled=False),
        add_repository_to_graph=lambda *_args, **_kwargs: None,
        commit_file_batch_to_graph=lambda *_args, **_kwargs: None,
    )

    coordinator._commit_repository_snapshot(
        builder,
        snapshot,
        is_dependency=False,
    )

    assert delete_calls == ["repository:r_12345678"]


def test_commit_repository_snapshot_discards_committed_batches_and_reports_progress(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Coordinator commit should release processed file-data batches eagerly."""

    coordinator = importlib.import_module("platform_context_graph.indexing.coordinator")
    repo_path = tmp_path / "payments-api"
    snapshot = RepositorySnapshot(
        repo_path=str(repo_path),
        file_count=3,
        imports_map={},
        file_data=[
            {"path": str(repo_path / "a.py")},
            {"path": str(repo_path / "b.py")},
            {"path": str(repo_path / "c.py")},
        ],
    )

    monkeypatch.setattr(
        coordinator,
        "_graph_store_adapter",
        lambda _builder: SimpleNamespace(delete_repository=lambda _repo_id: None),
    )
    monkeypatch.setattr(
        coordinator,
        "repository_metadata",
        lambda **_kwargs: {"id": "repository:r_12345678"},
    )
    monkeypatch.setattr(coordinator, "git_remote_for_path", lambda _path: None)
    monkeypatch.setenv("PCG_FILE_BATCH_SIZE", "2")

    committed_batch_sizes: list[int] = []
    progress_updates: list[dict[str, object]] = []

    builder = SimpleNamespace(
        _content_provider=SimpleNamespace(enabled=False),
        add_repository_to_graph=lambda *_args, **_kwargs: None,
        commit_file_batch_to_graph=lambda batch, _repo_path, **_kwargs: committed_batch_sizes.append(
            len(batch)
        ),
    )

    coordinator._commit_repository_snapshot(
        builder,
        snapshot,
        is_dependency=False,
        progress_callback=lambda **kwargs: progress_updates.append(kwargs),
    )

    assert committed_batch_sizes == [2, 1]
    assert snapshot.file_data == []
    assert progress_updates == [
        {
            "processed_files": 2,
            "total_files": 3,
            "current_file": str((repo_path / "b.py").resolve()),
            "committed": True,
        },
        {
            "processed_files": 3,
            "total_files": 3,
            "current_file": str((repo_path / "c.py").resolve()),
            "committed": True,
        },
    ]


def test_commit_repository_snapshot_replays_disk_backed_batches_when_snapshot_cleared(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Coordinator commit should support disk-backed replay after parse spills."""

    coordinator = importlib.import_module("platform_context_graph.indexing.coordinator")
    repo_path = tmp_path / "payments-api"
    snapshot = RepositorySnapshot(
        repo_path=str(repo_path),
        file_count=3,
        imports_map={},
        file_data=[],
    )

    monkeypatch.setattr(
        coordinator,
        "_graph_store_adapter",
        lambda _builder: SimpleNamespace(delete_repository=lambda _repo_id: None),
    )
    monkeypatch.setattr(
        coordinator,
        "repository_metadata",
        lambda **_kwargs: {"id": "repository:r_12345678"},
    )
    monkeypatch.setattr(coordinator, "git_remote_for_path", lambda _path: None)
    monkeypatch.setenv("PCG_FILE_BATCH_SIZE", "2")

    committed_batch_sizes: list[int] = []
    progress_updates: list[dict[str, object]] = []

    builder = SimpleNamespace(
        _content_provider=SimpleNamespace(enabled=False),
        add_repository_to_graph=lambda *_args, **_kwargs: None,
        commit_file_batch_to_graph=lambda batch, _repo_path, **_kwargs: committed_batch_sizes.append(
            len(batch)
        ),
    )

    coordinator._commit_repository_snapshot(
        builder,
        snapshot,
        is_dependency=False,
        progress_callback=lambda **kwargs: progress_updates.append(kwargs),
        iter_snapshot_file_data_batches_fn=lambda _repo_path, batch_size: iter(
            [
                [
                    {"path": str(repo_path / "a.py")},
                    {"path": str(repo_path / "b.py")},
                ][:batch_size],
                [
                    {"path": str(repo_path / "c.py")},
                ],
            ]
        ),
    )

    assert committed_batch_sizes == [2, 1]
    assert progress_updates == [
        {
            "processed_files": 2,
            "total_files": 3,
            "current_file": str((repo_path / "b.py").resolve()),
            "committed": True,
        },
        {
            "processed_files": 3,
            "total_files": 3,
            "current_file": str((repo_path / "c.py").resolve()),
            "committed": True,
        },
    ]


def test_commit_repository_snapshot_relays_intra_batch_heartbeats(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Coordinator commit should surface builder heartbeats before batch commit."""

    coordinator = importlib.import_module("platform_context_graph.indexing.coordinator")
    repo_path = tmp_path / "payments-api"
    snapshot = RepositorySnapshot(
        repo_path=str(repo_path),
        file_count=3,
        imports_map={},
        file_data=[
            {"path": str(repo_path / "a.py")},
            {"path": str(repo_path / "b.py")},
            {"path": str(repo_path / "c.py")},
        ],
    )

    monkeypatch.setattr(
        coordinator,
        "_graph_store_adapter",
        lambda _builder: SimpleNamespace(delete_repository=lambda _repo_id: None),
    )
    monkeypatch.setattr(
        coordinator,
        "repository_metadata",
        lambda **_kwargs: {"id": "repository:r_12345678"},
    )
    monkeypatch.setattr(coordinator, "git_remote_for_path", lambda _path: None)
    monkeypatch.setenv("PCG_FILE_BATCH_SIZE", "3")

    progress_updates: list[dict[str, object]] = []

    def _commit_file_batch_to_graph(batch, _repo_path, *, progress_callback=None):
        assert len(batch) == 3
        assert callable(progress_callback)
        progress_callback(
            processed_files=1,
            total_files=3,
            current_file=str((repo_path / "a.py").resolve()),
            committed=False,
        )
        progress_callback(
            processed_files=2,
            total_files=3,
            current_file=str((repo_path / "b.py").resolve()),
            committed=False,
        )
        progress_callback(
            processed_files=3,
            total_files=3,
            current_file=str((repo_path / "c.py").resolve()),
            committed=False,
        )

    builder = SimpleNamespace(
        _content_provider=SimpleNamespace(enabled=False),
        add_repository_to_graph=lambda *_args, **_kwargs: None,
        commit_file_batch_to_graph=_commit_file_batch_to_graph,
    )

    coordinator._commit_repository_snapshot(
        builder,
        snapshot,
        is_dependency=False,
        progress_callback=lambda **kwargs: progress_updates.append(kwargs),
    )

    assert progress_updates == [
        {
            "processed_files": 1,
            "total_files": 3,
            "current_file": str((repo_path / "a.py").resolve()),
            "committed": False,
        },
        {
            "processed_files": 2,
            "total_files": 3,
            "current_file": str((repo_path / "b.py").resolve()),
            "committed": False,
        },
        {
            "processed_files": 3,
            "total_files": 3,
            "current_file": str((repo_path / "c.py").resolve()),
            "committed": False,
        },
        {
            "processed_files": 3,
            "total_files": 3,
            "current_file": str((repo_path / "c.py").resolve()),
            "committed": True,
        },
    ]


def test_commit_repository_snapshot_requeues_failed_files_from_partial_batch_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Partial batch failures should keep failed files in the snapshot for retry."""

    coordinator = importlib.import_module("platform_context_graph.indexing.coordinator")
    repo_path = tmp_path / "payments-api"
    snapshot = RepositorySnapshot(
        repo_path=str(repo_path),
        file_count=3,
        imports_map={},
        file_data=[
            {"path": str(repo_path / "a.py")},
            {"path": str(repo_path / "b.py")},
            {"path": str(repo_path / "c.py")},
        ],
    )

    monkeypatch.setattr(
        coordinator,
        "_graph_store_adapter",
        lambda _builder: SimpleNamespace(delete_repository=lambda _repo_id: None),
    )
    monkeypatch.setattr(
        coordinator,
        "repository_metadata",
        lambda **_kwargs: {"id": "repository:r_12345678"},
    )
    monkeypatch.setattr(coordinator, "git_remote_for_path", lambda _path: None)
    monkeypatch.setenv("PCG_FILE_BATCH_SIZE", "3")

    progress_updates: list[dict[str, object]] = []

    builder = SimpleNamespace(
        _content_provider=SimpleNamespace(enabled=False),
        add_repository_to_graph=lambda *_args, **_kwargs: None,
        commit_file_batch_to_graph=lambda batch, _repo_path, **_kwargs: BatchCommitResult(
            committed_file_paths=(str((repo_path / "a.py").resolve()),),
            failed_file_paths=(
                str((repo_path / "b.py").resolve()),
                str((repo_path / "c.py").resolve()),
            ),
        ),
    )

    with pytest.raises(RuntimeError, match="Failed to persist 2 files"):
        coordinator._commit_repository_snapshot(
            builder,
            snapshot,
            is_dependency=False,
            progress_callback=lambda **kwargs: progress_updates.append(kwargs),
        )

    assert snapshot.file_data == [
        {"path": str(repo_path / "b.py")},
        {"path": str(repo_path / "c.py")},
    ]
    assert progress_updates == [
        {
            "processed_files": 1,
            "total_files": 3,
            "current_file": str((repo_path / "a.py").resolve()),
            "committed": True,
        }
    ]
