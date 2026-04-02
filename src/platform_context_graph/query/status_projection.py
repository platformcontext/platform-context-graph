"""Projection helpers for ingester status and run summaries."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def active_repository_from_summary(summary: dict[str, Any]) -> dict[str, Any] | None:
    """Return the best active repository from one checkpoint summary."""

    repositories = summary.get("repositories")
    if not isinstance(repositories, list):
        return None

    active_states = {"running", "parsed", "commit_incomplete"}
    active_repos = [
        repo
        for repo in repositories
        if isinstance(repo, dict) and repo.get("status") in active_states
    ]
    if not active_repos:
        return None

    def _sort_key(repo: dict[str, Any]) -> tuple[str, str]:
        return (
            str(repo.get("last_progress_at") or repo.get("updated_at") or ""),
            str(repo.get("repo_path") or ""),
        )

    return max(active_repos, key=_sort_key)


def active_finalization_from_summary(summary: dict[str, Any]) -> dict[str, Any] | None:
    """Return active finalization details when no repository is actively running."""

    if summary.get("finalization_status") != "running":
        return None
    stage_name = summary.get("finalization_current_stage")
    stage_details = summary.get("finalization_stage_details")
    current_file = None
    if isinstance(stage_details, dict) and isinstance(stage_name, str):
        current_stage_details = stage_details.get(stage_name)
        if isinstance(current_stage_details, dict):
            current_file = current_stage_details.get("current_file")
    return {
        "active_phase": (
            f"finalizing:{stage_name}" if isinstance(stage_name, str) else "finalizing"
        ),
        "active_phase_started_at": (
            summary.get("finalization_stage_started_at")
            or summary.get("finalization_started_at")
        ),
        "active_current_file": current_file,
        "active_last_progress_at": summary.get("updated_at"),
    }


def derive_finalization_status(
    summary: dict[str, Any], public_status: str
) -> str | None:
    """Derive the finalization status from run state or active phase signals."""

    explicit = summary.get("finalization_status")
    if isinstance(explicit, str) and explicit:
        return explicit
    active_phase = str(summary.get("active_phase") or "")
    if active_phase.startswith("finalizing:") or active_phase == "finalizing":
        return "running"
    if public_status == "completed":
        return "completed"
    return None


def checkpoint_status_payload(
    *, ingester: str, source_mode: str | None, summary: dict[str, Any]
) -> dict[str, Any]:
    """Project checkpointed run state into the ingester-status response shape."""

    active_repo = active_repository_from_summary(summary)
    active_finalization = (
        active_finalization_from_summary(summary)
        if active_repo is None
        else None
    )
    run_status = str(summary.get("status") or "bootstrap_pending")
    public_status = "indexing" if run_status == "running" else run_status
    updated_at = summary.get("updated_at")
    finalization_status = derive_finalization_status(summary, public_status)
    return {
        "runtime_family": "ingester",
        "ingester": ingester,
        "provider": ingester,
        "source_mode": source_mode,
        "status": public_status,
        "finalization_status": finalization_status,
        "active_run_id": summary.get("run_id"),
        "last_attempt_at": summary.get("created_at"),
        "last_success_at": updated_at if public_status == "completed" else None,
        "next_retry_at": None,
        "last_error_kind": None,
        "last_error_message": summary.get("last_error"),
        "active_repository_path": (
            active_repo.get("repo_path") if active_repo is not None else None
        ),
        "active_phase": (
            active_repo.get("phase")
            if active_repo is not None
            else (
                active_finalization.get("active_phase")
                if active_finalization is not None
                else None
            )
        ),
        "active_phase_started_at": (
            active_repo.get("phase_started_at")
            if active_repo is not None
            else (
                active_finalization.get("active_phase_started_at")
                if active_finalization is not None
                else None
            )
        ),
        "active_current_file": (
            active_repo.get("current_file")
            if active_repo is not None
            else (
                active_finalization.get("active_current_file")
                if active_finalization is not None
                else None
            )
        ),
        "active_last_progress_at": (
            active_repo.get("last_progress_at")
            if active_repo is not None
            else (
                active_finalization.get("active_last_progress_at")
                if active_finalization is not None
                else None
            )
        ),
        "active_commit_started_at": (
            active_repo.get("commit_started_at") if active_repo is not None else None
        ),
        "repository_count": int(summary.get("repository_count") or 0),
        "pulled_repositories": int(summary.get("repository_count") or 0),
        "in_sync_repositories": int(summary.get("completed_repositories") or 0),
        "pending_repositories": int(summary.get("pending_repositories") or 0),
        "completed_repositories": int(summary.get("completed_repositories") or 0),
        "failed_repositories": int(summary.get("failed_repositories") or 0),
        "scan_request_state": "idle",
        "scan_request_token": None,
        "scan_requested_at": None,
        "scan_requested_by": None,
        "scan_started_at": None,
        "scan_completed_at": None,
        "scan_error_message": None,
        "updated_at": updated_at,
    }


def runtime_run_summary_from_status(
    status_payload: dict[str, Any],
    *,
    fallback_root_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Build a run-summary payload from shared runtime ingester status."""

    run_id = str(status_payload.get("active_run_id") or "").strip()
    if not run_id:
        return None

    runtime_status = str(status_payload.get("status") or "").strip().lower()
    if runtime_status == "indexing":
        summary_status = "running"
    elif runtime_status in {"completed", "partial_failure", "failed"}:
        summary_status = runtime_status
    else:
        return None

    root_path = None
    if fallback_root_path is not None:
        root_path = str(Path(fallback_root_path).resolve())
    else:
        active_repository_path = status_payload.get("active_repository_path")
        if isinstance(active_repository_path, str) and active_repository_path.strip():
            root_path = str(Path(active_repository_path).resolve().parent)

    active_phase = str(status_payload.get("active_phase") or "")
    if active_phase.startswith("finalizing:") or active_phase == "finalizing":
        finalization_status = "running"
    elif summary_status == "completed":
        finalization_status = "completed"
    elif summary_status == "failed":
        finalization_status = "failed"
    else:
        finalization_status = "pending"

    repositories: list[dict[str, Any]] = []
    active_repository_path = status_payload.get("active_repository_path")
    if isinstance(active_repository_path, str) and active_repository_path.strip():
        repositories.append(
            {
                "repo_path": active_repository_path,
                "status": "running" if summary_status == "running" else summary_status,
                "file_count": None,
                "error": status_payload.get("last_error_message"),
                "started_at": status_payload.get("last_attempt_at"),
                "finished_at": None,
                "updated_at": status_payload.get("updated_at"),
                "phase": status_payload.get("active_phase"),
                "phase_started_at": status_payload.get("active_phase_started_at"),
                "last_progress_at": status_payload.get("active_last_progress_at"),
                "current_file": status_payload.get("active_current_file"),
                "commit_started_at": status_payload.get("active_commit_started_at"),
                "commit_finished_at": None,
                "commit_duration_seconds": None,
            }
        )

    return {
        "run_id": run_id,
        "root_path": root_path,
        "family": "repository",
        "source": status_payload.get("source_mode"),
        "status": summary_status,
        "finalization_status": finalization_status,
        "created_at": (
            status_payload.get("last_attempt_at") or status_payload.get("updated_at")
        ),
        "updated_at": status_payload.get("updated_at"),
        "finalization_started_at": None,
        "finalization_finished_at": (
            status_payload.get("last_success_at")
            if finalization_status == "completed"
            else None
        ),
        "finalization_duration_seconds": None,
        "finalization_current_stage": None,
        "finalization_stage_started_at": None,
        "finalization_stage_durations": {},
        "finalization_stage_details": {},
        "last_error": status_payload.get("last_error_message"),
        "repository_count": int(status_payload.get("repository_count") or 0),
        "completed_repositories": int(
            status_payload.get("completed_repositories") or 0
        ),
        "failed_repositories": int(status_payload.get("failed_repositories") or 0),
        "pending_repositories": int(status_payload.get("pending_repositories") or 0),
        "repositories": repositories,
    }
