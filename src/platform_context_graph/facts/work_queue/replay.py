"""Replay helpers for the PostgreSQL-backed fact work queue."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from .models import FactReplayEventRow
from .models import FactWorkItemRow
from .support import utc_now

_INSERT_REPLAY_EVENTS_SQL = """
INSERT INTO fact_replay_events (
    replay_event_id,
    work_item_id,
    repository_id,
    source_run_id,
    work_type,
    failure_class,
    operator_note,
    created_at
) VALUES (
    %(replay_event_id)s,
    %(work_item_id)s,
    %(repository_id)s,
    %(source_run_id)s,
    %(work_type)s,
    %(failure_class)s,
    %(operator_note)s,
    %(created_at)s
)
"""


def _replay_event_params(event: FactReplayEventRow) -> dict[str, Any]:
    """Return SQL parameters for one replay-event row."""

    return {
        "replay_event_id": event.replay_event_id,
        "work_item_id": event.work_item_id,
        "repository_id": event.repository_id,
        "source_run_id": event.source_run_id,
        "work_type": event.work_type,
        "failure_class": event.failure_class,
        "operator_note": event.operator_note,
        "created_at": event.created_at,
    }


def _record_replay_events(
    queue: Any,
    *,
    replayed_rows: list[FactWorkItemRow],
    operator_note: str | None,
) -> list[FactReplayEventRow]:
    """Persist one durable replay event for each replayed work item."""

    created_at = utc_now()
    events: list[FactReplayEventRow] = []
    for row in replayed_rows:
        event = FactReplayEventRow(
            replay_event_id=f"fact-replay:{uuid4()}",
            work_item_id=row.work_item_id,
            repository_id=row.repository_id,
            source_run_id=row.source_run_id,
            work_type=row.work_type,
            failure_class=row.failure_class,
            operator_note=operator_note,
            created_at=created_at,
        )
        events.append(event)
    if events:
        queue._executemany(
            _INSERT_REPLAY_EVENTS_SQL,
            [_replay_event_params(event) for event in events],
        )
    return events


def replay_failed_work_items(
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
                  AND (%(failure_class)s IS NULL OR failure_class = %(failure_class)s)
                ORDER BY updated_at ASC
                LIMIT %(limit)s
            )
            UPDATE fact_work_items
            SET status = 'pending',
                lease_owner = NULL,
                lease_expires_at = NULL,
                attempt_count = 0,
                failure_stage = NULL,
                error_class = NULL,
                failure_class = NULL,
                failure_code = NULL,
                retry_disposition = NULL,
                dead_lettered_at = NULL,
                last_attempt_started_at = NULL,
                last_attempt_finished_at = NULL,
                next_retry_at = NULL,
                operator_note = %(operator_note)s,
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
                "failure_class": failure_class,
                "operator_note": operator_note,
                "limit": max(limit, 1),
                "updated_at": utc_now(),
            },
        ),
        row_count=None,
    )
    replayed_rows = [FactWorkItemRow(**row) for row in rows]
    _record_replay_events(
        queue,
        replayed_rows=replayed_rows,
        operator_note=operator_note,
    )
    return replayed_rows
