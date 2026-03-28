"""Unit tests for runtime status publishing from the indexing coordinator."""

from __future__ import annotations

import importlib


def test_publish_runtime_progress_reports_ingester_repo_counts(
    monkeypatch,
) -> None:
    """Coordinator progress payloads should expose pulled/synced/failed counts."""

    coordinator = importlib.import_module(
        "platform_context_graph.indexing.coordinator_runtime_status"
    )
    models = importlib.import_module(
        "platform_context_graph.indexing.coordinator_models"
    )

    run_state = models.IndexRunState(
        run_id="run-123",
        root_path="/tmp/repos",
        family="sync",
        source="githubOrg",
        discovery_signature="abc123",
        is_dependency=False,
        status="running",
        finalization_status="pending",
        created_at="2026-03-22T12:00:00+00:00",
        updated_at="2026-03-22T12:00:00+00:00",
        repositories={
            "/tmp/repos/repo-a": models.RepositoryRunState(
                repo_path="/tmp/repos/repo-a",
                status="completed",
            ),
            "/tmp/repos/repo-b": models.RepositoryRunState(
                repo_path="/tmp/repos/repo-b",
                status="failed",
            ),
            "/tmp/repos/repo-c": models.RepositoryRunState(
                repo_path="/tmp/repos/repo-c",
                status="commit_incomplete",
                phase="committing",
                phase_started_at="2026-03-22T12:03:00+00:00",
                current_file="/tmp/repos/repo-c/app.js",
                last_progress_at="2026-03-22T12:04:00+00:00",
                commit_started_at="2026-03-22T12:04:30+00:00",
            ),
            "/tmp/repos/repo-d": models.RepositoryRunState(
                repo_path="/tmp/repos/repo-d",
                status="running",
            ),
        },
    )
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        coordinator,
        "update_runtime_ingester_status",
        lambda **kwargs: calls.append(kwargs),
    )

    coordinator.publish_runtime_progress(
        ingester="repository",
        source="githubOrg",
        run_state=run_state,
        repository_count=4,
        status="indexing",
    )

    assert calls == [
        {
            "ingester": "repository",
            "source_mode": "githubOrg",
            "status": "indexing",
            "active_run_id": "run-123",
            "last_success_at": None,
            "last_error_message": None,
            "repository_count": 4,
            "pulled_repositories": 4,
            "in_sync_repositories": 1,
            "pending_repositories": 3,
            "completed_repositories": 1,
            "failed_repositories": 1,
            "active_repository_path": "/tmp/repos/repo-c",
            "active_phase": "committing",
            "active_phase_started_at": "2026-03-22T12:03:00+00:00",
            "active_current_file": "/tmp/repos/repo-c/app.js",
            "active_last_progress_at": "2026-03-22T12:04:00+00:00",
            "active_commit_started_at": "2026-03-22T12:04:30+00:00",
        }
    ]


def test_publish_runtime_progress_surfaces_active_finalization(
    monkeypatch,
) -> None:
    """Runtime status should treat finalization as active work when no repo is active."""

    coordinator = importlib.import_module(
        "platform_context_graph.indexing.coordinator_runtime_status"
    )
    models = importlib.import_module(
        "platform_context_graph.indexing.coordinator_models"
    )

    run_state = models.IndexRunState(
        run_id="run-456",
        root_path="/tmp/repos",
        family="index",
        source="filesystem",
        discovery_signature="abc123",
        is_dependency=False,
        status="running",
        finalization_status="running",
        created_at="2026-03-25T12:00:00+00:00",
        updated_at="2026-03-25T12:10:00+00:00",
        finalization_started_at="2026-03-25T12:05:00+00:00",
        finalization_current_stage="function_calls",
        finalization_stage_started_at="2026-03-25T12:05:30+00:00",
        finalization_stage_details={
            "function_calls": {
                "current_file": "/tmp/repos/repo-a/lib/security.php",
                "processed_files": 32,
                "total_files": 100,
            }
        },
        repositories={
            "/tmp/repos/repo-a": models.RepositoryRunState(
                repo_path="/tmp/repos/repo-a",
                status="completed",
            )
        },
    )
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        coordinator,
        "update_runtime_ingester_status",
        lambda **kwargs: calls.append(kwargs),
    )

    coordinator.publish_runtime_progress(
        ingester="repository",
        source="filesystem",
        run_state=run_state,
        repository_count=1,
        status="indexing",
    )

    assert calls[0]["active_repository_path"] is None
    assert calls[0]["active_phase"] == "finalizing:function_calls"
    assert calls[0]["active_phase_started_at"] == "2026-03-25T12:05:30+00:00"
    assert calls[0]["active_current_file"] == "/tmp/repos/repo-a/lib/security.php"
    assert calls[0]["active_last_progress_at"] == "2026-03-25T12:10:00+00:00"


