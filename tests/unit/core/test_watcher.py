"""Unit tests for watch planning and repo-partitioned watcher behavior."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from platform_context_graph.core.watcher import (
    CodeWatcher,
    RepositoryEventHandler,
    resolve_watch_targets,
)


def test_resolve_watch_targets_auto_scope_discovers_nested_repositories(
    tmp_path: Path,
) -> None:
    """Auto scope should treat a multi-repo folder as a workspace."""

    workspace = tmp_path / "workspace"
    repo_a = workspace / "payments-api"
    repo_b = workspace / "orders-api"
    (repo_a / ".git").mkdir(parents=True)
    (repo_b / ".git").mkdir(parents=True)

    plan = resolve_watch_targets(workspace, scope="auto")

    assert plan.scope == "workspace"
    assert plan.root_path == workspace.resolve()
    assert plan.repository_paths == [repo_b.resolve(), repo_a.resolve()]


def test_resolve_watch_targets_workspace_scope_applies_repo_filters(
    tmp_path: Path,
) -> None:
    """Workspace watch filters should apply to discovered repository roots."""

    workspace = tmp_path / "workspace"
    repo_a = workspace / "payments-api"
    repo_b = workspace / "orders-api"
    repo_c = workspace / "infra-live"
    (repo_a / ".git").mkdir(parents=True)
    (repo_b / ".git").mkdir(parents=True)
    (repo_c / ".git").mkdir(parents=True)

    plan = resolve_watch_targets(
        workspace,
        scope="workspace",
        include_repositories=["*-api", "infra-*"],
        exclude_repositories=["orders-*"],
    )

    assert plan.scope == "workspace"
    assert plan.repository_paths == [repo_c.resolve(), repo_a.resolve()]


def test_resolve_watch_targets_repo_scope_keeps_single_repository(
    tmp_path: Path,
) -> None:
    """Explicit repo scope should keep the provided repository as-is."""

    repo = tmp_path / "payments-api"
    (repo / ".git").mkdir(parents=True)

    plan = resolve_watch_targets(repo, scope="repo")

    assert plan.scope == "repo"
    assert plan.repository_paths == [repo.resolve()]


def test_refresh_watch_directory_adds_new_workspace_repository(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Workspace watch refresh should attach new repo handlers without restart."""

    workspace = tmp_path / "workspace"
    repo_a = workspace / "payments-api"
    repo_b = workspace / "orders-api"
    (repo_a / ".git").mkdir(parents=True)

    class FakeObserver:
        def __init__(self) -> None:
            self.scheduled: list[str] = []
            self.unscheduled: list[str] = []

        def schedule(self, handler, path: str, recursive: bool = True):
            del handler, recursive
            self.scheduled.append(path)
            return f"watch:{path}"

        def unschedule(self, watch) -> None:
            self.unscheduled.append(str(watch))

        def is_alive(self) -> bool:
            return False

    cleanup_calls: list[str] = []

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
            cleanup_calls.append(str(self.repo_path))

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
    result = watcher.refresh_watch_directory(str(workspace))

    assert result["added_repositories"] == [str(repo_b.resolve())]
    assert watcher.watches[str(workspace.resolve())]


def test_repository_event_handlers_keep_workspace_repo_updates_partitioned(
    tmp_path: Path,
) -> None:
    """One repo's file changes should not force updates in unrelated repos."""

    workspace = tmp_path / "workspace"
    repo_a = workspace / "payments-api"
    repo_b = workspace / "orders-api"
    file_a = repo_a / "app.py"
    file_b = repo_b / "worker.py"
    file_a.parent.mkdir(parents=True)
    file_b.parent.mkdir(parents=True)
    file_a.write_text("print('a')\n", encoding="utf-8")
    file_b.write_text("print('b')\n", encoding="utf-8")

    update_calls: list[tuple[Path, Path]] = []
    def _collect_supported_files(path: Path) -> list[Path]:
        return sorted(
            candidate
            for candidate in path.rglob("*")
            if candidate.is_file() and candidate.suffix == ".py"
        )

    graph_builder = SimpleNamespace(
        parsers={".py": object()},
        _collect_supported_files=_collect_supported_files,
        _pre_scan_for_imports=lambda _files: {},
        update_file_in_graph=lambda path, repo_path, imports_map: (
            update_calls.append((repo_path.resolve(), path.resolve())),
            {"path": str(path.resolve()), "imports_map": imports_map},
        )[1],
        delete_file_from_graph=lambda _path: None,
        _create_all_function_calls=lambda _file_data, _imports_map: None,
        _create_all_inheritance_links=lambda _file_data, _imports_map: None,
        _create_all_infra_links=lambda _file_data: None,
    )

    handler_a = RepositoryEventHandler(
        graph_builder,
        repo_a,
        debounce_interval=0.1,
        perform_initial_scan=False,
    )
    handler_b = RepositoryEventHandler(
        graph_builder,
        repo_b,
        debounce_interval=0.1,
        perform_initial_scan=False,
    )

    handler_a._queue_event(str(file_a))
    handler_a._process_pending_changes()
    handler_b._queue_event(str(file_b))
    handler_b._process_pending_changes()

    assert update_calls == [
        (repo_a.resolve(), file_a.resolve()),
        (repo_b.resolve(), file_b.resolve()),
    ]


