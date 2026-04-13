"""Integration coverage for workspace watch rediscovery behavior."""

from __future__ import annotations

from pathlib import Path

from platform_context_graph.core.watcher import CodeWatcher, RepositoryEventHandler


def test_workspace_watch_refresh_adds_new_repo_without_churning_existing_ones(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Workspace refresh should add new repos and ignore unrelated existing edits."""

    workspace = tmp_path / "workspace"
    repo_a = workspace / "payments-api"
    repo_b = workspace / "orders-api"
    file_a = repo_a / "app.py"
    (repo_a / ".git").mkdir(parents=True)
    file_a.write_text("print('a')\n", encoding="utf-8")

    class FakeObserver:
        def __init__(self) -> None:
            self.scheduled: list[str] = []

        def schedule(self, handler, path: str, recursive: bool = True):
            del handler, recursive
            self.scheduled.append(path)
            return f"watch:{path}"

        def unschedule(self, watch) -> None:
            del watch

        def is_alive(self) -> bool:
            return False

    class FakeHandler:
        def __init__(
            self,
            index_repository,
            repo_path: Path,
            debounce_interval: float = 2.0,
            perform_initial_scan: bool = True,
        ) -> None:
            del index_repository, debounce_interval, perform_initial_scan
            self.repo_path = repo_path.resolve()

        def cleanup(self) -> None:
            return None

    monkeypatch.setattr(
        "platform_context_graph.core.watcher.Observer",
        lambda: FakeObserver(),
    )
    monkeypatch.setattr(
        "platform_context_graph.core.watcher.RepositoryEventHandler",
        FakeHandler,
    )

    watcher = CodeWatcher(index_repository=lambda *_args, **_kwargs: None)
    watcher.watch_directory(
        str(workspace),
        perform_initial_scan=False,
        scope="workspace",
        rediscover_interval_seconds=30,
    )

    (repo_b / ".git").mkdir(parents=True)
    added = watcher.refresh_watch_directory(str(workspace))

    file_a.write_text("print('updated')\n", encoding="utf-8")
    unchanged = watcher.refresh_watch_directory(str(workspace))

    assert added["added_repositories"] == [str(repo_b.resolve())]
    assert added["removed_repositories"] == []
    assert unchanged["added_repositories"] == []
    assert unchanged["removed_repositories"] == []
    assert watcher.list_watched_paths() == [str(workspace.resolve())]
    assert sorted(watcher.watches[str(workspace.resolve())]) == sorted(
        [
            str(repo_a.resolve()),
            str(repo_b.resolve()),
        ]
    )


def test_workspace_watch_repo_handlers_keep_reindex_requests_scoped_to_each_repo(
    tmp_path: Path,
) -> None:
    """Repo-local change batches should stay scoped to the changed repository."""

    workspace = tmp_path / "workspace"
    repo_a = workspace / "payments-api"
    repo_b = workspace / "orders-api"
    (repo_a / ".git").mkdir(parents=True)
    (repo_b / ".git").mkdir(parents=True)
    kept_a = repo_a / "visible.py"
    kept_b = repo_b / "worker.py"
    for file_path in (kept_a, kept_b):
        file_path.write_text("print('ok')\n", encoding="utf-8")

    reindex_calls: list[tuple[Path, bool]] = []

    def _index_repository(repo_path: Path, *, force: bool) -> None:
        reindex_calls.append((repo_path.resolve(), force))

    handler_a = RepositoryEventHandler(
        _index_repository,
        repo_a,
        debounce_interval=0.1,
        perform_initial_scan=False,
    )
    handler_b = RepositoryEventHandler(
        _index_repository,
        repo_b,
        debounce_interval=0.1,
        perform_initial_scan=False,
    )

    handler_a._queue_event(str(kept_a.resolve()))
    handler_a._process_pending_changes()
    handler_b._queue_event(str(kept_b.resolve()))
    handler_b._process_pending_changes()

    assert reindex_calls == [
        (repo_a.resolve(), True),
        (repo_b.resolve(), True),
    ]
