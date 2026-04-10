"""Tests for archived-repository repo-sync behavior."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


class _FakeResponse:
    """Minimal GitHub API response stub."""

    def __init__(self, payload: list[dict[str, object]]) -> None:
        """Store the response payload."""

        self._payload = payload

    def raise_for_status(self) -> None:
        """Pretend the request succeeded."""

    def json(self) -> list[dict[str, object]]:
        """Return the configured payload."""

        return self._payload


def _paged_request(payload: list[dict[str, object]]):
    """Return a GitHub API stub that emits one populated page then stops."""

    def _request(
        _method: str,
        _url: str,
        *,
        headers: dict[str, str],
        params: dict[str, object],
        timeout: int,
    ) -> _FakeResponse:
        del headers, timeout
        if int(params["page"]) == 1:
            return _FakeResponse(payload)
        return _FakeResponse([])

    return _request


def test_github_discovery_skips_archived_repositories_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GitHub org discovery should ignore archived repositories by default."""

    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")
    git = importlib.import_module("platform_context_graph.runtime.ingester.git")
    selection = importlib.import_module(
        "platform_context_graph.runtime.ingester.repository_selection"
    )

    monkeypatch.setenv("PCG_GITHUB_ORG", "boatsgroup")
    monkeypatch.delenv("PCG_INCLUDE_ARCHIVED_REPOS", raising=False)

    config = repo_sync.RepoSyncConfig.from_env(component="repo-sync")

    monkeypatch.setattr(
        selection,
        "github_api_request",
        _paged_request(
            [
                {"full_name": "boatsgroup/active-repo", "archived": False},
                {"full_name": "boatsgroup/lib-url-yachtworld", "archived": True},
            ]
        ),
    )

    assert git.list_repo_identifiers(config, token="token") == [
        "boatsgroup/active-repo"
    ]


def test_github_discovery_includes_archived_repositories_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GitHub org discovery should include archived repositories when enabled."""

    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")
    git = importlib.import_module("platform_context_graph.runtime.ingester.git")
    selection = importlib.import_module(
        "platform_context_graph.runtime.ingester.repository_selection"
    )

    monkeypatch.setenv("PCG_GITHUB_ORG", "boatsgroup")
    monkeypatch.setenv("PCG_INCLUDE_ARCHIVED_REPOS", "true")

    config = repo_sync.RepoSyncConfig.from_env(component="repo-sync")

    monkeypatch.setattr(
        selection,
        "github_api_request",
        _paged_request(
            [
                {"full_name": "boatsgroup/active-repo", "archived": False},
                {"full_name": "boatsgroup/lib-url-yachtworld", "archived": True},
            ]
        ),
    )

    assert git.list_repo_identifiers(config, token="token") == [
        "boatsgroup/active-repo",
        "boatsgroup/lib-url-yachtworld",
    ]


def test_exact_repository_rules_can_include_archived_repositories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exact rules should override the archived-repository default exclusion."""

    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")
    git = importlib.import_module("platform_context_graph.runtime.ingester.git")
    selection = importlib.import_module(
        "platform_context_graph.runtime.ingester.repository_selection"
    )

    monkeypatch.setenv("PCG_GITHUB_ORG", "boatsgroup")
    monkeypatch.setenv(
        "PCG_REPOSITORY_RULES_JSON",
        json.dumps(
            [
                {
                    "type": "exact",
                    "value": "boatsgroup/lib-url-yachtworld",
                }
            ]
        ),
    )

    config = repo_sync.RepoSyncConfig.from_env(component="repo-sync")

    monkeypatch.setattr(
        selection,
        "github_api_request",
        _paged_request(
            [
                {"full_name": "boatsgroup/active-repo", "archived": False},
                {"full_name": "boatsgroup/lib-url-yachtworld", "archived": True},
            ]
        ),
    )

    assert git.list_repo_identifiers(config, token="token") == [
        "boatsgroup/lib-url-yachtworld"
    ]


