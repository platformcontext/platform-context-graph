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

    predicates: list[str] = []
    params: dict[str, Any] = {"limit": max(limit, 1)}
    if statuses:
        predicates.append("status = ANY(%(statuses)s::text[])")
        params["statuses"] = statuses
    if repository_id is not None:
        predicates.append("repository_id = %(repository_id)s")
        params["repository_id"] = repository_id
    if source_run_id is not None:
        predicates.append("source_run_id = %(source_run_id)s")
        params["source_run_id"] = source_run_id
    if work_type is not None:
        predicates.append("work_type = %(work_type)s")
        params["work_type"] = work_type
    if failure_class is not None:
        predicates.append("failure_class = %(failure_class)s")
        params["failure_class"] = failure_class
    where_clause = ""
    if predicates:
        where_clause = "WHERE " + " AND ".join(predicates)

    rows = queue._record_operation(
        operation="list_work_items",
        callback=lambda: queue._fetchall(
            f"""
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
                   parent_work_item_id,
                   projection_domain,
                   accepted_generation_id,
                   authoritative_shared_domains,
                   completed_shared_domains,
                   shared_projection_pending,
                   created_at,
                   updated_at
            FROM fact_work_items
            {where_clause}
            ORDER BY updated_at DESC, work_item_id DESC
            LIMIT %(limit)s
            """,
            params,
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


def count_shared_projection_pending(
    queue: Any, *, source_run_id: str | None = None
) -> int:
    """Return the number of work items blocked on authoritative shared follow-up."""

    predicates = ["shared_projection_pending = TRUE"]
    params: dict[str, Any] = {}
    if source_run_id is not None:
        predicates.append("source_run_id = %(source_run_id)s")
        params["source_run_id"] = source_run_id

    row = queue._record_operation(
        operation="count_shared_projection_pending",
        callback=lambda: queue._fetchone(
            f"""
            SELECT COUNT(*) AS pending_count
            FROM fact_work_items
            WHERE {" AND ".join(predicates)}
            """,
            params,
        ),
        row_count=None,
    )
    if row is None:
        return 0
    return int(row.get("pending_count") or 0)


def list_shared_projection_acceptances(
    queue: Any,
    *,
    projection_domain: str,
    repository_ids: list[str] | None = None,
) -> dict[tuple[str, str], str]:
    """Return accepted generations for pending authoritative shared projection."""

    rows = queue._record_operation(
        operation="list_shared_projection_acceptances",
        callback=lambda: queue._fetchall(
            """
            SELECT DISTINCT ON (repository_id, source_run_id)
                   repository_id,
                   source_run_id,
                   accepted_generation_id
            FROM fact_work_items
            WHERE shared_projection_pending = TRUE
              AND accepted_generation_id IS NOT NULL
              AND %(projection_domain)s = ANY(authoritative_shared_domains)
              AND (
                %(repository_ids)s IS NULL
                OR repository_id = ANY(%(repository_ids)s)
              )
            ORDER BY repository_id, source_run_id, updated_at DESC, work_item_id DESC
            """,
            {
                "projection_domain": projection_domain,
                "repository_ids": repository_ids or None,
            },
        ),
        row_count=None,
    )
    accepted: dict[tuple[str, str], str] = {}
    for row in rows:
        repository_id = str(row.get("repository_id") or "").strip()
        source_run_id = str(row.get("source_run_id") or "").strip()
        generation_id = str(row.get("accepted_generation_id") or "").strip()
        if repository_id and source_run_id and generation_id:
            accepted[(repository_id, source_run_id)] = generation_id
    return accepted
