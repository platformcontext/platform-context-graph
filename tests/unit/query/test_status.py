from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from platform_context_graph.query import status as status_queries


class _Store:
    enabled = True

    def __init__(self, payload):
        self._payload = payload

    def get_runtime_status(self, *, ingester: str):
        return self._payload.get(ingester)


class _DecisionStore:
    enabled = True


class _Queue:
    enabled = True

    def count_shared_projection_pending(self, *, source_run_id: str | None = None):
        return 0


def test_get_ingester_status_normalizes_datetime_fields(
    monkeypatch,
) -> None:
    """Runtime ingester status should serialize datetimes to ISO-8601 strings."""

    store = _Store(
        {
            "repository": {
                "runtime_family": "ingester",
                "ingester": "repository",
                "provider": "repository",
                "status": "idle",
                "last_attempt_at": datetime(2026, 3, 22, 12, 0, tzinfo=timezone.utc),
                "active_phase_started_at": datetime(
                    2026, 3, 22, 12, 0, 30, tzinfo=timezone.utc
                ),
                "active_last_progress_at": datetime(
                    2026, 3, 22, 12, 0, 45, tzinfo=timezone.utc
                ),
                "active_commit_started_at": datetime(
                    2026, 3, 22, 12, 0, 50, tzinfo=timezone.utc
                ),
                "updated_at": datetime(2026, 3, 22, 12, 1, tzinfo=timezone.utc),
            }
        }
    )
    monkeypatch.setattr(status_queries, "get_runtime_status_store", lambda: store)

    result = status_queries.get_ingester_status(object(), ingester="repository")

    assert result["last_attempt_at"] == "2026-03-22T12:00:00+00:00"
    assert result["active_phase_started_at"] == "2026-03-22T12:00:30+00:00"
    assert result["active_last_progress_at"] == "2026-03-22T12:00:45+00:00"
    assert result["active_commit_started_at"] == "2026-03-22T12:00:50+00:00"
    assert result["updated_at"] == "2026-03-22T12:01:00+00:00"


def test_get_ingester_status_surfaces_truth_summary(
    monkeypatch,
) -> None:
    """Runtime ingester status should include the reducer truth rollup."""

    store = _Store(
        {
            "repository": {
                "runtime_family": "ingester",
                "ingester": "repository",
                "provider": "repository",
                "status": "indexing",
                "active_run_id": "run-789",
                "repository_count": 3,
                "pending_repositories": 1,
                "completed_repositories": 2,
                "failed_repositories": 0,
                "updated_at": datetime(2026, 3, 22, 12, 1, tzinfo=timezone.utc),
            }
        }
    )
    monkeypatch.setattr(status_queries, "get_runtime_status_store", lambda: store)
    monkeypatch.setattr(status_queries, "get_fact_work_queue", lambda: _Queue())
    monkeypatch.setattr(
        status_queries,
        "get_projection_decision_store",
        lambda: _DecisionStore(),
    )
    monkeypatch.setattr(
        status_queries,
        "get_shared_projection_intent_store",
        lambda: None,
    )
    monkeypatch.setattr(
        status_queries,
        "_checkpoint_status_fallback",
        lambda _ingester: None,
    )

    result = status_queries.get_ingester_status(object(), ingester="repository")

    assert result["truth_summary"] == {
        "state": "healthy",
        "reducer_queue_available": True,
        "projection_decision_store_available": True,
        "pending_reducer_work_items": 0,
        "shared_projection_backlog_count": 0,
        "shared_projection_domains": [],
        "shared_projection_oldest_pending_age_seconds": 0.0,
        "reason": "reducer queue and projection decision store are ready",
    }


def test_request_ingester_scan_control_normalizes_datetime_fields(
    monkeypatch,
) -> None:
    """Manual ingester scan responses should serialize datetimes to ISO-8601 strings."""

    monkeypatch.setattr(
        status_queries,
        "request_ingester_scan",
        lambda **_kwargs: {
            "ingester": "repository",
            "scan_request_token": "scan-123",
            "scan_request_state": "pending",
            "scan_requested_at": datetime(2026, 3, 22, 12, 5, tzinfo=timezone.utc),
            "scan_requested_by": "api",
        },
    )

    result = status_queries.request_ingester_scan_control(
        object(),
        ingester="repository",
        requested_by="api",
    )

    assert result["scan_requested_at"] == "2026-03-22T12:05:00+00:00"


