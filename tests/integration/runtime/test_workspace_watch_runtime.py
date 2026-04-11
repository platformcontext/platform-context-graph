"""Integration coverage for workspace watch rediscovery behavior."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

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


def test_workspace_watch_repo_handlers_keep_gitignore_scoped_to_each_repo(
    tmp_path: Path,
) -> None:
    """Repo-local `.gitignore` files should not leak across workspace repos."""

    workspace = tmp_path / "workspace"
    repo_a = workspace / "payments-api"
    repo_b = workspace / "orders-api"
    (repo_a / ".git").mkdir(parents=True)
    (repo_b / ".git").mkdir(parents=True)
    (workspace / ".gitignore").write_text("*.py\n", encoding="utf-8")
    (repo_a / ".gitignore").write_text("ignored.py\n", encoding="utf-8")

    kept_a = repo_a / "visible.py"
    dropped_a = repo_a / "ignored.py"
    kept_b = repo_b / "worker.py"
    for file_path in (kept_a, dropped_a, kept_b):
        file_path.write_text("print('ok')\n", encoding="utf-8")

    parse_calls: list[Path] = []

    def _collect_supported_files(path: Path) -> list[Path]:
        return sorted(
            candidate
            for candidate in path.rglob("*")
            if candidate.is_file() and candidate.suffix == ".py"
        )

    graph_builder = SimpleNamespace(
        parsers={".py": object()},
        _collect_supported_files=_collect_supported_files,
        _pre_scan_for_imports=lambda files: {
            "files": [str(path.resolve()) for path in files]
        },
        parse_file=lambda repo_path, file_path, is_dependency=False: (
            parse_calls.append(file_path.resolve()),
            {"path": str(file_path.resolve()), "functions": [], "classes": []},
        )[1],
        update_file_in_graph=lambda *_args, **_kwargs: None,
        delete_file_from_graph=lambda *_args, **_kwargs: None,
        _create_all_function_calls=lambda *_args, **_kwargs: None,
        _create_all_inheritance_links=lambda *_args, **_kwargs: None,
        _create_all_sql_relationships=lambda *_args, **_kwargs: None,
        _create_all_infra_links=lambda *_args, **_kwargs: None,
    )

    handler_a = RepositoryEventHandler(
        graph_builder,
        repo_a,
        debounce_interval=0.1,
        perform_initial_scan=True,
    )
    handler_b = RepositoryEventHandler(
        graph_builder,
        repo_b,
        debounce_interval=0.1,
        perform_initial_scan=True,
    )

    assert set(parse_calls) == {kept_a.resolve(), kept_b.resolve()}
    assert set(handler_a.file_data_by_path) == {str(kept_a.resolve())}
    assert set(handler_b.file_data_by_path) == {str(kept_b.resolve())}
