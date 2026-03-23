"""Tests for the CLI workspace helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from platform_context_graph.cli.helpers.workspace import (
    workspace_index_helper,
    workspace_plan_helper,
    workspace_status_helper,
    workspace_sync_helper,
    workspace_watch_helper,
)


def test_workspace_plan_helper_reports_matched_and_stale_repositories(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Workspace plan should preview selected repositories and stale checkouts."""

    repos_dir = tmp_path / "repos"
    (repos_dir / "acme--payments" / ".git").mkdir(parents=True)
    (repos_dir / "stale-repo" / ".git").mkdir(parents=True)

    prints: list[str] = []
    config = SimpleNamespace(
        source_mode="githubOrg",
        repos_dir=repos_dir,
        component="workspace-plan",
    )

    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.workspace._api",
        lambda: SimpleNamespace(console=SimpleNamespace(print=prints.append)),
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.workspace.RepoSyncConfig.from_env",
        lambda *, component: config,
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.workspace.build_workspace_plan",
        lambda _config: {
            "source_mode": "githubOrg",
            "repos_dir": repos_dir,
            "repository_ids": ["acme/payments", "acme/orders"],
            "matched_repositories": 2,
            "already_cloned": 1,
            "stale_checkouts": 1,
        },
    )

    workspace_plan_helper()

    joined = "\n".join(prints)
    assert "Workspace Plan" in joined
    assert "githubOrg" in joined
    assert "Matched repositories" in joined
    assert "acme/payments" in joined
    assert "acme/orders" in joined
    assert "Stale checkouts" in joined


def test_workspace_sync_helper_reports_materialization_counts(monkeypatch) -> None:
    """Workspace sync should print the materialization result summary."""

    prints: list[str] = []
    config = SimpleNamespace(
        source_mode="explicit",
        repos_dir=Path("/tmp/repos"),
        component="workspace-sync",
    )

    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.workspace._api",
        lambda: SimpleNamespace(console=SimpleNamespace(print=prints.append)),
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.workspace.RepoSyncConfig.from_env",
        lambda *, component: config,
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.workspace.run_workspace_sync",
        lambda _config: SimpleNamespace(
            discovered=3,
            cloned=1,
            updated=1,
            skipped=1,
            failed=0,
            stale=0,
            indexed=0,
            lock_skipped=False,
        ),
    )

    workspace_sync_helper()

    joined = "\n".join(prints)
    assert "Workspace Sync" in joined
    assert "discovered=3" in joined
    assert "cloned=1" in joined
    assert "updated=1" in joined


def test_workspace_status_helper_reports_latest_workspace_index_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Workspace status should surface the latest index summary for the workspace."""

    prints: list[str] = []
    repos_dir = tmp_path / "repos"
    repos_dir.mkdir()
    (repos_dir / "acme--payments" / ".git").mkdir(parents=True)

    config = SimpleNamespace(
        source_mode="filesystem",
        repos_dir=repos_dir,
        component="workspace-status",
    )

    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.workspace._api",
        lambda: SimpleNamespace(console=SimpleNamespace(print=prints.append)),
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.workspace.RepoSyncConfig.from_env",
        lambda *, component: config,
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.workspace.describe_index_run",
        lambda target: {
            "run_id": "abc123",
            "status": "completed",
            "finalization_status": "completed",
            "repository_count": 1,
            "completed_repositories": 1,
            "failed_repositories": 0,
            "pending_repositories": 0,
        },
    )

    workspace_status_helper()

    joined = "\n".join(prints)
    assert "Workspace Status" in joined
    assert "filesystem" in joined
    assert "Local checkouts" in joined
    assert "abc123" in joined
    assert "completed" in joined


def test_workspace_index_helper_indexes_the_materialized_workspace(monkeypatch) -> None:
    """Workspace index should delegate to the shared path-based index helper."""

    prints: list[str] = []
    repos_dir = Path("/tmp/materialized-workspace")
    config = SimpleNamespace(
        source_mode="githubOrg",
        repos_dir=repos_dir,
        component="workspace-index",
    )
    index_calls: list[str] = []

    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.workspace._api",
        lambda: SimpleNamespace(console=SimpleNamespace(print=prints.append)),
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.workspace.RepoSyncConfig.from_env",
        lambda *, component: config,
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.workspace.index_helper",
        lambda path: index_calls.append(path),
    )

    workspace_index_helper()

    assert index_calls == [str(repos_dir)]
    assert any("Workspace Index" in message for message in prints)


def test_workspace_watch_helper_delegates_to_path_watch_helper(monkeypatch) -> None:
    """Workspace watch should delegate to the shared path-based watch helper."""

    prints: list[str] = []
    repos_dir = Path("/tmp/materialized-workspace")
    config = SimpleNamespace(
        source_mode="githubOrg",
        repos_dir=repos_dir,
        component="workspace-watch",
    )
    watch_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.workspace._api",
        lambda: SimpleNamespace(console=SimpleNamespace(print=prints.append)),
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.workspace.RepoSyncConfig.from_env",
        lambda *, component: config,
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.workspace.watch_helper",
        lambda path, **kwargs: watch_calls.append({"path": path, **kwargs}),
    )

    workspace_watch_helper(
        include_repositories=["*-api"],
        exclude_repositories=["infra-*"],
        rediscover_interval_seconds=45,
    )

    assert watch_calls == [
        {
            "path": str(repos_dir),
            "scope": "workspace",
            "include_repositories": ["*-api"],
            "exclude_repositories": ["infra-*"],
            "rediscover_interval_seconds": 45,
        }
    ]
    assert any("Workspace Watch" in message for message in prints)
