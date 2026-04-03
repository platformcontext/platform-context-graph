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
    created_at: datetime | None = None
    updated_at: datetime | None = None
