"""Integration coverage for workspace watch rediscovery behavior."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from platform_context_graph.core.watcher import CodeWatcher


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
            graph_builder,
            repo_path: Path,
            debounce_interval: float = 2.0,
            perform_initial_scan: bool = True,
        ) -> None:
            del graph_builder, debounce_interval, perform_initial_scan
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

    watcher = CodeWatcher(graph_builder=SimpleNamespace())
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
