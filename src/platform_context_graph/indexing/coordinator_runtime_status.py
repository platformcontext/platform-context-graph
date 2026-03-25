"""Runtime-status publishing helpers for checkpointed ingester runs."""

from __future__ import annotations

from .coordinator_models import IndexRunState
from ..runtime.status_store import update_runtime_ingester_status


def publish_runtime_progress(
    *,
    ingester: str,
    source: str,
    run_state: IndexRunState,
    repository_count: int,
    status: str,
    last_success_at: str | None = None,
) -> None:
    """Publish the current checkpointed run summary into runtime ingester status."""

    active_repo = run_state.active_repository_state()
    finalization_details = {}
    if (
        active_repo is None
        and run_state.finalization_status == "running"
        and run_state.finalization_current_stage
    ):
        stage_details = run_state.finalization_stage_details.get(
            run_state.finalization_current_stage,
            {},
        )
        if isinstance(stage_details, dict):
            finalization_details = stage_details
    if active_repo is not None:
        active_phase = active_repo.phase
        active_phase_started_at = active_repo.phase_started_at
        active_current_file = active_repo.current_file
        active_last_progress_at = active_repo.last_progress_at
        active_commit_started_at = active_repo.commit_started_at
        active_repository_path = active_repo.repo_path
    elif run_state.finalization_status == "running":
        active_phase = (
            f"finalizing:{run_state.finalization_current_stage}"
            if run_state.finalization_current_stage
            else "finalizing"
        )
        active_phase_started_at = (
            run_state.finalization_stage_started_at or run_state.finalization_started_at
        )
        active_current_file = finalization_details.get("current_file")
        active_last_progress_at = run_state.updated_at
        active_commit_started_at = None
        active_repository_path = None
    else:
        active_phase = None
        active_phase_started_at = None
        active_current_file = None
        active_last_progress_at = None
        active_commit_started_at = None
        active_repository_path = None
    update_runtime_ingester_status(
        ingester=ingester,
        source_mode=source,
        status=status,
        active_run_id=run_state.run_id,
        last_success_at=last_success_at,
        last_error_message=run_state.last_error,
        repository_count=repository_count,
        pulled_repositories=repository_count,
        in_sync_repositories=run_state.completed_repositories(),
        pending_repositories=run_state.pending_repositories(),
        completed_repositories=run_state.completed_repositories(),
        failed_repositories=run_state.failed_repositories(),
        active_repository_path=active_repository_path,
        active_phase=active_phase,
        active_phase_started_at=active_phase_started_at,
        active_current_file=active_current_file,
        active_last_progress_at=active_last_progress_at,
        active_commit_started_at=active_commit_started_at,
    )
