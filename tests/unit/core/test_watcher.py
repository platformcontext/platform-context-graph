"""Unit tests for watch planning and repo-partitioned watcher behavior."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from platform_context_graph.core.watcher import CodeWatcher, resolve_watch_targets


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
