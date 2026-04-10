"""Shared-projection-aware ingester status adjustments."""

from __future__ import annotations

from typing import Any


def count_pending_shared_projection_repositories(
    queue: Any | None, *, source_run_id: str | None
) -> int | None:
    """Return the number of repositories still waiting on shared authoritative work."""

    if queue is None or not getattr(queue, "enabled", True):
        return None
    count_fn = getattr(queue, "count_shared_projection_pending", None)
    if not callable(count_fn) or not source_run_id:
        return None
    return int(count_fn(source_run_id=source_run_id) or 0)


def list_shared_projection_backlog(
    shared_projection_intent_store: Any | None,
    *,
    source_run_id: str | None,
) -> list[dict[str, Any]]:
    """Return one shared-backlog summary list for the current source run."""

    if shared_projection_intent_store is None or not getattr(
        shared_projection_intent_store, "enabled", True
    ):
        return []
    list_fn = getattr(
        shared_projection_intent_store, "list_pending_backlog_snapshot", None
    )
    if not callable(list_fn):
        return []
    rows = list_fn(source_run_id=source_run_id) if source_run_id else list_fn()
    summaries: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            projection_domain = str(row.get("projection_domain") or "").strip()
            pending_depth = int(row.get("pending_depth") or 0)
            oldest_age_seconds = float(row.get("oldest_age_seconds") or 0.0)
        else:
            projection_domain = str(getattr(row, "projection_domain", "") or "").strip()
            pending_depth = int(getattr(row, "pending_depth", 0) or 0)
            oldest_age_seconds = float(getattr(row, "oldest_age_seconds", 0.0) or 0.0)
        if not projection_domain or pending_depth <= 0:
            continue
        summaries.append(
            {
                "projection_domain": projection_domain,
                "pending_intents": pending_depth,
                "oldest_pending_age_seconds": oldest_age_seconds,
            }
        )
    return summaries


def apply_shared_projection_pending_status(
    payload: dict[str, Any],
    *,
    pending_count: int | None,
    backlog: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Project shared-follow-up pending state into the public ingester payload."""

    normalized = dict(payload)
    normalized["shared_projection_backlog"] = list(backlog or [])
    if pending_count is None:
        normalized["shared_projection_pending_repositories"] = int(
            normalized.get("shared_projection_pending_repositories") or 0
        )
        return normalized

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


def enrich_shared_projection_status(
    payload: dict[str, Any],
    *,
    queue: Any | None,
    shared_projection_intent_store: Any | None,
) -> dict[str, Any]:
    """Return one status payload enriched with shared-projection state."""

    source_run_id = str(payload.get("active_run_id") or "").strip() or None
    pending_count = count_pending_shared_projection_repositories(
        queue,
        source_run_id=source_run_id,
    )
    backlog = list_shared_projection_backlog(
        shared_projection_intent_store,
        source_run_id=source_run_id,
    )
    return apply_shared_projection_pending_status(
        payload,
        pending_count=pending_count,
        backlog=backlog,
    )
