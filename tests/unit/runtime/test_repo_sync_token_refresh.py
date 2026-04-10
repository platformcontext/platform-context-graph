"""Regression coverage for per-repository Git auth refresh during repo sync."""

from __future__ import annotations

import base64
import importlib
from pathlib import Path
from types import SimpleNamespace


def _github_app_config(tmp_path: Path):
    """Return a repo-sync config that uses GitHub App authentication."""

    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")
    repos_dir = tmp_path / "workspace" / "repos"
    return repo_sync.RepoSyncConfig(
        repos_dir=repos_dir,
        source_mode="githubOrg",
        git_auth_method="githubApp",
        github_org="boatsgroup",
        repositories=[],
        filesystem_root=None,
        clone_depth=1,
        repo_limit=100,
        sync_lock_dir=repos_dir / ".pcg-sync.lock",
        component="repository",
    )


def _decode_extraheader(env: dict[str, str]) -> str:
    """Return the decoded GitHub App token from a Git extraheader env."""

    config_count = int(env.get("GIT_CONFIG_COUNT", "0"))
    for index in range(config_count):
        if env.get(f"GIT_CONFIG_KEY_{index}") == "http.https://github.com/.extraheader":
            header = env[f"GIT_CONFIG_VALUE_{index}"]
            encoded = header.removeprefix("AUTHORIZATION: basic ")
            return base64.b64decode(encoded).decode("utf-8")
    raise KeyError("http.https://github.com/.extraheader")


def test_clone_missing_repositories_builds_git_env_for_each_repository(
    tmp_path: Path,
) -> None:
    """Clone loops should rebuild Git auth env inside the per-repo loop."""

    git_sync_ops = importlib.import_module(
        "platform_context_graph.runtime.ingester.git_sync_ops"
    )
    config = _github_app_config(tmp_path)

    env_calls: list[str | None] = []

    def _git_env(_config, token):
        env_calls.append(token)
        return {"TOKEN": str(token)}

    def _run(*_args, **_kwargs):
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    discovered, cloned_paths, skipped, failed = (
        git_sync_ops.clone_missing_repositories_detailed_impl(
            config,
            "stale-token",
            repository_ids=[
                "boatsgroup/alpha",
                "boatsgroup/beta",
            ],
            repo_checkout_name_fn=lambda repo_id: repo_id.split("/", maxsplit=1)[1],
            repo_remote_url_fn=lambda *_args: "https://github.com/boatsgroup/repo.git",
            git_env_fn=_git_env,
            subprocess_run_fn=_run,
        )
    )

    assert discovered == ["boatsgroup/alpha", "boatsgroup/beta"]
    assert [path.name for path in cloned_paths] == ["alpha", "beta"]
    assert skipped == 0
    assert failed == 0
    assert env_calls == ["stale-token", "stale-token"]


def test_update_existing_repositories_builds_git_env_for_each_repository(
    tmp_path: Path,
) -> None:
    """Update loops should rebuild Git auth env for each managed repository."""

    git_sync_ops = importlib.import_module(
        "platform_context_graph.runtime.ingester.git_sync_ops"
    )
    config = _github_app_config(tmp_path)
    alpha_dir = config.repos_dir / "alpha"
    beta_dir = config.repos_dir / "beta"
    (alpha_dir / ".git").mkdir(parents=True)
    (beta_dir / ".git").mkdir(parents=True)

    env_calls: list[str | None] = []

    def _git_env(_config, token):
        env_calls.append(token)
        return {"TOKEN": str(token)}

    def _run(command, **_kwargs):
        if command[3:5] == ["remote", "get-url"]:
            return SimpleNamespace(
                returncode=0,
                stdout="https://github.com/boatsgroup/repo.git\n",
                stderr="",
            )
        if command[3:4] == ["symbolic-ref"]:
            return SimpleNamespace(
                returncode=0,
                stdout="refs/remotes/origin/main\n",
                stderr="",
            )
        if command[3:4] == ["fetch"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[3:] == ["rev-parse", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout="local\n", stderr="")
        if command[3:] == ["rev-parse", "refs/remotes/origin/main"]:
            return SimpleNamespace(returncode=0, stdout="remote\n", stderr="")
        if command[3:5] == ["reset", "--hard"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(f"unexpected command: {command}")

    updated_paths, failed = git_sync_ops.update_existing_repositories_detailed_impl(
        config,
        "stale-token",
        git_env_fn=_git_env,
        refresh_repository_origin_url_fn=lambda *_args, **_kwargs: None,
        subprocess_run_fn=_run,
    )

    assert sorted(path.name for path in updated_paths) == ["alpha", "beta"]
    assert failed == 0
    assert env_calls == ["stale-token", "stale-token"]


def test_clone_missing_repositories_refreshes_github_app_token_per_operation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Clone operations should refresh GitHub App tokens for each repo."""

    git_module = importlib.import_module("platform_context_graph.runtime.ingester.git")
    config = _github_app_config(tmp_path)

    refreshed_envs: list[dict[str, str]] = []

    def _fake_impl(
        _config,
        token,
        *,
        repository_ids,
        repo_checkout_name_fn,
        repo_remote_url_fn,
        git_env_fn,
        subprocess_run_fn,
    ):
        del (
            token,
            repository_ids,
            repo_checkout_name_fn,
            repo_remote_url_fn,
            subprocess_run_fn,
        )
        refreshed_envs.append(git_env_fn(_config, "stale-token"))
        refreshed_envs.append(git_env_fn(_config, "stale-token"))
        return [], [], 0, 0

    monkeypatch.setattr(
        git_module, "clone_missing_repositories_detailed_impl", _fake_impl
    )
    monkeypatch.setattr(
        git_module,
        "github_app_token",
        lambda: f"fresh-token-{len(refreshed_envs) + 1}",
    )

    git_module.clone_missing_repositories_detailed(
        config,
        "stale-token",
        selected_repository_ids=["boatsgroup/alpha", "boatsgroup/beta"],
    )

    assert [_decode_extraheader(env) for env in refreshed_envs] == [
        "x-access-token:fresh-token-1",
        "x-access-token:fresh-token-2",
    ]


def test_update_existing_repositories_refreshes_github_app_token_per_operation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Fetch operations should refresh GitHub App tokens for each repo."""

    git_module = importlib.import_module("platform_context_graph.runtime.ingester.git")
    config = _github_app_config(tmp_path)

    refreshed_envs: list[dict[str, str]] = []

    def _fake_impl(
        _config,
        token,
        *,
        force_default_branch_refresh,
        selected_repository_paths,
        git_env_fn,
        refresh_repository_origin_url_fn,
        subprocess_run_fn,
    ):
        del (
            token,
            force_default_branch_refresh,
            selected_repository_paths,
            refresh_repository_origin_url_fn,
            subprocess_run_fn,
        )
        refreshed_envs.append(git_env_fn(_config, "stale-token"))
        refreshed_envs.append(git_env_fn(_config, "stale-token"))
        return [], 0

    monkeypatch.setattr(
        git_module, "update_existing_repositories_detailed_impl", _fake_impl
    )
    monkeypatch.setattr(
        git_module,
        "github_app_token",
        lambda: f"fresh-token-{len(refreshed_envs) + 1}",
    )

    git_module.update_existing_repositories_detailed(config, "stale-token")

    assert [_decode_extraheader(env) for env in refreshed_envs] == [
        "x-access-token:fresh-token-1",
        "x-access-token:fresh-token-2",
    ]
