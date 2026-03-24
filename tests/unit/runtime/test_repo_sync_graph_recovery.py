from __future__ import annotations

import importlib
from contextlib import contextmanager
from pathlib import Path


def test_repo_sync_cycle_indexes_repositories_missing_from_graph(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Sync should self-heal local checkouts that are missing graph state."""

    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")
    sync = importlib.import_module("platform_context_graph.runtime.ingester.sync")

    repos_dir = tmp_path / "workspace" / "repos"
    repo_a = repos_dir / "platformcontext--payments-api"
    (repo_a / ".git").mkdir(parents=True)

    config = repo_sync.RepoSyncConfig(
        repos_dir=repos_dir,
        source_mode="githubOrg",
        git_auth_method="token",
        github_org="platformcontext",
        repositories=[],
        filesystem_root=None,
        clone_depth=1,
        repo_limit=20,
        sync_lock_dir=repos_dir / ".pcg-sync.lock",
        component="repo-sync",
    )

    captured: dict[str, object] = {}

    @contextmanager
    def _workspace_lock(_config):
        yield True

    @contextmanager
    def _index_cycle(**_kwargs):
        yield

    monkeypatch.setattr(sync, "initialize_observability", lambda **_kwargs: None)
    monkeypatch.setattr(sync, "workspace_lock", _workspace_lock)
    monkeypatch.setattr(sync, "begin_index_cycle", _index_cycle)
    monkeypatch.setattr(sync, "record_phase", lambda **_kwargs: None)
    monkeypatch.setattr(sync, "git_token", lambda _config: "token")
    monkeypatch.setattr(
        sync,
        "clone_missing_repositories_detailed",
        lambda _config, _token: (
            ["platformcontext/payments-api"],
            [],
            1,
            0,
        ),
        raising=False,
    )
    monkeypatch.setattr(
        sync,
        "update_existing_repositories_detailed",
        lambda _config, _token: ([], 0),
        raising=False,
    )
    monkeypatch.setattr(
        sync,
        "resumable_repository_paths",
        lambda _workspace: [],
        raising=False,
    )
    monkeypatch.setattr(
        sync,
        "graph_missing_repository_paths",
        lambda repo_paths: [path for path in repo_paths if path == repo_a.resolve()],
        raising=False,
    )

    def _index_workspace(
        workspace: Path,
        *,
        selected_repositories: list[Path] | None = None,
        **_kwargs,
    ) -> None:
        captured["workspace"] = workspace
        captured["selected_repositories"] = selected_repositories

    result = sync.run_repo_sync_cycle(config, index_workspace=_index_workspace)

    assert captured["workspace"] == repos_dir
    assert captured["selected_repositories"] == [repo_a.resolve()]
    assert result.indexed == 1
