"""Tests for the CLI watch helper."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from platform_context_graph.cli.helpers.watch import watch_helper


def test_watch_helper_passes_workspace_scope_and_filters_to_code_watcher(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Workspace watch mode should preserve repo filters when starting the watcher."""

    workspace = tmp_path / "workspace"
    repo_a = workspace / "payments-api"
    repo_b = workspace / "orders-api"
    repo_a.mkdir(parents=True)
    repo_b.mkdir(parents=True)

    prints: list[str] = []
    db_manager = SimpleNamespace(close_driver=MagicMock())
    graph_builder = MagicMock()
    code_finder = SimpleNamespace(
        list_indexed_repositories=lambda: [
            {"path": str(repo_a)},
            {"path": str(repo_b)},
        ]
    )
    watcher = MagicMock()
    api = SimpleNamespace(
        console=SimpleNamespace(print=prints.append),
        _initialize_services=lambda: (db_manager, graph_builder, code_finder),
    )

    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.watch._api",
        lambda: api,
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.watch.resolve_watch_targets",
        lambda *_args, **_kwargs: SimpleNamespace(
            scope="workspace",
            repository_paths=[repo_a.resolve(), repo_b.resolve()],
        ),
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.watch.CodeWatcher",
        lambda *_args, **_kwargs: watcher,
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.watch.threading.Event",
        lambda: SimpleNamespace(wait=lambda: None),
    )

    watch_helper(
        str(workspace),
        scope="workspace",
        include_repositories=["*-api"],
    )

    watcher.start.assert_called_once()
    watcher.watch_directory.assert_called_once_with(
        str(workspace.resolve()),
        perform_initial_scan=False,
        scope="workspace",
        include_repositories=["*-api"],
        exclude_repositories=None,
        rediscover_interval_seconds=None,
    )
    watcher.stop.assert_called_once()
    db_manager.close_driver.assert_called_once()


def test_watch_helper_passes_rediscovery_interval_to_code_watcher(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Workspace watch helper should forward rediscovery cadence to the watcher."""

    workspace = tmp_path / "workspace"
    repo_a = workspace / "payments-api"
    repo_a.mkdir(parents=True)

    db_manager = SimpleNamespace(close_driver=MagicMock())
    graph_builder = MagicMock()
    code_finder = SimpleNamespace(
        list_indexed_repositories=lambda: [{"path": str(repo_a)}]
    )
    watcher = MagicMock()
    api = SimpleNamespace(
        console=SimpleNamespace(print=lambda *_args, **_kwargs: None),
        _initialize_services=lambda: (db_manager, graph_builder, code_finder),
    )

    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.watch._api",
        lambda: api,
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.watch.resolve_watch_targets",
        lambda *_args, **_kwargs: SimpleNamespace(
            scope="workspace",
            repository_paths=[repo_a.resolve()],
        ),
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.watch.CodeWatcher",
        lambda *_args, **_kwargs: watcher,
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.watch.threading.Event",
        lambda: SimpleNamespace(wait=lambda: None),
    )

    watch_helper(
        str(workspace),
        scope="workspace",
        rediscover_interval_seconds=30,
    )

    watcher.watch_directory.assert_called_once_with(
        str(workspace.resolve()),
        perform_initial_scan=False,
        scope="workspace",
        include_repositories=None,
        exclude_repositories=None,
        rediscover_interval_seconds=30,
    )


def test_watch_helper_reports_effective_debounce_configuration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """CLI watch should surface the effective debounce interval."""

    workspace = tmp_path / "workspace"
    repo_a = workspace / "payments-api"
    repo_a.mkdir(parents=True)

    prints: list[str] = []
    db_manager = SimpleNamespace(close_driver=MagicMock())
    graph_builder = MagicMock()
    code_finder = SimpleNamespace(
        list_indexed_repositories=lambda: [{"path": str(repo_a)}]
    )
    watcher = MagicMock()
    api = SimpleNamespace(
        console=SimpleNamespace(print=prints.append),
        _initialize_services=lambda: (db_manager, graph_builder, code_finder),
    )

    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.watch._api",
        lambda: api,
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.watch.resolve_watch_targets",
        lambda *_args, **_kwargs: SimpleNamespace(
            scope="workspace",
            repository_paths=[repo_a.resolve()],
        ),
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.watch.CodeWatcher",
        lambda *_args, **_kwargs: watcher,
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.watch.threading.Event",
        lambda: SimpleNamespace(wait=lambda: None),
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.config_manager.get_config_value",
        lambda key: {"PCG_WATCH_DEBOUNCE_SECONDS": "1.5"}.get(key),
    )

    watch_helper(str(workspace), scope="workspace")

    assert any(
        "Watch config:" in message and "debounce=1.5s" in message for message in prints
    )