def test_get_ingester_status_falls_back_to_checkpointed_bootstrap_run(
    monkeypatch,
) -> None:
    """Active bootstrap runs should surface from checkpoint state when no row exists."""

    monkeypatch.setattr(status_queries, "get_runtime_status_store", lambda: None)
    monkeypatch.setattr(
        status_queries,
        "_describe_index_run",
        lambda target: {
            "run_id": "run-123",
            "status": "running",
            "created_at": "2026-03-24T12:00:00Z",
            "updated_at": "2026-03-24T12:02:00Z",
            "last_error": None,
            "repository_count": 10,
            "completed_repositories": 4,
            "failed_repositories": 1,
            "pending_repositories": 5,
            "repositories": [
                {
                    "repo_path": "/tmp/repos/payments-api",
                    "status": "running",
                    "phase": "committing",
                    "phase_started_at": "2026-03-24T12:01:30Z",
                    "current_file": "src/app.py",
                    "last_progress_at": "2026-03-24T12:01:59Z",
                    "commit_started_at": "2026-03-24T12:01:31Z",
                    "updated_at": "2026-03-24T12:01:59Z",
                }
            ],
        },
    )
    monkeypatch.setenv("PCG_REPO_SOURCE_MODE", "filesystem")
    monkeypatch.setenv("PCG_REPOS_DIR", "/tmp/repos")
    monkeypatch.setenv("PCG_FILESYSTEM_ROOT", "/tmp/source-root")

    result = status_queries.get_ingester_status(object(), ingester="repository")

    assert result["status"] == "indexing"
    assert result["active_run_id"] == "run-123"
    assert result["active_repository_path"] == "/tmp/repos/payments-api"
    assert result["active_phase"] == "committing"
    assert result["repository_count"] == 10
    assert result["completed_repositories"] == 4
    assert result["pending_repositories"] == 5


def test_checkpoint_target_prefers_working_checkout_root(monkeypatch) -> None:
    """Checkpoint lookups should use the working checkout root when configured."""

    monkeypatch.setenv("PCG_REPO_SOURCE_MODE", "filesystem")
    monkeypatch.setenv("PCG_REPOS_DIR", "/tmp/repos")
    monkeypatch.setenv("PCG_FILESYSTEM_ROOT", "/tmp/source-root")

    target = status_queries._checkpoint_target_for_ingester("repository")

    assert target is not None
    assert target == Path("/tmp/repos").resolve()


def test_get_ingester_status_prefers_checkpoint_when_store_is_bootstrap_pending(
    monkeypatch,
) -> None:
    """Bootstrap-pending runtime rows should be replaced by active checkpoint state."""

    store = _Store(
        {
            "repository": {
                "runtime_family": "ingester",
                "ingester": "repository",
                "provider": "repository",
                "status": "bootstrap_pending",
                "updated_at": datetime(2026, 3, 24, 12, 0, tzinfo=timezone.utc),
            }
        }
    )
    monkeypatch.setattr(status_queries, "get_runtime_status_store", lambda: store)
    monkeypatch.setattr(
        status_queries,
        "_describe_index_run",
        lambda target: {
            "run_id": "run-456",
            "status": "partial_failure",
            "created_at": "2026-03-24T12:00:00Z",
            "updated_at": "2026-03-24T12:05:00Z",
            "last_error": "repo failed",
            "repository_count": 3,
            "completed_repositories": 2,
            "failed_repositories": 1,
            "pending_repositories": 0,
            "repositories": [],
        },
    )
    monkeypatch.setenv("PCG_REPO_SOURCE_MODE", "githubOrg")
    monkeypatch.setenv("PCG_REPOS_DIR", "/tmp/repos")

    result = status_queries.get_ingester_status(object(), ingester="repository")

    assert result["status"] == "partial_failure"
    assert result["active_run_id"] == "run-456"
    assert result["last_error_message"] == "repo failed"


