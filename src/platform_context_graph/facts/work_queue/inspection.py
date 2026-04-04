"""Inspection helpers for PostgreSQL-backed fact work queues."""

from __future__ import annotations

from typing import Any

from .models import FactWorkItemRow
from .models import FactWorkQueueSnapshotRow
from .support import utc_now


def list_work_items(
    queue: Any,
    *,
    statuses: list[str] | None = None,
    repository_id: str | None = None,
    source_run_id: str | None = None,
    work_type: str | None = None,
    failure_class: str | None = None,
    limit: int = 100,
) -> list[FactWorkItemRow]:
    """Return work items filtered by status and failure selectors."""

    rows = queue._record_operation(
        operation="list_work_items",
        callback=lambda: queue._fetchall(
            """
            SELECT work_item_id,
                   work_type,
                   repository_id,
                   source_run_id,
                   lease_owner,
                   lease_expires_at,
                   status,
                   attempt_count,
                   last_error,
                   failure_stage,
                   error_class,
                   failure_class,
                   failure_code,
                   retry_disposition,
                   dead_lettered_at,
                   last_attempt_started_at,
                   last_attempt_finished_at,
                   next_retry_at,
                   operator_note,
                   created_at,
                   updated_at
            FROM fact_work_items
            WHERE (%(statuses)s IS NULL OR status = ANY(%(statuses)s))
              AND (%(repository_id)s IS NULL OR repository_id = %(repository_id)s)
              AND (%(source_run_id)s IS NULL OR source_run_id = %(source_run_id)s)
              AND (%(work_type)s IS NULL OR work_type = %(work_type)s)
              AND (%(failure_class)s IS NULL OR failure_class = %(failure_class)s)
            ORDER BY updated_at DESC, work_item_id DESC
            LIMIT %(limit)s
            """,
            {
                "statuses": statuses or None,
                "repository_id": repository_id,
                "source_run_id": source_run_id,
                "work_type": work_type,
                "failure_class": failure_class,
                "limit": max(limit, 1),
            },
        ),
        row_count=None,
    )
    return [FactWorkItemRow(**row) for row in rows]


def list_queue_snapshot(queue: Any) -> list[FactWorkQueueSnapshotRow]:
    """Return aggregated queue depth and oldest age by work type and status."""

    now = utc_now()
    rows = queue._record_operation(
        operation="list_queue_snapshot",
        callback=lambda: queue._fetchall(
            """
            SELECT work_type,
                   status,
                   COUNT(*) AS depth,
                   COALESCE(
                     EXTRACT(EPOCH FROM (%(now)s - MIN(created_at))),
                     0
                   ) AS oldest_age_seconds
            FROM fact_work_items
            GROUP BY work_type, status
            """,
            {"now": now},
        ),
        row_count=None,
    )
    return [
        FactWorkQueueSnapshotRow(
            work_type=row["work_type"],
            status=row["status"],
            depth=int(row["depth"]),
            oldest_age_seconds=float(row["oldest_age_seconds"] or 0.0),
        )
        for row in rows
    ]