def test_describe_run_state_includes_finalization_diagnostics() -> None:
    """Checkpoint summaries should expose persisted finalization timings."""

    coordinator = importlib.import_module("platform_context_graph.indexing.coordinator")
    models = importlib.import_module(
        "platform_context_graph.indexing.coordinator_models"
    )

    run_state = models.IndexRunState(
        run_id="run-123",
        root_path="/tmp/repos",
        family="sync",
        source="githubOrg",
        discovery_signature="abc123",
        is_dependency=False,
        status="running",
        finalization_status="running",
        created_at="2026-03-22T12:00:00+00:00",
        updated_at="2026-03-22T12:00:00+00:00",
        finalization_started_at="2026-03-22T12:05:00+00:00",
        finalization_finished_at=None,
        finalization_duration_seconds=12.5,
        finalization_current_stage="function_calls",
        finalization_stage_started_at="2026-03-22T12:05:10+00:00",
        finalization_stage_durations={"inheritance": 2.0},
        finalization_stage_details={
            "function_calls": {"fallback_duration_seconds": 9.0}
        },
        repositories={},
    )

    summary = coordinator._describe_run_state(run_state)

    assert summary["finalization_started_at"] == "2026-03-22T12:05:00+00:00"
    assert summary["finalization_finished_at"] is None
    assert summary["finalization_duration_seconds"] == 12.5
    assert summary["finalization_current_stage"] == "function_calls"
    assert summary["finalization_stage_started_at"] == "2026-03-22T12:05:10+00:00"
    assert summary["finalization_stage_durations"] == {"inheritance": 2.0}
    assert summary["finalization_stage_details"] == {
        "function_calls": {"fallback_duration_seconds": 9.0}
    }


def test_parse_worker_recycling_is_opt_in_by_default(monkeypatch) -> None:
    """Parse workers should not recycle unless the operator opts in."""

    coordinator = importlib.import_module("platform_context_graph.indexing.coordinator")

    monkeypatch.delenv("PCG_WORKER_MAX_TASKS", raising=False)

    assert coordinator._parse_worker_max_tasks_per_child() is None


def test_parse_executor_scope_omits_recycle_threshold_when_unset(
    monkeypatch,
) -> None:
    """The process pool should not receive a recycle threshold unless configured."""

    coordinator = importlib.import_module("platform_context_graph.indexing.coordinator")
    captured: dict[str, object] = {}

    class _FakeExecutor:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        def shutdown(self, wait: bool = True, cancel_futures: bool = True) -> None:
            captured["shutdown"] = {
                "wait": wait,
                "cancel_futures": cancel_futures,
            }

    monkeypatch.setenv("PCG_REPO_FILE_PARSE_MULTIPROCESS", "true")
    monkeypatch.setenv("PCG_PARSE_WORKERS", "3")
    monkeypatch.delenv("PCG_WORKER_MAX_TASKS", raising=False)
    monkeypatch.setattr(coordinator.multiprocessing, "get_context", lambda method: method)
    monkeypatch.setattr(coordinator, "ProcessPoolExecutor", _FakeExecutor)

    with coordinator._parse_executor_scope():
        pass

    assert captured["max_workers"] == 3
    assert captured["mp_context"] == "spawn"
    assert captured["initializer"] is coordinator.init_parse_worker
    assert "max_tasks_per_child" not in captured
    assert captured["shutdown"] == {"wait": True, "cancel_futures": True}