def test_get_ingester_status_prefers_newer_checkpoint_over_stale_runtime_row(
    monkeypatch,
) -> None:
    """Active checkpoint state should beat an older idle persisted runtime row."""

    store = _Store(
        {
            "repository": {
                "runtime_family": "ingester",
                "ingester": "repository",
                "provider": "repository",
                "status": "idle",
                "active_run_id": "run-old",
                "updated_at": datetime(2026, 3, 24, 12, 0, tzinfo=timezone.utc),
            }
        }
    )
    monkeypatch.setattr(status_queries, "get_runtime_status_store", lambda: store)
    monkeypatch.setattr(
        status_queries,
        "_describe_index_run",
        lambda target: {
            "run_id": "run-new",
            "status": "running",
            "created_at": "2026-03-24T12:01:00+00:00",
            "updated_at": "2026-03-24T12:05:00+00:00",
            "last_error": None,
            "repository_count": 8,
            "completed_repositories": 3,
            "failed_repositories": 0,
            "pending_repositories": 5,
            "repositories": [
                {
                    "repo_path": "/tmp/repos/orders-api",
                    "status": "running",
                    "phase": "parsed",
                    "phase_started_at": "2026-03-24T12:04:30+00:00",
                    "last_progress_at": "2026-03-24T12:05:00+00:00",
                    "updated_at": "2026-03-24T12:05:00+00:00",
                }
            ],
        },
    )
    monkeypatch.setenv("PCG_REPOS_DIR", "/tmp/repos")

    result = status_queries.get_ingester_status(object(), ingester="repository")

    assert result["status"] == "indexing"
    assert result["active_run_id"] == "run-new"
    assert result["active_repository_path"] == "/tmp/repos/orders-api"
    assert result["pending_repositories"] == 5


def test_get_ingester_status_keeps_fresher_runtime_row_when_checkpoint_is_older(
    monkeypatch,
) -> None:
    """Fresh runtime status should still win when checkpoint state lags behind it."""

    store = _Store(
        {
            "repository": {
                "runtime_family": "ingester",
                "ingester": "repository",
                "provider": "repository",
                "status": "indexing",
                "active_run_id": "run-live",
                "active_phase": "committing",
                "updated_at": datetime(2026, 3, 24, 12, 6, tzinfo=timezone.utc),
            }
        }
    )
    monkeypatch.setattr(status_queries, "get_runtime_status_store", lambda: store)
    monkeypatch.setattr(
        status_queries,
        "_describe_index_run",
        lambda target: {
            "run_id": "run-old",
            "status": "running",
            "created_at": "2026-03-24T12:00:00+00:00",
            "updated_at": "2026-03-24T12:02:00+00:00",
            "last_error": None,
            "repository_count": 8,
            "completed_repositories": 2,
            "failed_repositories": 0,
            "pending_repositories": 6,
            "repositories": [],
        },
    )
    monkeypatch.setenv("PCG_REPOS_DIR", "/tmp/repos")

    result = status_queries.get_ingester_status(object(), ingester="repository")

    assert result["status"] == "indexing"
    assert result["active_run_id"] == "run-live"
    assert result["active_phase"] == "committing"


def test_get_ingester_status_uses_bootstrap_provider_row_for_repository_view(
    monkeypatch,
) -> None:
    """The public repository ingester view should reflect active bootstrap work."""

    store = _Store(
        {
            "bootstrap-index": {
                "runtime_family": "ingester",
                "ingester": "bootstrap-index",
                "provider": "bootstrap-index",
                "status": "indexing",
                "active_run_id": "run-789",
                "active_repository_path": "/tmp/repos/payments-api",
                "active_phase": "parsing",
                "updated_at": datetime(2026, 3, 25, 12, 3, tzinfo=timezone.utc),
            }
        }
    )
    monkeypatch.setattr(status_queries, "get_runtime_status_store", lambda: store)

    result = status_queries.get_ingester_status(object(), ingester="repository")

    assert result["ingester"] == "repository"
    assert result["provider"] == "bootstrap-index"
    assert result["status"] == "indexing"
    assert result["active_run_id"] == "run-789"


