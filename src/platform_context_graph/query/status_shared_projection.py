"""Shared-projection-aware ingester status adjustments."""

from __future__ import annotations

from typing import Any


def count_pending_shared_projection_repositories(
    queue: Any | None, *, source_run_id: str | None
) -> int:
    """Return the number of repositories still waiting on shared authoritative work."""

    if queue is None or not getattr(queue, "enabled", True):
        return 0
    count_fn = getattr(queue, "count_shared_projection_pending", None)
    if not callable(count_fn) or not source_run_id:
        return 0
    return int(count_fn(source_run_id=source_run_id) or 0)


def apply_shared_projection_pending_status(
    payload: dict[str, Any], *, pending_count: int
) -> dict[str, Any]:
    """Project shared-follow-up pending state into the public ingester payload."""

    normalized = dict(payload)
    normalized["shared_projection_pending_repositories"] = max(pending_count, 0)
    if pending_count <= 0:
        return normalized

    completed_repositories = int(normalized.get("completed_repositories") or 0)
    shifted = min(completed_repositories, pending_count)
    normalized["completed_repositories"] = max(completed_repositories - shifted, 0)
    normalized["in_sync_repositories"] = normalized["completed_repositories"]
    normalized["pending_repositories"] = (
        int(normalized.get("pending_repositories") or 0) + shifted
    )
    if str(normalized.get("status") or "") == "completed":
        normalized["status"] = "indexing"
        normalized["finalization_status"] = "running"
        normalized["last_success_at"] = None
    if not normalized.get("active_phase"):
        normalized["active_phase"] = "awaiting_shared_projection"
    return normalized
