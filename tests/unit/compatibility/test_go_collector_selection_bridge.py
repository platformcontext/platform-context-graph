"""Tests for the Go collector selection compatibility bridge."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from platform_context_graph.runtime.ingester.config import RepoSyncConfig, RepoSyncResult
from platform_context_graph.runtime.ingester.go_collector_selection_bridge import (
    collect_selection_batch,
)


def test_collect_selection_batch_emits_observed_at_repositories_and_remote_urls(
    tmp_path: Path,
) -> None:
    """The selection bridge should report one cycle of repository picks."""

    repo_a = tmp_path / "service-a"
    repo_b = tmp_path / "service-b"
    repo_a.mkdir()
    repo_b.mkdir()

    observed_at = datetime(2026, 4, 12, 15, 30, tzinfo=timezone.utc)
    config = RepoSyncConfig(
        repos_dir=tmp_path / "workspace",
        source_mode="filesystem",
        git_auth_method="none",
        github_org=None,
        repositories=[],
        filesystem_root=tmp_path,
        clone_depth=1,
        repo_limit=50,
        sync_lock_dir=tmp_path / ".pcg-sync.lock",
        component="collector-git-selection-bridge",
    )

    def fake_run_repo_sync_cycle(
        _config: RepoSyncConfig,
        *,
        index_workspace,
    ) -> RepoSyncResult:
        index_workspace(
            config.repos_dir,
            selected_repositories=[repo_b, repo_a],
            family="sync",
            source="filesystem",
            component=config.component,
        )
        return RepoSyncResult(discovered=2, indexed=2)

    selection = collect_selection_batch(
        config,
        run_repo_sync_cycle_fn=fake_run_repo_sync_cycle,
        git_remote_for_path_fn=lambda repo_path: {
            repo_a: "https://github.com/example/service-a",
            repo_b: "https://github.com/example/service-b",
        }[repo_path],
        utc_now_fn=lambda: observed_at,
    )

    assert selection == {
        "observed_at": "2026-04-12T15:30:00+00:00",
        "repositories": [
            {
                "repo_path": str(repo_a.resolve()),
                "remote_url": "https://github.com/example/service-a",
            },
            {
                "repo_path": str(repo_b.resolve()),
                "remote_url": "https://github.com/example/service-b",
            },
        ],
    }
