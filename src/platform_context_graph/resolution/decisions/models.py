"""Typed models for persisted projection decisions and evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class ProjectionDecisionRow:
    """One persisted projection decision."""

    decision_id: str
    decision_type: str
    repository_id: str
    source_run_id: str
    work_item_id: str
    subject: str
    confidence_score: float
    confidence_reason: str
    provenance_summary: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ProjectionDecisionEvidenceRow:
    """One evidence record attached to a persisted projection decision."""

    evidence_id: str
    decision_id: str
    fact_id: str | None
    evidence_kind: str
    detail: dict[str, Any]
    created_at: datetime
