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
                status="running",
                phase="committing",
                phase_started_at="2026-03-22T12:03:00+00:00",
                current_file="/tmp/repos/repo-c/app.js",
                last_progress_at="2026-03-22T12:04:00+00:00",
                commit_started_at="2026-03-22T12:04:30+00:00",
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
        repository_count=3,
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
            "repository_count": 3,
            "pulled_repositories": 3,
            "in_sync_repositories": 1,
            "pending_repositories": 2,
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
