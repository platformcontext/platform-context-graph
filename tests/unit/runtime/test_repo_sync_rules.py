"""Tests for repo-sync rule parsing and Git rediscovery behavior."""

from __future__ import annotations

import contextlib
import importlib
import json
from pathlib import Path

import pytest

from platform_context_graph.runtime.ingester.config import RepoSyncRepositoryRule


class _FakeResponse:
    """Minimal requests response used to stub GitHub discovery."""

    def __init__(self, payload: list[dict[str, str]]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        """Pretend the response was successful."""

    def json(self) -> list[dict[str, str]]:
        """Return the stubbed JSON payload."""

        return self._payload


def test_config_from_env_merges_structured_and_legacy_repository_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Merge structured rules with the deprecated exact shorthand."""

    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")

    monkeypatch.setenv(
        "PCG_REPOSITORY_RULES_JSON",
        json.dumps(
            [
                {"type": "exact", "value": "org/service-a"},
                {"type": "regex", "value": r"^org/service-[bc]$"},
            ]
        ),
    )
    monkeypatch.setenv("PCG_REPOSITORIES", "org/legacy-one,org/legacy-two")

    config = repo_sync.RepoSyncConfig.from_env(component="repo-sync")

    assert config.repositories == ["org/legacy-one", "org/legacy-two"]
    assert config.repository_rules == (
        RepoSyncRepositoryRule(kind="exact", value="org/service-a"),
        RepoSyncRepositoryRule(kind="regex", value=r"^org/service-[bc]$"),
        RepoSyncRepositoryRule(kind="exact", value="org/legacy-one"),
        RepoSyncRepositoryRule(kind="exact", value="org/legacy-two"),
    )


def test_git_discovery_applies_exact_and_regex_include_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Filter GitHub discovery results using mixed exact and regex rules."""

    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")
    git = importlib.import_module("platform_context_graph.runtime.ingester.git")

    config = repo_sync.RepoSyncConfig(
        repos_dir=Path("/tmp/repos"),
        source_mode="githubOrg",
        git_auth_method="token",
        github_org="org",
        repositories=[],
        filesystem_root=None,
        clone_depth=1,
        repo_limit=20,
        sync_lock_dir=Path("/tmp/repos/.pcg-sync.lock"),
        component="repo-sync",
        repository_rules=(
            RepoSyncRepositoryRule(kind="exact", value="org/service-a"),
            RepoSyncRepositoryRule(kind="regex", value=r"^org/service-[bc]$"),
        ),
    )

    page_calls: list[int] = []

    def fake_request(
        _method: str,
        _url: str,
        *,
        headers: dict[str, str],
        params: dict[str, object],
        timeout: int,
    ) -> _FakeResponse:
        del headers, timeout
        page_calls.append(int(params["page"]))
        if params["page"] == 1:
            return _FakeResponse(
                [
                    {"full_name": "org/service-a"},
                    {"full_name": "org/service-b"},
                    {"full_name": "org/service-c"},
                    {"full_name": "org/other"},
                ]
            )
        return _FakeResponse([])

    monkeypatch.setattr(git, "github_api_request", fake_request)

    assert git.list_repo_identifiers(config, token="token") == [
        "org/service-a",
        "org/service-b",
        "org/service-c",
    ]
    assert page_calls == [1, 2]


def test_explicit_source_mode_uses_exact_repositories_only() -> None:
    """Explicit mode should ignore regex rules and use the exact repository list."""

    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")
    git = importlib.import_module("platform_context_graph.runtime.ingester.git")

    config = repo_sync.RepoSyncConfig(
        repos_dir=Path("/tmp/repos"),
        source_mode="explicit",
        git_auth_method="token",
        github_org="org",
        repositories=["org/service-a", "org/service-b"],
        filesystem_root=None,
        clone_depth=1,
        repo_limit=20,
        sync_lock_dir=Path("/tmp/repos/.pcg-sync.lock"),
        component="workspace-plan",
        repository_rules=(
            RepoSyncRepositoryRule(kind="regex", value=r"^org/ignored-.*$"),
        ),
    )

    assert git.list_repo_identifiers(config, token="token") == [
        "org/service-a",
        "org/service-b",
    ]


def test_workspace_plan_filesystem_mode_does_not_require_github_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Filesystem workspace planning should not depend on GitHub auth config."""

    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")
    git = importlib.import_module("platform_context_graph.runtime.ingester.git")

    filesystem_root = tmp_path / "fixtures"
    (filesystem_root / "service-a").mkdir(parents=True)
    (filesystem_root / "service-b").mkdir(parents=True)

    config = repo_sync.RepoSyncConfig(
        repos_dir=tmp_path / "workspace" / "repos",
        source_mode="filesystem",
        git_auth_method="githubApp",
        github_org=None,
        repositories=[],
        filesystem_root=filesystem_root,
        clone_depth=1,
        repo_limit=20,
        sync_lock_dir=tmp_path / "workspace" / "repos" / ".pcg-sync.lock",
        component="workspace-plan",
    )

    monkeypatch.setattr(
        git,
        "git_token",
        lambda _config: pytest.fail("filesystem planning should not request Git auth"),
    )

    plan = git.build_workspace_plan(config)

    assert plan["repos_dir"] == str(config.repos_dir)
    assert plan["repository_ids"] == ["service-a", "service-b"]
    assert plan["matched_repositories"] == 2


def test_filesystem_mode_preserves_nested_repository_paths(
    tmp_path: Path,
) -> None:
    """Filesystem mode should preserve relative repo paths from the source root."""

    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")
    git = importlib.import_module("platform_context_graph.runtime.ingester.git")

    filesystem_root = tmp_path / "fixtures"
    nested_repo = filesystem_root / "org" / "repo"
    nested_repo.mkdir(parents=True)
    (nested_repo / "main.py").write_text("print('nested')\n", encoding="utf-8")

    config = repo_sync.RepoSyncConfig(
        repos_dir=tmp_path / "workspace" / "repos",
        source_mode="filesystem",
        git_auth_method="none",
        github_org=None,
        repositories=["org/repo"],
        filesystem_root=filesystem_root,
        clone_depth=1,
        repo_limit=20,
        sync_lock_dir=tmp_path / "workspace" / "repos" / ".pcg-sync.lock",
        component="workspace-plan",
    )

    assert git.list_repo_identifiers(config, token=None) == ["org/repo"]

    discovered = git.filesystem_sync_all(config)

    assert discovered == ["org/repo"]
    assert (config.repos_dir / "org" / "repo" / "main.py").exists()


def test_filesystem_mode_auto_discovers_nested_repository_paths(
    tmp_path: Path,
) -> None:
    """Filesystem mode should recursively discover nested repo roots."""

    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")
    git = importlib.import_module("platform_context_graph.runtime.ingester.git")

    filesystem_root = tmp_path / "fixtures"
    nested_repo = filesystem_root / "boatsgroup" / "api-bridge"
    nested_repo.mkdir(parents=True)
    (nested_repo / ".git").mkdir()
    (nested_repo / "main.py").write_text("print('nested')\n", encoding="utf-8")

    config = repo_sync.RepoSyncConfig(
        repos_dir=tmp_path / "workspace" / "repos",
        source_mode="filesystem",
        git_auth_method="none",
        github_org=None,
        repositories=[],
        filesystem_root=filesystem_root,
        clone_depth=1,
        repo_limit=20,
        sync_lock_dir=tmp_path / "workspace" / "repos" / ".pcg-sync.lock",
        component="workspace-plan",
    )

    discovered = git.list_repo_identifiers(config, token=None)

    assert discovered == ["boatsgroup/api-bridge"]


def test_workspace_plan_counts_nested_managed_checkouts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Workspace planning should count nested managed repos and stale siblings."""

    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")
    git = importlib.import_module("platform_context_graph.runtime.ingester.git")

    repos_dir = tmp_path / "workspace" / "repos"
    nested_repo = repos_dir / "boatsgroup" / "devops-captain"
    stale_repo = repos_dir / "boatsgroup" / "legacy-service"
    (nested_repo / ".git").mkdir(parents=True)
    (stale_repo / ".git").mkdir(parents=True)

    config = repo_sync.RepoSyncConfig(
        repos_dir=repos_dir,
        source_mode="githubOrg",
        git_auth_method="githubApp",
        github_org="boatsgroup",
        repositories=[],
        filesystem_root=None,
        clone_depth=1,
        repo_limit=20,
        sync_lock_dir=repos_dir / ".pcg-sync.lock",
        component="workspace-plan",
    )

    monkeypatch.setattr(git, "git_token", lambda _config: "token")
    monkeypatch.setattr(
        git,
        "list_repo_identifiers",
        lambda _config, _token: ["boatsgroup/devops-captain"],
    )

    plan = git.build_workspace_plan(config)

    assert plan["repository_ids"] == ["boatsgroup/devops-captain"]
    assert plan["already_cloned"] == 1
    assert plan["stale_checkouts"] == 1


def test_git_repo_sync_cycle_rediscoveries_and_indexes_only_on_change(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Rediscover matching repos and reindex only after clone or update changes."""

    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")
    sync = importlib.import_module("platform_context_graph.runtime.ingester.sync")

    repos_dir = tmp_path / "repos"
    existing_repo = repos_dir / "service-a"
    (existing_repo / ".git").mkdir(parents=True)

    config = repo_sync.RepoSyncConfig(
        repos_dir=repos_dir,
        source_mode="githubOrg",
        git_auth_method="token",
        github_org="org",
        repositories=[],
        filesystem_root=None,
        clone_depth=1,
        repo_limit=20,
        sync_lock_dir=repos_dir / ".pcg-sync.lock",
        component="repo-sync",
        repository_rules=(
            RepoSyncRepositoryRule(kind="exact", value="org/service-a"),
            RepoSyncRepositoryRule(kind="regex", value=r"^org/service-b$"),
        ),
    )

    calls: list[str] = []
    index_calls: list[Path] = []

    def fake_clone_missing_repositories_detailed(
        _config: object, _token: object
    ) -> tuple[list[str], list[Path], int, int]:
        calls.append("clone")
        cloned_repo = repos_dir / "service-b"
        (cloned_repo / ".git").mkdir(parents=True, exist_ok=True)
        return (["org/service-a", "org/service-b"], [cloned_repo.resolve()], 1, 0)

    def fake_update_existing_repositories_detailed(
        _config: object, _token: object
    ) -> tuple[list[Path], int]:
        calls.append("update")
        return ([existing_repo.resolve()], 0)

    monkeypatch.setattr(
        sync,
        "clone_missing_repositories_detailed",
        fake_clone_missing_repositories_detailed,
        raising=False,
    )
    monkeypatch.setattr(
        sync,
        "update_existing_repositories_detailed",
        fake_update_existing_repositories_detailed,
        raising=False,
    )
    monkeypatch.setattr(
        sync, "workspace_lock", lambda _config: contextlib.nullcontext(True)
    )
    monkeypatch.setattr(
        sync, "begin_index_cycle", lambda **_kwargs: contextlib.nullcontext()
    )
    monkeypatch.setattr(sync, "initialize_observability", lambda **_kwargs: None)

    result = sync.run_repo_sync_cycle(
        config,
        index_workspace=lambda workspace: index_calls.append(workspace),
    )

    assert calls == ["clone", "update"]
    assert index_calls == [repos_dir]
    assert result.discovered == 2
    assert result.cloned == 1
    assert result.updated == 1
    assert result.skipped == 1
    assert result.failed == 0
    assert result.indexed == 2


def test_git_repo_sync_cycle_skips_reindex_when_no_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Skip the reindex pass when rediscovery finds no material changes."""

    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")
    sync = importlib.import_module("platform_context_graph.runtime.ingester.sync")

    repos_dir = tmp_path / "repos"
    (repos_dir / "service-a" / ".git").mkdir(parents=True)

    config = repo_sync.RepoSyncConfig(
        repos_dir=repos_dir,
        source_mode="githubOrg",
        git_auth_method="token",
        github_org="org",
        repositories=[],
        filesystem_root=None,
        clone_depth=1,
        repo_limit=20,
        sync_lock_dir=repos_dir / ".pcg-sync.lock",
        component="repo-sync",
        repository_rules=(RepoSyncRepositoryRule(kind="exact", value="org/service-a"),),
    )

    calls: list[str] = []
    index_calls: list[Path] = []

    def fake_clone_missing_repositories_detailed(
        _config: object, _token: object
    ) -> tuple[list[str], list[Path], int, int]:
        calls.append("clone")
        return (["org/service-a"], [], 1, 0)

    def fake_update_existing_repositories_detailed(
        _config: object, _token: object
    ) -> tuple[list[Path], int]:
        calls.append("update")
        return ([], 0)

    monkeypatch.setattr(
        sync,
        "clone_missing_repositories_detailed",
        fake_clone_missing_repositories_detailed,
        raising=False,
    )
    monkeypatch.setattr(
        sync,
        "update_existing_repositories_detailed",
        fake_update_existing_repositories_detailed,
        raising=False,
    )
    monkeypatch.setattr(
        sync, "workspace_lock", lambda _config: contextlib.nullcontext(True)
    )
    monkeypatch.setattr(
        sync, "begin_index_cycle", lambda **_kwargs: contextlib.nullcontext()
    )
    monkeypatch.setattr(sync, "initialize_observability", lambda **_kwargs: None)

    result = sync.run_repo_sync_cycle(
        config,
        index_workspace=lambda workspace: index_calls.append(workspace),
    )

    assert calls == ["clone", "update"]
    assert index_calls == []
    assert result.discovered == 1
    assert result.skipped == 1
    assert result.failed == 0
    assert result.indexed == 0
