"""Recovery and audit helpers for PostgreSQL-backed fact work queues."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from .models import FactBackfillRequestRow
from .models import FactReplayEventRow
from .models import FactWorkItemRow
from .support import utc_now

_DEFAULT_DEAD_LETTER_ERROR = "Operator moved work item to dead letter"
_ARCHIVED_SKIP_NOTE = "Repository is archived and excluded by repo-sync policy."


def dead_letter_work_items(
    queue: Any,
    *,
    work_item_ids: list[str] | None = None,
    repository_id: str | None = None,
    source_run_id: str | None = None,
    work_type: str | None = None,
    failure_class: str | None = None,
    operator_note: str | None = None,
    limit: int = 100,
) -> list[FactWorkItemRow]:
    """Move selected work items into durable dead-letter state."""

    updated_at = utc_now()
    rows = queue._record_operation(
        operation="dead_letter_work_items",
        callback=lambda: queue._fetchall(
            """
            WITH selected AS (
                SELECT work_item_id
                FROM fact_work_items
                WHERE status <> 'completed'
                  AND (%(work_item_ids)s IS NULL OR work_item_id = ANY(%(work_item_ids)s))
                  AND (%(repository_id)s IS NULL OR repository_id = %(repository_id)s)
                  AND (%(source_run_id)s IS NULL OR source_run_id = %(source_run_id)s)
                  AND (%(work_type)s IS NULL OR work_type = %(work_type)s)
                ORDER BY updated_at ASC
                LIMIT %(limit)s
            )
            UPDATE fact_work_items
            SET status = 'failed',
                lease_owner = NULL,
                lease_expires_at = NULL,
                last_error = COALESCE(last_error, %(last_error)s),
                failure_stage = COALESCE(failure_stage, %(failure_stage)s),
                failure_class = COALESCE(failure_class, %(failure_class)s),
                failure_code = COALESCE(failure_code, %(failure_code)s),
                retry_disposition = %(retry_disposition)s,
                dead_lettered_at = %(updated_at)s,
                last_attempt_finished_at = %(updated_at)s,
                next_retry_at = NULL,
                operator_note = %(operator_note)s,
                updated_at = %(updated_at)s
            WHERE work_item_id IN (SELECT work_item_id FROM selected)
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
                "work_item_ids": work_item_ids or None,
                "repository_id": repository_id,
                "source_run_id": source_run_id,
                "work_type": work_type,
                "failure_class": failure_class or "manual_override",
                "failure_code": "manual_dead_letter",
                "failure_stage": "operator_action",
                "retry_disposition": "manual_review",
                "last_error": _DEFAULT_DEAD_LETTER_ERROR,
                "operator_note": operator_note,
                "limit": max(limit, 1),
                "updated_at": updated_at,
            },
        ),
        row_count=None,
    )
    return [FactWorkItemRow(**row) for row in rows]


def skip_repository_work_items(
    queue: Any,
    *,
    repository_id: str,
    operator_note: str | None = None,
) -> list[FactWorkItemRow]:
    """Mark one repository's actionable work items as intentionally skipped."""

    updated_at = utc_now()
    rows = queue._record_operation(
        operation="skip_repository_work_items",
        callback=lambda: queue._fetchall(
            """
            WITH selected AS (
                SELECT work_item_id
                FROM fact_work_items
                WHERE repository_id = %(repository_id)s
                  AND status NOT IN ('completed', 'skipped')
                ORDER BY updated_at ASC, work_item_id ASC
            )
            UPDATE fact_work_items
            SET status = 'skipped',
                lease_owner = NULL,
                lease_expires_at = NULL,
                failure_stage = 'repo_sync',
                failure_class = %(failure_class)s,
                failure_code = %(failure_code)s,
                retry_disposition = %(retry_disposition)s,
                dead_lettered_at = NULL,
                last_attempt_finished_at = %(updated_at)s,
                next_retry_at = NULL,
                operator_note = %(operator_note)s,
                updated_at = %(updated_at)s
            WHERE work_item_id IN (SELECT work_item_id FROM selected)
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
                "repository_id": repository_id,
                "failure_class": "skipped_repository",
                "failure_code": "archived_repository",
                "retry_disposition": "non_retryable",
                "operator_note": operator_note or _ARCHIVED_SKIP_NOTE,
                "updated_at": updated_at,
            },
        ),
        row_count=None,
    )
    return [FactWorkItemRow(**row) for row in rows]


def request_backfill(
    queue: Any,
    *,
    repository_id: str | None = None,
    source_run_id: str | None = None,
    operator_note: str | None = None,
) -> FactBackfillRequestRow:
    """Persist one durable operator backfill request."""

    row = FactBackfillRequestRow(
        backfill_request_id=f"fact-backfill:{uuid4()}",
        repository_id=repository_id,
        source_run_id=source_run_id,
        operator_note=operator_note,
        created_at=utc_now(),
    )
    queue._record_operation(
        operation="request_backfill",
        row_count=1,
        callback=lambda: queue._execute(
            """
            INSERT INTO fact_backfill_requests (
                backfill_request_id,
                repository_id,
                source_run_id,
                operator_note,
                created_at
            ) VALUES (
                %(backfill_request_id)s,
                %(repository_id)s,
                %(source_run_id)s,
                %(operator_note)s,
                %(created_at)s
            )
            """,
            {
                "backfill_request_id": row.backfill_request_id,
                "repository_id": row.repository_id,
                "source_run_id": row.source_run_id,
                "operator_note": row.operator_note,
                "created_at": row.created_at,
            },
        ),
    )
    return row


def list_replay_events(
    queue: Any,
    *,
    repository_id: str | None = None,
    source_run_id: str | None = None,
    work_item_id: str | None = None,
    failure_class: str | None = None,
    limit: int = 100,
) -> list[FactReplayEventRow]:
    """Return durable replay audit rows with optional selectors."""

    rows = queue._record_operation(
        operation="list_replay_events",
        callback=lambda: queue._fetchall(
            """
            SELECT replay_event_id,
                   work_item_id,
                   repository_id,
                   source_run_id,
                   work_type,
                   failure_class,
                   operator_note,
                   created_at
            FROM fact_replay_events
            WHERE (%(repository_id)s IS NULL OR repository_id = %(repository_id)s)
              AND (%(source_run_id)s IS NULL OR source_run_id = %(source_run_id)s)
              AND (%(work_item_id)s IS NULL OR work_item_id = %(work_item_id)s)
              AND (%(failure_class)s IS NULL OR failure_class = %(failure_class)s)
            ORDER BY created_at DESC, replay_event_id DESC
            LIMIT %(limit)s
            """,
            {
                "repository_id": repository_id,
                "source_run_id": source_run_id,
                "work_item_id": work_item_id,
                "failure_class": failure_class,
                "limit": max(limit, 1),
            },
        ),
        row_count=None,
    )
    return [FactReplayEventRow(**row) for row in rows]
