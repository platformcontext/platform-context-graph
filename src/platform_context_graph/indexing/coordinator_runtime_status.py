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
    )