def test_code_watcher_stop_clears_repo_partition_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Stopping a workspace watcher should clear watched roots and handlers."""

    workspace = tmp_path / "workspace"
    repo_a = workspace / "payments-api"
    (repo_a / ".git").mkdir(parents=True)

    class FakeObserver:
        def __init__(self) -> None:
            self.stop_called = False
            self.join_called = False

        def schedule(self, handler, path: str, recursive: bool = True):
            del handler, recursive
            return f"watch:{path}"

        def unschedule(self, watch) -> None:
            del watch

        def is_alive(self) -> bool:
            return True

        def start(self) -> None:
            return None

        def stop(self) -> None:
            self.stop_called = True

        def join(self) -> None:
            self.join_called = True

    cleanup_calls: list[str] = []

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
            cleanup_calls.append(str(self.repo_path))

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
    )

    watcher.stop()

    assert cleanup_calls == [str(repo_a.resolve())]
    assert watcher.watched_paths == set()
    assert watcher.watches == {}
    assert watcher._handlers == {}
    assert watcher._plans == {}
    assert watcher._watch_configs == {}


def test_repository_event_handler_initial_scan_skips_gitignored_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Initial watcher scans should honor repo-local .gitignore rules."""

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    visible = repo / "visible.py"
    ignored = repo / "ignored.py"
    visible.write_text("print('visible')\n", encoding="utf-8")
    ignored.write_text("print('ignored')\n", encoding="utf-8")
    (repo / ".gitignore").write_text("ignored.py\n", encoding="utf-8")

    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder.get_config_value",
        lambda key: "true" if key == "PCG_HONOR_GITIGNORE" else None,
    )

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
            "visible": [str(path.resolve()) for path in files]
        },
        parse_file=lambda repo_path, file_path, is_dependency=False: (
            parse_calls.append(file_path.resolve()),
            {"path": str(file_path.resolve()), "functions": [], "classes": []},
        )[1],
        update_file_in_graph=lambda *_args, **_kwargs: None,
        delete_file_from_graph=lambda *_args, **_kwargs: None,
        _create_all_function_calls=lambda *_args, **_kwargs: None,
        _create_all_inheritance_links=lambda *_args, **_kwargs: None,
        _create_all_infra_links=lambda *_args, **_kwargs: None,
    )

    handler = RepositoryEventHandler(
        graph_builder,
        repo,
        debounce_interval=0.1,
        perform_initial_scan=True,
    )

    assert parse_calls == [visible.resolve()]
    assert sorted(handler.file_data_by_path) == [str(visible.resolve())]


def test_repository_event_handler_gitignore_change_removes_newly_ignored_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Changing .gitignore should trigger a full rescan and stale graph cleanup."""

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    tracked = repo / "app.py"
    tracked.write_text("print('tracked')\n", encoding="utf-8")
    (repo / ".gitignore").write_text("", encoding="utf-8")

    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder.get_config_value",
        lambda key: "true" if key == "PCG_HONOR_GITIGNORE" else None,
    )

    delete_file_from_graph = MagicMock()
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
            "app": [str(path.resolve()) for path in files]
        },
        parse_file=lambda repo_path, file_path, is_dependency=False: {
            "path": str(file_path.resolve()),
            "functions": [],
            "classes": [],
        },
        update_file_in_graph=lambda path, repo_path, imports_map: {
            "path": str(path.resolve()),
            "imports_map": imports_map,
        },
        delete_file_from_graph=delete_file_from_graph,
        _create_all_function_calls=lambda *_args, **_kwargs: None,
        _create_all_inheritance_links=lambda *_args, **_kwargs: None,
        _create_all_infra_links=lambda *_args, **_kwargs: None,
    )

    handler = RepositoryEventHandler(
        graph_builder,
        repo,
        debounce_interval=0.1,
        perform_initial_scan=True,
    )
    assert str(tracked.resolve()) in handler.file_data_by_path

    (repo / ".gitignore").write_text("app.py\n", encoding="utf-8")
    handler._queue_event(str((repo / ".gitignore").resolve()))
    handler._process_pending_changes()

    delete_file_from_graph.assert_called_once_with(str(tracked.resolve()))
    assert handler.file_data_by_path == {}
