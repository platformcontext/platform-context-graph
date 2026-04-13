from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from platform_context_graph.core.ecosystem import EcosystemState
from platform_context_graph.core.ecosystem_indexer import EcosystemIndexer


class _RecordingJobManager:
    def __init__(self) -> None:
        self.created: list[str] = []

    def create_job(self, job_name: str) -> str:
        self.created.append(job_name)
        return f"job:{job_name}"


def test_index_repo_uses_go_owned_repo_indexer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "payments-api"
    repo.mkdir()
    (repo / "main.py").write_text("print('ok')\n", encoding="utf-8")

    go_index_calls: list[tuple[Path, bool]] = []

    def _index_repository(path: Path, *, force: bool) -> None:
        go_index_calls.append((path.resolve(), force))

    monkeypatch.setattr(
        "platform_context_graph.core.ecosystem_indexer._get_git_head_sha",
        lambda _path: "abc123",
    )

    state = EcosystemState()
    results = {"indexed": [], "failed": []}
    indexer = EcosystemIndexer(
        graph_builder=SimpleNamespace(),
        job_manager=_RecordingJobManager(),
        index_repository=_index_repository,
    )

    asyncio.run(
        indexer._index_repo(
            "payments-api",
            str(repo),
            state,
            asyncio.Semaphore(1),
            results,
        )
    )

    assert go_index_calls == [(repo.resolve(), False)]
    assert results["indexed"] == ["payments-api"]
    assert state.repos["payments-api"].status == "indexed"
    assert state.repos["payments-api"].last_indexed_commit == "abc123"
    assert state.repos["payments-api"].file_count == 1


def test_index_repo_records_failure_when_go_repo_indexer_raises(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "payments-api"
    repo.mkdir()

    monkeypatch.setattr(
        "platform_context_graph.core.ecosystem_indexer._get_git_head_sha",
        lambda _path: "abc123",
    )

    state = EcosystemState()
    results = {"indexed": [], "failed": []}
    indexer = EcosystemIndexer(
        graph_builder=SimpleNamespace(),
        job_manager=_RecordingJobManager(),
        index_repository=lambda _path, *, force: (_ for _ in ()).throw(
            RuntimeError("go bootstrap failed")
        ),
    )

    asyncio.run(
        indexer._index_repo(
            "payments-api",
            str(repo),
            state,
            asyncio.Semaphore(1),
            results,
        )
    )

    assert results["failed"] == [
        {"name": "payments-api", "error": "go bootstrap failed"}
    ]
    assert state.repos["payments-api"].status == "failed"
    assert state.repos["payments-api"].error == "go bootstrap failed"
