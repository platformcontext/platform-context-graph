"""Storage-facing row models for facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class FactRunRow:
    """One persisted fact-ingestion run."""

    source_run_id: str
    source_system: str
    source_snapshot_id: str
    repository_id: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class FactRecordRow:
    """One persisted fact record."""

    fact_id: str
    fact_type: str
    repository_id: str
    checkout_path: str
    relative_path: str | None
    source_system: str
    source_run_id: str
    source_snapshot_id: str
    payload: dict[str, Any]
    observed_at: datetime
    ingested_at: datetime
    provenance: dict[str, Any]