def test_regex_rules_do_not_override_archived_repository_exclusion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regex rules should not force archived repositories into sync selection."""

    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")
    git = importlib.import_module("platform_context_graph.runtime.ingester.git")
    selection = importlib.import_module(
        "platform_context_graph.runtime.ingester.repository_selection"
    )

    monkeypatch.setenv("PCG_GITHUB_ORG", "boatsgroup")
    monkeypatch.setenv(
        "PCG_REPOSITORY_RULES_JSON",
        json.dumps(
            [
                {
                    "type": "regex",
                    "value": r"^boatsgroup/lib-url-.*$",
                }
            ]
        ),
    )

    config = repo_sync.RepoSyncConfig.from_env(component="repo-sync")

    monkeypatch.setattr(
        selection,
        "github_api_request",
        _paged_request(
            [
                {"full_name": "boatsgroup/lib-url-yachtworld", "archived": True},
            ]
        ),
    )

    assert git.list_repo_identifiers(config, token="token") == []


def test_update_existing_repositories_only_updates_selected_repo_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repo updates should only touch the selected repository checkout paths."""

    git_module = importlib.import_module("platform_context_graph.runtime.ingester.git")
    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")

    repos_dir = tmp_path / "workspace" / "repos"
    selected_repo = repos_dir / "boatsgroup" / "active-repo"
    skipped_repo = repos_dir / "boatsgroup" / "archived-repo"
    (selected_repo / ".git").mkdir(parents=True)
    (skipped_repo / ".git").mkdir(parents=True)

    config = repo_sync.RepoSyncConfig(
        repos_dir=repos_dir,
        source_mode="githubOrg",
        git_auth_method="none",
        github_org="boatsgroup",
        repositories=[],
        filesystem_root=None,
        clone_depth=1,
        repo_limit=100,
        sync_lock_dir=repos_dir / ".pcg-sync.lock",
        component="repository",
    )

    commands: list[list[str]] = []

    def _run(command, **_kwargs):  # type: ignore[no-untyped-def]
        commands.append(command)
        if command[3:4] == ["symbolic-ref"]:
            return SimpleNamespace(
                returncode=0,
                stdout="refs/remotes/origin/main\n",
                stderr="",
            )
        if command[3:4] == ["fetch"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[3:] == ["rev-parse", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout="same-head\n", stderr="")
        if command[3:] == ["rev-parse", "refs/remotes/origin/main"]:
            return SimpleNamespace(returncode=0, stdout="same-head\n", stderr="")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(git_module.subprocess, "run", _run)

    updated, failed = git_module.update_existing_repositories_detailed(
        config,
        None,
        selected_repository_ids=["boatsgroup/active-repo"],
    )

    assert updated == []
    assert failed == 0
    touched_paths = {command[2] for command in commands}
    assert str(selected_repo) in touched_paths
    assert str(skipped_repo) not in touched_paths


def test_update_existing_repositories_fetches_remote_tracking_ref_and_ignores_set_head_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful fetch/reset should not warn when `remote set-head` healing fails."""

    git_module = importlib.import_module("platform_context_graph.runtime.ingester.git")
    git_sync_ops = importlib.import_module(
        "platform_context_graph.runtime.ingester.git_sync_ops"
    )
    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")

    repos_dir = tmp_path / "workspace" / "repos"
    repo_dir = repos_dir / "boatsgroup" / "active-repo"
    (repo_dir / ".git").mkdir(parents=True)

    config = repo_sync.RepoSyncConfig(
        repos_dir=repos_dir,
        source_mode="githubOrg",
        git_auth_method="none",
        github_org="boatsgroup",
        repositories=[],
        filesystem_root=None,
        clone_depth=1,
        repo_limit=100,
        sync_lock_dir=repos_dir / ".pcg-sync.lock",
        component="repository",
    )

    fetch_calls: list[list[str]] = []
    warnings: list[str] = []

    def _run(command, **_kwargs):  # type: ignore[no-untyped-def]
        if command[3:4] == ["symbolic-ref"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        if command[3:5] == ["ls-remote", "--symref"]:
            return SimpleNamespace(
                returncode=0,
                stdout="ref: refs/heads/main\tHEAD\n95fe482\tHEAD\n",
                stderr="",
            )
        if command[3:4] == ["fetch"]:
            fetch_calls.append(command)
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[3:5] == ["remote", "set-head"]:
            return SimpleNamespace(
                returncode=1,
                stdout="",
                stderr="error: Not a valid ref: refs/remotes/origin/main",
            )
        if command[3:] == ["rev-parse", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout="same-head\n", stderr="")
        if command[3:] == ["rev-parse", "refs/remotes/origin/main"]:
            return SimpleNamespace(returncode=0, stdout="same-head\n", stderr="")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(git_module.subprocess, "run", _run)
    monkeypatch.setattr(git_sync_ops, "warning_logger", warnings.append)

    updated, failed = git_module.update_existing_repositories_detailed(
        config,
        None,
        selected_repository_ids=["boatsgroup/active-repo"],
    )

    assert updated == []
    assert failed == 0
    assert fetch_calls == [
        [
            "git",
            "-C",
            str(repo_dir),
            "fetch",
            "origin",
            "+refs/heads/main:refs/remotes/origin/main",
            "--depth=1",
        ]
    ]
    assert warnings == []
