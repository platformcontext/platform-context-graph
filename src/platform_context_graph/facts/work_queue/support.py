"""Support helpers shared by the PostgreSQL fact work queue."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import FactWorkItemRow


def utc_now() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(tz=timezone.utc)


def work_item_params(entry: FactWorkItemRow) -> dict[str, Any]:
    """Return SQL parameters for one fact work item row."""

    return {
        "work_item_id": entry.work_item_id,
        "work_type": entry.work_type,
        "repository_id": entry.repository_id,
        "source_run_id": entry.source_run_id,
        "lease_owner": entry.lease_owner,
        "lease_expires_at": entry.lease_expires_at,
        "status": entry.status,
        "attempt_count": entry.attempt_count,
        "last_error": entry.last_error,
        "failure_stage": entry.failure_stage,
        "error_class": entry.error_class,
        "failure_class": entry.failure_class,
        "failure_code": entry.failure_code,
        "retry_disposition": entry.retry_disposition,
        "dead_lettered_at": entry.dead_lettered_at,
        "last_attempt_started_at": entry.last_attempt_started_at,
        "last_attempt_finished_at": entry.last_attempt_finished_at,
        "next_retry_at": entry.next_retry_at,
        "operator_note": entry.operator_note,
        "created_at": entry.created_at or utc_now(),
        "updated_at": entry.updated_at or utc_now(),
    }
