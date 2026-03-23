"""Unit tests for checkpointed coordinator execution."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from platform_context_graph.indexing.coordinator import execute_index_run
from platform_context_graph.indexing.coordinator_models import RepositorySnapshot


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
    ) -> RepositorySnapshot:
        del is_dependency, job_id, asyncio_module, info_logger_fn, progress_callback
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
        lambda _builder, snapshot, *, is_dependency: committed.append(
            snapshot.repo_path
        ),
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
