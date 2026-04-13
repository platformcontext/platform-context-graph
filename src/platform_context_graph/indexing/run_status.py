"""Read-only checkpoint status helpers for index-run introspection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .coordinator_storage import _load_run_state_by_id, _matching_run_states


def _describe_run_state(run_state: Any) -> dict[str, Any]:
    """Return a CLI/API-friendly summary for one checkpointed run."""

    return {
        "run_id": run_state.run_id,
        "root_path": run_state.root_path,
        "family": run_state.family,
        "source": run_state.source,
        "status": run_state.status,
        "finalization_status": run_state.finalization_status,
        "created_at": run_state.created_at,
        "updated_at": run_state.updated_at,
        "finalization_started_at": run_state.finalization_started_at,
        "finalization_finished_at": run_state.finalization_finished_at,
        "finalization_duration_seconds": run_state.finalization_duration_seconds,
        "finalization_current_stage": run_state.finalization_current_stage,
        "finalization_stage_started_at": run_state.finalization_stage_started_at,
        "finalization_stage_durations": run_state.finalization_stage_durations,
        "finalization_stage_details": run_state.finalization_stage_details,
        "last_error": run_state.last_error,
        "repository_count": len(run_state.repositories),
        "completed_repositories": run_state.completed_repositories(),
        "failed_repositories": run_state.failed_repositories(),
        "pending_repositories": run_state.pending_repositories(),
        "repositories": [
            {
                "repo_path": state.repo_path,
                "status": state.status,
                "file_count": state.file_count,
                "error": state.error,
                "started_at": state.started_at,
                "finished_at": state.finished_at,
                "updated_at": state.updated_at,
                "phase": state.phase,
                "phase_started_at": state.phase_started_at,
                "last_progress_at": state.last_progress_at,
                "current_file": state.current_file,
                "commit_started_at": state.commit_started_at,
                "commit_finished_at": state.commit_finished_at,
                "commit_duration_seconds": state.commit_duration_seconds,
            }
            for state in sorted(
                run_state.repositories.values(),
                key=lambda item: item.repo_path,
            )
        ],
    }


def describe_latest_index_run(path: Path) -> dict[str, Any] | None:
    """Return the latest persisted run summary for a root path."""

    matches = _matching_run_states(path.resolve())
    if not matches:
        return None
    return _describe_run_state(matches[0])


def describe_index_run(path_or_run_id: str | Path) -> dict[str, Any] | None:
    """Return a persisted run summary for a root path or explicit run ID."""

    if isinstance(path_or_run_id, Path):
        return describe_latest_index_run(path_or_run_id)

    candidate = str(path_or_run_id).strip()
    if candidate and all(char in "0123456789abcdef" for char in candidate.lower()):
        run_state = _load_run_state_by_id(candidate)
        if run_state is not None:
            return _describe_run_state(run_state)
    return describe_latest_index_run(Path(candidate).resolve())
