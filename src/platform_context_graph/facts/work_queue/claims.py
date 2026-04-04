"""Queue mutation helpers for PostgreSQL-backed fact work items."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from .models import FactWorkItemRow
from .support import utc_now
from .support import work_item_params


def enqueue_work_item(queue: Any, entry: FactWorkItemRow) -> None:
    """Insert or update one pending fact work item."""

    queue._record_operation(
        operation="enqueue_work_item",
        row_count=1,
        callback=lambda: queue._execute(
            """
            INSERT INTO fact_work_items (
                work_item_id,
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
            ) VALUES (
                %(work_item_id)s,
                %(work_type)s,
                %(repository_id)s,
                %(source_run_id)s,
                %(lease_owner)s,
                %(lease_expires_at)s,
                %(status)s,
                %(attempt_count)s,
                %(last_error)s,
                %(failure_stage)s,
                %(error_class)s,
                %(failure_class)s,
                %(failure_code)s,
                %(retry_disposition)s,
                %(dead_lettered_at)s,
                %(last_attempt_started_at)s,
                %(last_attempt_finished_at)s,
                %(next_retry_at)s,
                %(operator_note)s,
                %(created_at)s,
                %(updated_at)s
            )
            ON CONFLICT (work_item_id) DO UPDATE
            SET work_type = EXCLUDED.work_type,
                repository_id = EXCLUDED.repository_id,
                source_run_id = EXCLUDED.source_run_id,
                lease_owner = EXCLUDED.lease_owner,
                lease_expires_at = EXCLUDED.lease_expires_at,
                status = EXCLUDED.status,
                attempt_count = EXCLUDED.attempt_count,
                last_error = EXCLUDED.last_error,
                failure_stage = EXCLUDED.failure_stage,
                error_class = EXCLUDED.error_class,
                failure_class = EXCLUDED.failure_class,
                failure_code = EXCLUDED.failure_code,
                retry_disposition = EXCLUDED.retry_disposition,
                dead_lettered_at = EXCLUDED.dead_lettered_at,
                last_attempt_started_at = EXCLUDED.last_attempt_started_at,
                last_attempt_finished_at = EXCLUDED.last_attempt_finished_at,
                next_retry_at = EXCLUDED.next_retry_at,
                operator_note = EXCLUDED.operator_note,
                updated_at = EXCLUDED.updated_at
            """,
            work_item_params(entry),
        ),
    )


def claim_work_item(
    queue: Any,
    *,
    lease_owner: str,
    lease_ttl_seconds: int,
) -> FactWorkItemRow | None:
    """Claim one pending work item and return the leased row."""

    now = utc_now()
    lease_expires_at = now + timedelta(seconds=lease_ttl_seconds)
    row = queue._record_operation(
        operation="claim_work_item",
        callback=lambda: queue._fetchone(
            """
            WITH claimable AS (
                SELECT work_item_id
                FROM fact_work_items
                WHERE (
                    (
                        status = 'pending'
                        AND (
                            lease_expires_at IS NULL
                            OR lease_expires_at <= %(now)s
                        )
                    )
                    OR (
                        status = 'leased'
                        AND lease_expires_at IS NOT NULL
                        AND lease_expires_at <= %(now)s
                    )
                )
                  AND (
                    next_retry_at IS NULL
                    OR next_retry_at <= %(now)s
                  )
                ORDER BY updated_at ASC
                LIMIT 1
            )
            UPDATE fact_work_items
            SET lease_owner = %(lease_owner)s,
                lease_expires_at = %(lease_expires_at)s,
                status = 'leased',
                attempt_count = fact_work_items.attempt_count + 1,
                last_attempt_started_at = %(now)s,
                updated_at = %(now)s
            WHERE work_item_id IN (SELECT work_item_id FROM claimable)
            RETURNING work_item_id,
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
            """,
            {
                "lease_owner": lease_owner,
                "lease_expires_at": lease_expires_at,
                "now": now,
            },
        ),
    )
    return FactWorkItemRow(**row) if row else None


def lease_work_item(
    queue: Any,
    *,
    work_item_id: str,
    lease_owner: str,
    lease_ttl_seconds: int,
) -> FactWorkItemRow | None:
    """Lease one specific work item when it is still claimable."""

    now = utc_now()
    lease_expires_at = now + timedelta(seconds=lease_ttl_seconds)
    row = queue._record_operation(
        operation="lease_work_item",
        callback=lambda: queue._fetchone(
            """
            UPDATE fact_work_items
            SET lease_owner = %(lease_owner)s,
                lease_expires_at = %(lease_expires_at)s,
                status = 'leased',
                attempt_count = fact_work_items.attempt_count + 1,
                last_attempt_started_at = %(now)s,
                updated_at = %(now)s
            WHERE work_item_id = %(work_item_id)s
              AND status = 'pending'
              AND (
                lease_expires_at IS NULL
                OR lease_expires_at <= %(now)s
              )
              AND (
                next_retry_at IS NULL
                OR next_retry_at <= %(now)s
              )
            RETURNING work_item_id,
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
            """,
            {
                "work_item_id": work_item_id,
                "lease_owner": lease_owner,
                "lease_expires_at": lease_expires_at,
                "now": now,
            },
        ),
    )
    return FactWorkItemRow(**row) if row else None


def fail_work_item(
    queue: Any,
    *,
    work_item_id: str,
    error_message: str,
    terminal: bool,
    failure_stage: str | None = None,
    error_class: str | None = None,
    failure_class: str | None = None,
    failure_code: str | None = None,
    retry_disposition: str | None = None,
    next_retry_at: Any | None = None,
    operator_note: str | None = None,
) -> None:
    """Mark one work item as retryable or terminally failed."""

    updated_at = utc_now()
    dead_lettered_at = updated_at if terminal else None
    queue._record_operation(
        operation="fail_work_item",
        row_count=1,
        callback=lambda: queue._execute(
            """
            UPDATE fact_work_items
            SET status = %(status)s,
                lease_owner = NULL,
                lease_expires_at = NULL,
                last_error = %(last_error)s,
                failure_stage = %(failure_stage)s,
                error_class = %(error_class)s,
                failure_class = %(failure_class)s,
                failure_code = %(failure_code)s,
                retry_disposition = %(retry_disposition)s,
                dead_lettered_at = %(dead_lettered_at)s,
                last_attempt_finished_at = %(updated_at)s,
                next_retry_at = %(next_retry_at)s,
                operator_note = %(operator_note)s,
                updated_at = %(updated_at)s
            WHERE work_item_id = %(work_item_id)s
            """,
            {
                "work_item_id": work_item_id,
                "status": "failed" if terminal else "pending",
                "last_error": error_message,
                "failure_stage": failure_stage,
                "error_class": error_class,
                "failure_class": failure_class,
                "failure_code": failure_code,
                "retry_disposition": retry_disposition,
                "dead_lettered_at": dead_lettered_at,
                "next_retry_at": None if terminal else next_retry_at,
                "operator_note": operator_note,
                "updated_at": updated_at,
            },
        ),
    )


def complete_work_item(queue: Any, *, work_item_id: str) -> None:
    """Mark one work item completed and clear its lease."""

    queue._record_operation(
        operation="complete_work_item",
        row_count=1,
        callback=lambda: queue._execute(
            """
            UPDATE fact_work_items
            SET status = 'completed',
                lease_owner = NULL,
                lease_expires_at = NULL,
                last_error = NULL,
                failure_stage = NULL,
                error_class = NULL,
                failure_class = NULL,
                failure_code = NULL,
                retry_disposition = NULL,
                dead_lettered_at = NULL,
                last_attempt_finished_at = %(updated_at)s,
                last_attempt_started_at = NULL,
                next_retry_at = NULL,
                operator_note = NULL,
                updated_at = %(updated_at)s
            WHERE work_item_id = %(work_item_id)s
            """,
            {
                "work_item_id": work_item_id,
                "updated_at": utc_now(),
            },
        ),
    )