def test_get_ingester_status_uses_workspace_index_provider_row_for_repository_view(
    monkeypatch,
) -> None:
    """Manual workspace indexing should surface through the repository ingester view."""

    store = _Store(
        {
            "workspace-index": {
                "runtime_family": "ingester",
                "ingester": "workspace-index",
                "provider": "workspace-index",
                "status": "indexing",
                "active_run_id": "run-workspace",
                "active_repository_path": "/tmp/repos/orders-api",
                "active_phase": "committing",
                "updated_at": datetime(2026, 3, 25, 12, 4, tzinfo=timezone.utc),
            }
        }
    )
    monkeypatch.setattr(status_queries, "get_runtime_status_store", lambda: store)

    result = status_queries.get_ingester_status(object(), ingester="repository")

    assert result["ingester"] == "repository"
    assert result["provider"] == "workspace-index"
    assert result["status"] == "indexing"
    assert result["active_run_id"] == "run-workspace"


def test_get_ingester_status_falls_back_to_checkpointed_finalization_progress(
    monkeypatch,
) -> None:
    """Checkpoint fallback should expose active finalization when no repo is active."""

    monkeypatch.setattr(status_queries, "get_runtime_status_store", lambda: None)
    monkeypatch.setattr(
        status_queries,
        "_describe_index_run",
        lambda target: {
            "run_id": "run-999",
            "status": "running",
            "finalization_status": "running",
            "finalization_current_stage": "function_calls",
            "finalization_started_at": "2026-03-25T12:00:00Z",
            "finalization_stage_started_at": "2026-03-25T12:01:00Z",
            "finalization_stage_details": {
                "function_calls": {
                    "current_file": "/tmp/repos/repo-a/lib/security.php",
                }
            },
            "created_at": "2026-03-25T11:00:00Z",
            "updated_at": "2026-03-25T12:02:00Z",
            "last_error": None,
            "repository_count": 1,
            "completed_repositories": 1,
            "failed_repositories": 0,
            "pending_repositories": 0,
            "repositories": [],
        },
    )
    monkeypatch.setenv("PCG_REPOS_DIR", "/tmp/repos")

    result = status_queries.get_ingester_status(object(), ingester="repository")

    assert result["status"] == "indexing"
    assert result["active_phase"] == "finalizing:function_calls"
    assert result["active_phase_started_at"] == "2026-03-25T12:01:00Z"
    assert result["active_current_file"] == "/tmp/repos/repo-a/lib/security.php"
    assert result["active_last_progress_at"] == "2026-03-25T12:02:00Z"


def test_resolve_index_status_target_maps_repo_name_to_local_path(
    monkeypatch,
) -> None:
    """Index-status target resolution should accept repository names."""

    database = MagicMock()
    driver = MagicMock()
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    driver.session.return_value = session
    database.get_driver.return_value = driver

    monkeypatch.setattr(
        status_queries,
        "resolve_repository",
        lambda _session, _target: {
            "id": "repository:r_20871f7f",
            "name": "api-node-boats",
            "path": "/data/repos/api-node-boats",
            "local_path": "/data/repos/api-node-boats",
        },
    )

    resolved = status_queries.resolve_index_status_target(
        database,
        target="api-node-boats",
    )

    assert resolved == Path("/data/repos/api-node-boats")


def test_describe_index_status_falls_back_to_active_runtime_run(
    monkeypatch,
) -> None:
    """Index-status should synthesize the active run from runtime state when needed."""

    store = _Store(
        {
            "workspace-index": {
                "runtime_family": "ingester",
                "ingester": "workspace-index",
                "provider": "workspace-index",
                "status": "indexing",
                "active_run_id": "run-live",
                "active_repository_path": "/tmp/repos/orders-api",
                "active_phase": "committing",
                "last_attempt_at": datetime(2026, 3, 25, 12, 0, tzinfo=timezone.utc),
                "updated_at": datetime(2026, 3, 25, 12, 4, tzinfo=timezone.utc),
                "repository_count": 8,
                "completed_repositories": 3,
                "failed_repositories": 0,
                "pending_repositories": 5,
            }
        }
    )
    monkeypatch.setattr(status_queries, "get_runtime_status_store", lambda: store)
    monkeypatch.setattr(status_queries, "_describe_index_run", lambda _target: None)
    monkeypatch.setenv("PCG_REPOS_DIR", "/tmp/repos")

    result = status_queries.describe_index_status(object(), target="run-live")

    assert result is not None
    assert result["run_id"] == "run-live"
    assert result["root_path"] == str(Path("/tmp/repos").resolve())
    assert result["status"] == "running"
    assert result["completed_repositories"] == 3
    assert result["pending_repositories"] == 5
