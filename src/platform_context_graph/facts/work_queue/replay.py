"""Replay helpers for the PostgreSQL-backed fact work queue."""

from __future__ import annotations

from typing import Any

from .models import FactWorkItemRow
from .support import utc_now


def replay_failed_work_items(
    queue: Any,
    *,
    work_item_ids: list[str] | None = None,
    repository_id: str | None = None,
    source_run_id: str | None = None,
    work_type: str | None = None,
    limit: int = 100,
) -> list[FactWorkItemRow]:
    """Replay terminally failed work items by returning them to pending."""

    rows = queue._record_operation(
        operation="replay_failed_work_items",
        callback=lambda: queue._fetchall(
            """
            WITH replayable AS (
                SELECT work_item_id
                FROM fact_work_items
                WHERE status = 'failed'
                  AND (%(work_item_ids)s IS NULL OR work_item_id = ANY(%(work_item_ids)s))
                  AND (%(repository_id)s IS NULL OR repository_id = %(repository_id)s)
                  AND (%(source_run_id)s IS NULL OR source_run_id = %(source_run_id)s)
                  AND (%(work_type)s IS NULL OR work_type = %(work_type)s)
                ORDER BY updated_at ASC
                LIMIT %(limit)s
            )
            UPDATE fact_work_items
            SET status = 'pending',
                lease_owner = NULL,
                lease_expires_at = NULL,
                attempt_count = 0,
                updated_at = %(updated_at)s
            WHERE work_item_id IN (SELECT work_item_id FROM replayable)
            RETURNING work_item_id,
                      work_type,
                      repository_id,
                      source_run_id,
                      lease_owner,
                      lease_expires_at,
                      status,
                      attempt_count,
                      last_error,
                      created_at,
                      updated_at
            """,
            {
                "work_item_ids": work_item_ids or None,
                "repository_id": repository_id,
                "source_run_id": source_run_id,
                "work_type": work_type,
                "limit": max(limit, 1),
                "updated_at": utc_now(),
            },
        ),
        row_count=None,
    )
    return [FactWorkItemRow(**row) for row in rows]
