"""Typed row models for the fact work queue."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class FactWorkItemRow:
    """One queued or leased fact-projection work item."""

    work_item_id: str
    work_type: str
    repository_id: str
    source_run_id: str
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    status: str = "pending"
    attempt_count: int = 0
    last_error: str | None = None
    failure_stage: str | None = None
    error_class: str | None = None
    failure_class: str | None = None
    failure_code: str | None = None
    retry_disposition: str | None = None
    dead_lettered_at: datetime | None = None
    last_attempt_started_at: datetime | None = None
    last_attempt_finished_at: datetime | None = None
    next_retry_at: datetime | None = None
    operator_note: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class FactWorkQueueSnapshotRow:
    """One aggregated queue depth and age observation."""

    work_type: str
    status: str
    depth: int
    oldest_age_seconds: float


@dataclass(frozen=True, slots=True)
class FactReplayEventRow:
    """One durable operator replay event for fact work items."""

    replay_event_id: str
    work_item_id: str
    repository_id: str
    source_run_id: str
    work_type: str
    failure_class: str | None = None
    operator_note: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class FactBackfillRequestRow:
    """One durable operator-created backfill request."""

    backfill_request_id: str
    repository_id: str | None = None
    source_run_id: str | None = None
    operator_note: str | None = None
    created_at: datetime | None = None
