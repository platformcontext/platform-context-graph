"""Tests for repo-sync backfill request consumption."""

from __future__ import annotations

import importlib
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from platform_context_graph.facts.work_queue.models import FactBackfillRequestRow


def _config(repo_sync: object, repos_dir: Path):
    """Build a GitHub-org repo sync config for tests."""

    return repo_sync.RepoSyncConfig(
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


def test_repo_sync_cycle_forces_reindex_for_pending_repository_backfill(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A pending repository backfill should force reindex without Git changes."""

    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")
    sync = importlib.import_module("platform_context_graph.runtime.ingester.sync")

    repos_dir = tmp_path / "workspace" / "repos"
    repo_a = repos_dir / "platformcontext" / "payments-api"
    (repo_a / ".git").mkdir(parents=True)

    @contextmanager
    def _workspace_lock(_config):
        yield True

    @contextmanager
    def _index_cycle(**_kwargs):
        yield

    queue = MagicMock()
    queue.enabled = True
    queue._record_operation.side_effect = (
        lambda *, operation, callback, row_count=None: callback()
    )
    queue._fetchall.side_effect = [
        [
            {
                "backfill_request_id": "fact-backfill:1",
                "repository_id": "repository:r_payments",
                "source_run_id": None,
                "operator_note": "refresh repo",
                "created_at": None,
            }
        ],
        [{"backfill_request_id": "fact-backfill:1"}],
    ]
    captured: dict[str, object] = {}

    monkeypatch.setattr(sync, "initialize_observability", lambda **_kwargs: None)
    monkeypatch.setattr(sync, "workspace_lock", _workspace_lock)
    monkeypatch.setattr(sync, "begin_index_cycle", _index_cycle)
    monkeypatch.setattr(sync, "record_phase", lambda **_kwargs: None)
    monkeypatch.setattr(sync, "git_token", lambda _config: "token")
    monkeypatch.setattr(sync, "get_fact_work_queue", lambda: queue, raising=False)
    monkeypatch.setattr(
        sync,
        "repository_id_for_path",
        lambda path: "repository:r_payments" if path == repo_a.resolve() else "other",
        raising=False,
    )
    monkeypatch.setattr(
        sync,
        "clone_missing_repositories_detailed",
        lambda _config, _token: (["platformcontext/payments-api"], [], 1, 0),
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
        "graph_recovery_repository_paths",
        lambda _repo_paths: [],
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

    result = sync.run_repo_sync_cycle(
        _config(repo_sync, repos_dir),
        index_workspace=_index_workspace,
    )

    assert captured["workspace"] == repos_dir
    assert captured["selected_repositories"] == [repo_a.resolve()]
    assert result.indexed == 1
    assert queue._fetchall.call_count == 2


def test_repo_sync_cycle_clears_backfill_after_source_run_reindex(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A satisfied source-run backfill should be cleared after successful indexing."""

    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")
    sync = importlib.import_module("platform_context_graph.runtime.ingester.sync")

    repos_dir = tmp_path / "workspace" / "repos"
    repo_a = repos_dir / "platformcontext" / "payments-api"
    (repo_a / ".git").mkdir(parents=True)

    @contextmanager
    def _workspace_lock(_config):
        yield True

    @contextmanager
    def _index_cycle(**_kwargs):
        yield

    queue = MagicMock()
    queue.enabled = True
    queue._record_operation.side_effect = (
        lambda *, operation, callback, row_count=None: callback()
    )
    queue._fetchall.side_effect = [
        [
            {
                "backfill_request_id": "fact-backfill:1",
                "repository_id": None,
                "source_run_id": "run-123",
                "operator_note": "refresh source run",
                "created_at": None,
            }
        ],
        [{"repository_id": "repository:r_payments"}],
        [{"backfill_request_id": "fact-backfill:1"}],
    ]

    monkeypatch.setattr(sync, "initialize_observability", lambda **_kwargs: None)
    monkeypatch.setattr(sync, "workspace_lock", _workspace_lock)
    monkeypatch.setattr(sync, "begin_index_cycle", _index_cycle)
    monkeypatch.setattr(sync, "record_phase", lambda **_kwargs: None)
    monkeypatch.setattr(sync, "git_token", lambda _config: "token")
    monkeypatch.setattr(sync, "get_fact_work_queue", lambda: queue, raising=False)
    monkeypatch.setattr(
        sync,
        "repository_id_for_path",
        lambda path: "repository:r_payments" if path == repo_a.resolve() else "other",
        raising=False,
    )
    monkeypatch.setattr(
        sync,
        "clone_missing_repositories_detailed",
        lambda _config, _token: (["platformcontext/payments-api"], [], 1, 0),
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
        "graph_recovery_repository_paths",
        lambda _repo_paths: [],
        raising=False,
    )

    result = sync.run_repo_sync_cycle(
        _config(repo_sync, repos_dir),
        index_workspace=lambda _workspace, **_kwargs: None,
    )

    assert result.indexed == 1
    assert queue._fetchall.call_count == 3


def test_repo_sync_cycle_leaves_unmatched_backfill_pending(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Unmatched backfills should stay pending and avoid forced indexing."""

    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")
    sync = importlib.import_module("platform_context_graph.runtime.ingester.sync")

    repos_dir = tmp_path / "workspace" / "repos"
    repo_a = repos_dir / "platformcontext" / "payments-api"
    (repo_a / ".git").mkdir(parents=True)
    logs: list[str] = []

    @contextmanager
    def _workspace_lock(_config):
        yield True

    @contextmanager
    def _index_cycle(**_kwargs):
        yield

    queue = MagicMock()
    queue.enabled = True
    queue._record_operation.side_effect = (
        lambda *, operation, callback, row_count=None: callback()
    )
    queue._fetchall.return_value = [
        {
            "backfill_request_id": "fact-backfill:1",
            "repository_id": "repository:r_orders",
            "source_run_id": None,
            "operator_note": "refresh repo",
            "created_at": None,
        }
    ]

    monkeypatch.setattr(sync, "initialize_observability", lambda **_kwargs: None)
    monkeypatch.setattr(sync, "workspace_lock", _workspace_lock)
    monkeypatch.setattr(sync, "begin_index_cycle", _index_cycle)
    monkeypatch.setattr(sync, "record_phase", lambda **_kwargs: None)
    monkeypatch.setattr(sync, "git_token", lambda _config: "token")
    monkeypatch.setattr(sync, "get_fact_work_queue", lambda: queue, raising=False)
    monkeypatch.setattr(
        sync,
        "repository_id_for_path",
        lambda path: "repository:r_payments" if path == repo_a.resolve() else "other",
        raising=False,
    )
    monkeypatch.setattr(
        sync,
        "log",
        lambda _component, message: logs.append(message),
        raising=False,
    )
    monkeypatch.setattr(
        sync,
        "clone_missing_repositories_detailed",
        lambda _config, _token: (["platformcontext/payments-api"], [], 1, 0),
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
        "graph_recovery_repository_paths",
        lambda _repo_paths: [],
        raising=False,
    )

    result = sync.run_repo_sync_cycle(
        _config(repo_sync, repos_dir),
        index_workspace=lambda _workspace, **_kwargs: None,
    )

    assert result.indexed == 0
    assert any(
        "Leaving pending fact backfill request(s) unresolved" in log for log in logs
    )
    assert queue._fetchall.call_count == 1


def test_repo_sync_cycle_keeps_backfill_pending_when_indexing_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Failed indexing should not clear matched backfill requests."""

    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")
    sync = importlib.import_module("platform_context_graph.runtime.ingester.sync")

    repos_dir = tmp_path / "workspace" / "repos"
    repo_a = repos_dir / "platformcontext" / "payments-api"
    (repo_a / ".git").mkdir(parents=True)

    @contextmanager
    def _workspace_lock(_config):
        yield True

    @contextmanager
    def _index_cycle(**_kwargs):
        yield

    queue = MagicMock()
    queue.enabled = True
    queue._record_operation.side_effect = (
        lambda *, operation, callback, row_count=None: callback()
    )
    queue._fetchall.return_value = [
        {
            "backfill_request_id": "fact-backfill:1",
            "repository_id": "repository:r_payments",
            "source_run_id": None,
            "operator_note": "refresh repo",
            "created_at": None,
        }
    ]

    monkeypatch.setattr(sync, "initialize_observability", lambda **_kwargs: None)
    monkeypatch.setattr(sync, "workspace_lock", _workspace_lock)
    monkeypatch.setattr(sync, "begin_index_cycle", _index_cycle)
    monkeypatch.setattr(sync, "record_phase", lambda **_kwargs: None)
    monkeypatch.setattr(sync, "git_token", lambda _config: "token")
    monkeypatch.setattr(sync, "get_fact_work_queue", lambda: queue, raising=False)
    monkeypatch.setattr(
        sync,
        "repository_id_for_path",
        lambda path: "repository:r_payments" if path == repo_a.resolve() else "other",
        raising=False,
    )
    monkeypatch.setattr(
        sync,
        "clone_missing_repositories_detailed",
        lambda _config, _token: (["platformcontext/payments-api"], [], 1, 0),
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
        "graph_recovery_repository_paths",
        lambda _repo_paths: [],
        raising=False,
    )

    def _raise_index_failure(_workspace: Path, **_kwargs) -> None:
        raise RuntimeError("indexing failed")

    with pytest.raises(RuntimeError, match="indexing failed"):
        sync.run_repo_sync_cycle(
            _config(repo_sync, repos_dir),
            index_workspace=_raise_index_failure,
        )

    assert queue._fetchall.call_count == 1


def test_plan_repo_sync_backfills_reuses_source_run_lookup_per_cycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Planning should query each source run at most once per cycle."""

    backfill_requests = importlib.import_module(
        "platform_context_graph.runtime.ingester.backfill_requests"
    )

    repos_dir = tmp_path / "workspace" / "repos"
    repo_a = repos_dir / "platformcontext" / "payments-api"
    repo_b = repos_dir / "platformcontext" / "orders-api"
    repo_a.mkdir(parents=True)
    repo_b.mkdir(parents=True)

    source_run_calls: list[str] = []
    queue = MagicMock()
    queue.enabled = True

    monkeypatch.setattr(
        backfill_requests,
        "list_backfill_requests",
        lambda _queue: [
            FactBackfillRequestRow(
                backfill_request_id="fact-backfill:1",
                source_run_id="run-123",
            ),
            FactBackfillRequestRow(
                backfill_request_id="fact-backfill:2",
                source_run_id="run-123",
            ),
        ],
    )
    monkeypatch.setattr(
        backfill_requests,
        "list_repository_ids_for_source_run",
        lambda _queue, *, source_run_id: (
            source_run_calls.append(source_run_id)
            or ["repository:r_orders", "repository:r_payments"]
        ),
    )

    selection = backfill_requests.plan_repo_sync_backfills(
        discovered_repository_paths=[repo_a, repo_b],
        get_fact_work_queue_fn=lambda: queue,
        repository_id_for_path_fn=lambda path: (
            "repository:r_payments"
            if path == repo_a.resolve()
            else "repository:r_orders"
        ),
    )

    assert selection.forced_repositories == (repo_b.resolve(), repo_a.resolve())
    assert selection.satisfiable_request_ids == (
        "fact-backfill:1",
        "fact-backfill:2",
    )
    assert source_run_calls == ["run-123"]
