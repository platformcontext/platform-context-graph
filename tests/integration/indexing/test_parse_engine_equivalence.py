"""Integration coverage for parser output parity and future process-pool dispatch."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from platform_context_graph.tools import graph_builder_parsers
from platform_context_graph.tools.graph_builder_indexing_execution import (
    parse_repository_snapshot_async,
)


class _NullSpan:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _no_op(*_args, **_kwargs) -> None:
    return None


async def _async_no_op(*_args, **_kwargs) -> None:
    return None


def _build_builder_registry(
    get_config_value_fn: Callable[[str], str],
) -> SimpleNamespace:
    return SimpleNamespace(
        parsers=graph_builder_parsers.build_parser_registry(get_config_value_fn)
    )


def test_parse_worker_entrypoint_matches_direct_parser_output(
    tmp_path: Path,
) -> None:
    """The worker entrypoint should preserve the same parsed payload as the direct path."""

    repo_path = tmp_path / "service"
    repo_path.mkdir()
    dockerfile = repo_path / "Dockerfile"
    dockerfile.write_text(
        'FROM python:3.12-slim\nENTRYPOINT ["python", "app.py"]\n',
        encoding="utf-8",
    )

    builder = _build_builder_registry(lambda _key: "false")
    direct_result = graph_builder_parsers.parse_file(
        builder,
        repo_path,
        dockerfile,
        False,
        get_config_value_fn=lambda _key: "false",
        debug_log_fn=_no_op,
        error_logger_fn=_no_op,
        warning_logger_fn=_no_op,
    )
    worker_result = graph_builder_parsers.parse_file_for_indexing_worker(
        repo_path,
        dockerfile,
        False,
        get_config_value_fn=lambda _key: "false",
        debug_log_fn=_no_op,
        error_logger_fn=_no_op,
        warning_logger_fn=_no_op,
    )

    assert worker_result == direct_result


@pytest.mark.asyncio
async def test_parse_repository_snapshot_uses_process_pool_dispatch_when_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The enabled flag should eventually route file parsing through a process pool."""

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    file_path = repo_path / "alpha.py"
    file_path.write_text("print('ok')\n", encoding="utf-8")

    class _RecordingExecutor:
        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple[object, ...]]] = []

    @contextmanager
    def _span_scope(*_args, **_kwargs):
        yield SimpleNamespace(record_exception=lambda _exc: None)

    class _Loop:
        def __init__(self, executor: _RecordingExecutor) -> None:
            self.executor = executor

        async def run_in_executor(self, executor, fn, *args):
            assert executor is self.executor
            self.executor.calls.append((getattr(fn, "__name__", repr(fn)), args))
            return {
                "path": str(file_path),
                "repo_path": str(repo_path),
                "functions": [],
            }

    fake_observability = SimpleNamespace(start_span=_span_scope)
    recording_executor = _RecordingExecutor()
    monkeypatch.setenv("PCG_REPO_FILE_PARSE_MULTIPROCESS", "true")
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder_indexing_execution.get_observability",
        lambda: fake_observability,
    )

    builder = SimpleNamespace(
        _pre_scan_for_imports=lambda _files: {},
        parse_file=lambda *_args, **_kwargs: {
            "path": str(file_path),
            "functions": [],
        },
        job_manager=SimpleNamespace(update_job=lambda *_args, **_kwargs: None),
    )

    snapshot = await parse_repository_snapshot_async(
        builder,
        repo_path,
        [file_path],
        is_dependency=False,
        job_id=None,
        asyncio_module=SimpleNamespace(
            sleep=_async_no_op,
            get_running_loop=lambda: _Loop(recording_executor),
        ),
        info_logger_fn=_no_op,
        progress_callback=None,
        parse_executor=recording_executor,
        component="repository",
        mode="index",
        source="filesystem",
        parse_workers=2,
    )

    assert snapshot.file_count == 1
    assert snapshot.file_data[0]["path"] == str(file_path)
    assert recording_executor.calls == [
        (
            "parse_file_in_worker",
            (str(repo_path), str(file_path), False),
        )
    ]
